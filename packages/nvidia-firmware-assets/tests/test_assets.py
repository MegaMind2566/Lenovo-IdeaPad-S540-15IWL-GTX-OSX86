#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Targeted archive, provenance and immutable asset handling tests."""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tarfile
import tempfile
import unittest
import sys

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("nvidia_firmware_acquire", ROOT / "acquire.py")
ACQUIRE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ACQUIRE)


def tar_bytes(members):
    result = io.BytesIO()
    with tarfile.open(fileobj=result, mode="w") as archive:
        for name, data, kind in members:
            member = tarfile.TarInfo(name)
            member.type = kind
            if kind == tarfile.REGTYPE:
                member.size = len(data)
                archive.addfile(member, io.BytesIO(data))
            else:
                member.linkname = "gsp_tu10x.bin"
                archive.addfile(member)
    result.seek(0)
    return result


GOOD = [(name, bytes([i]), tarfile.REGTYPE) for i, name in enumerate(ACQUIRE.ASSET_NAMES)]
PINS = [{"archive_path": name, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        for name, data, _ in GOOD]


class Assets(unittest.TestCase):
    def test_manifest_source_pin(self):
        m = ACQUIRE.MANIFEST
        self.assertEqual(m["source_commit"], "1a82fbfda8f321b056eb3568850f9316c5e465c5")
        self.assertEqual(m["release"], "615.78.08")
        self.assertEqual(m["archive"]["sha256"], "e9d5167f4ca67f58b2b3447584b1e4273218d5088aba210d3aef2a407e522892")
        self.assertEqual(m["archive"]["size"], 408754604)
        self.assertEqual(m["approved_pair"]["ucodes_fingerprint"], "0x8d1990ab6b98ae2b")

    def test_reference_hashes_and_license(self):
        for item in ACQUIRE.MANIFEST["references"]:
            data = (ROOT / item["local_path"]).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), item["sha256"])
            self.assertIn(b"SPDX-License-Identifier: MIT", data)
            if item["mode"] == "verbatim":
                self.assertEqual(hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest(), item["git_blob_sha1"])
        notice = (ROOT / "NVIDIA-DRIVER-LICENSE.txt").read_bytes()
        self.assertEqual(hashlib.sha256(notice).hexdigest(), ACQUIRE.MANIFEST["redistribution"]["notice_sha256"])
        self.assertIn(b"operating system kernels", notice)
        self.assertIn(b"this Agreement is provided to each SOFTWARE", notice)

    def test_no_firmware_in_source_package(self):
        self.assertEqual(list(ROOT.rglob("*.bin")), [])
        self.assertIs(ACQUIRE.MANIFEST["redistribution"]["automatic_asset_packaging"], True)

    def test_safe_exact_members(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "firmware"
            result = ACQUIRE.extract_selected_tar(tar_bytes(GOOD), out, PINS)
            self.assertEqual(result["members_checked"], 3)
            self.assertEqual({p.name for p in out.iterdir()}, set(ACQUIRE.ASSET_NAMES.values()))

    def test_official_root_directory_marker_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = ACQUIRE.extract_selected_tar(tar_bytes([(".",b"",tarfile.DIRTYPE)] + GOOD), Path(tmp) / "out", PINS)
            self.assertEqual(result["members_checked"], 4)

    def test_path_traversal_rejected(self):
        for name in ("../escape", "/absolute", "firmware/../escape", "a\\b"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(ACQUIRE.AssetError):
                    ACQUIRE.extract_selected_tar(tar_bytes([(name,b"x",tarfile.REGTYPE)] + GOOD), Path(tmp) / "out", PINS)

    def test_symlink_and_hardlink_selected_rejected(self):
        for kind in (tarfile.SYMTYPE, tarfile.LNKTYPE):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                bad = [(GOOD[0][0], b"", kind)] + GOOD[1:]
                with self.assertRaises(ACQUIRE.AssetError):
                    ACQUIRE.extract_selected_tar(tar_bytes(bad), Path(tmp) / "out", PINS)

    def test_duplicate_selected_rejected(self):
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(ACQUIRE.AssetError):
            ACQUIRE.extract_selected_tar(tar_bytes(GOOD + [GOOD[0]]), Path(tmp) / "out", PINS)

    def test_hash_and_size_rejected(self):
        for data in (b"z", b"too long"):
            with self.subTest(data=data), tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(ACQUIRE.AssetError):
                    ACQUIRE.extract_selected_tar(tar_bytes([(GOOD[0][0],data,tarfile.REGTYPE)] + GOOD[1:]), Path(tmp) / "out", PINS)

    def test_missing_member_rejected(self):
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(ACQUIRE.AssetError):
            ACQUIRE.extract_selected_tar(tar_bytes(GOOD[:-1]), Path(tmp) / "out", PINS)

    def test_existing_destination_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp);(out / "gsp_tu10x.bin").write_bytes(b"existing")
            with self.assertRaises(FileExistsError):
                ACQUIRE.extract_selected_tar(tar_bytes(GOOD), out, PINS)
            self.assertEqual((out / "gsp_tu10x.bin").read_bytes(), b"existing")

    def test_expanded_limit(self):
        limited = ACQUIRE.LimitedReader(io.BytesIO(b"0123456789"), maximum=4)
        self.assertEqual(limited.read(4), b"0123")
        with self.assertRaises(ACQUIRE.AssetError):
            limited.read(1)
        with self.assertRaises(ACQUIRE.AssetError):
            ACQUIRE.LimitedReader(io.BytesIO(b"x")).read(-1)

    def test_pinned_payload_line_is_not_executed(self):
        prefix = b"#! /bin/sh\nskip=1015\n"
        padding = 160219 - len(prefix) - 1 - 1011
        prefix += b"x" * padding + b"\n" + b"\n" * 1011 + b"\x28\xb5\x2f\xfd"
        self.assertEqual(ACQUIRE.archive_payload_offset(prefix), 160219)
        with self.assertRaises(ACQUIRE.AssetError):
            ACQUIRE.archive_payload_offset(prefix.replace(b"skip=1015",b"skip=9999",1))
        with self.assertRaises(ACQUIRE.AssetError):
            ACQUIRE.archive_payload_offset(prefix[:-1])

    def test_symlink_file_hash_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp);(root / "file").write_bytes(b"x");(root / "link").symlink_to("file")
            with self.assertRaises(OSError):
                ACQUIRE.digest_file(root / "link",1)

    def test_fifo_file_hash_rejected_without_blocking(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fifo"; os.mkfifo(path)
            with self.assertRaises(ACQUIRE.AssetError):
                ACQUIRE.digest_file(path)

    def test_unexpected_asset_file_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "private.txt").write_text("not an asset")
            with self.assertRaises(ACQUIRE.AssetError):
                ACQUIRE.verify_assets(Path(tmp))


if __name__ == "__main__":
    unittest.main()
