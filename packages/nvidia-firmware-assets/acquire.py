#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Acquire unmodified pinned NVIDIA firmware without executing its installer."""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import tarfile
import tempfile
import time
import urllib.parse
import urllib.request

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parent
MANIFEST = json.loads((ROOT / "MANIFEST.json").read_text())
MAX_EXPANDED = 2 * 1024 * 1024 * 1024
MAX_MEMBER = 256 * 1024 * 1024
MAX_MEMBERS = 20000
ASSET_NAMES = {"firmware/gsp_tu10x.bin": "gsp_tu10x.bin",
               "firmware/ucodes_tu10x.bin": "ucodes_tu10x.bin",
               "LICENSE": "NVIDIA-DRIVER-LICENSE.txt"}


class AssetError(RuntimeError):
    pass


def regular_file(path: Path):
    # A FIFO must not block before fstat can reject its file type.
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise AssetError("Expected a regular file")
    except BaseException:
        os.close(fd)
        raise
    return os.fdopen(fd, "rb")


def digest_handle(handle, expected_size: int | None = None) -> str:
    before = os.fstat(handle.fileno())
    if not stat.S_ISREG(before.st_mode):
        raise AssetError("Expected a regular file")
    if expected_size is not None and before.st_size != expected_size:
        raise AssetError("Pinned file size mismatch")
    digest = hashlib.sha256()
    handle.seek(0)
    while chunk := handle.read(1024 * 1024):
        digest.update(chunk)
    after = os.fstat(handle.fileno())
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
        raise AssetError("File changed while checking its hash")
    return digest.hexdigest()


def digest_file(path: Path, expected_size: int | None = None) -> str:
    with regular_file(path) as handle:
        return digest_handle(handle, expected_size)


def archive_payload_offset(prefix: bytes) -> int:
    """The pinned makeself skip is a 1-based tail line, not a byte offset."""
    expected = MANIFEST["archive"]
    if not prefix.startswith(b"#! /bin/sh\n"):
        raise AssetError("Unexpected installer header")
    matches = re.findall(rb"^skip=(\d+)$", prefix[:4096], re.M)
    if matches != [str(expected["skip_line"]).encode()]:
        raise AssetError("Unexpected installer payload line")
    offset = 0
    for _ in range(expected["skip_line"] - 1):
        end = prefix.find(b"\n", offset)
        if end < 0:
            raise AssetError("Truncated installer header")
        offset = end + 1
    if offset != expected["payload_offset"] or prefix[offset:offset + 4] != b"\x28\xb5\x2f\xfd":
        raise AssetError("Unexpected pinned zstd payload offset")
    return offset


class NvidiaRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urllib.parse.urlsplit(newurl)
        if parsed.scheme != "https" or not parsed.hostname or not parsed.hostname.endswith(".nvidia.com"):
            raise AssetError("Firmware source redirected outside NVIDIA HTTPS")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download_archive(cache: Path) -> Path:
    cache.mkdir(parents=True, exist_ok=True)
    source = MANIFEST["archive"]
    name = PurePosixPath(urllib.parse.urlsplit(source["url"]).path).name
    target = cache / name
    if target.exists() or target.is_symlink():
        if digest_file(target, source["size"]) != source["sha256"]:
            raise AssetError("Cached archive does not match the pinned official archive")
        return target
    opener = urllib.request.build_opener(NvidiaRedirect())
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix="nvidia-download-", dir=cache, delete=False) as out:
            temporary = Path(out.name)
            digest = hashlib.sha256()
            received = 0
            started = time.monotonic()
            with opener.open(source["url"], timeout=30) as response:
                if response.status != 200 or int(response.headers.get("Content-Length", "-1")) != source["size"]:
                    raise AssetError("Unexpected official archive response")
                while chunk := response.read(1024 * 1024):
                    received += len(chunk)
                    if received > source["size"] or time.monotonic() - started > 600:
                        raise AssetError("Official archive exceeded its size/time limit")
                    digest.update(chunk)
                    out.write(chunk)
            if received != source["size"] or digest.hexdigest() != source["sha256"]:
                raise AssetError("Official archive SHA256 mismatch")
        os.replace(temporary, target)
        temporary = None
        return target
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def safe_member_name(name: str) -> bool:
    return bool(name) and not name.startswith("/") and "\\" not in name and "\0" not in name and all(
        part not in ("", ".", "..") for part in name.split("/"))


class LimitedReader:
    def __init__(self, source, maximum=MAX_EXPANDED):
        self.source, self.maximum, self.used = source, maximum, 0

    def read(self, count):
        if count < 0:
            raise AssetError("Unbounded archive read is forbidden")
        chunk = self.source.read(min(count, self.maximum - self.used + 1))
        self.used += len(chunk)
        if self.used > self.maximum:
            raise AssetError("Archive exceeded expanded size limit")
        return chunk


def extract_selected_tar(source, output: Path, expected_assets=None):
    """Never call extract/extractall: only three fixed regular-file members."""
    expected_assets = expected_assets or MANIFEST["assets"]
    expected = {item["archive_path"]: item for item in expected_assets}
    selected, count, expanded = set(), 0, 0
    output.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=source, mode="r|", bufsize=1024 * 1024) as archive:
        for member in archive:
            count += 1
            # The official tar includes a root-directory marker. It creates
            # nothing because extraction is manual and the marker is ignored.
            if member.name == "." and member.isdir() and member.size == 0:
                if count > MAX_MEMBERS:
                    raise AssetError("Excessive archive members")
                continue
            if count > MAX_MEMBERS or not safe_member_name(member.name):
                raise AssetError("Unsafe or excessive archive members")
            if member.size < 0 or member.size > MAX_MEMBER:
                raise AssetError("Archive member exceeded size limit")
            expanded += member.size
            if expanded > MAX_EXPANDED:
                raise AssetError("Archive exceeded declared expanded size limit")
            if member.name not in ASSET_NAMES:
                continue
            if member.name in selected or not member.isfile() or member.sparse is not None:
                raise AssetError("Selected asset is duplicate, sparse or not a regular file")
            pin = expected[member.name]
            if member.size != pin["size"]:
                raise AssetError("Selected asset size does not match the manifest")
            handle = archive.extractfile(member)
            if handle is None:
                raise AssetError("Selected asset cannot be read")
            data = handle.read(pin["size"] + 1)
            if len(data) != pin["size"] or hashlib.sha256(data).hexdigest() != pin["sha256"]:
                raise AssetError("Selected asset SHA256 mismatch")
            destination = output / ASSET_NAMES[member.name]
            fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "wb") as out:
                out.write(data)
            selected.add(member.name)
    if selected != set(ASSET_NAMES):
        raise AssetError("Required NVIDIA firmware or license member is missing")
    return {"members_checked": count, "declared_expanded_bytes": expanded}


def verify_assets(directory: Path):
    if directory.is_symlink() or not directory.is_dir():
        raise AssetError("Expected a real firmware directory")
    if {item.name for item in directory.iterdir()} != set(ASSET_NAMES.values()):
        raise AssetError("Firmware directory contains missing or unexpected items")
    result = []
    for pin in MANIFEST["assets"]:
        name = ASSET_NAMES[pin["archive_path"]]
        if digest_file(directory / name, pin["size"]) != pin["sha256"]:
            raise AssetError("Extracted asset SHA256 mismatch")
        result.append({"filename": name, "size": pin["size"], "sha256": pin["sha256"]})
    return result


def acquire(directory: Path, *, cache: Path | None = None, archive_path: Path | None = None):
    if archive_path is None:
        if cache is None:
            raise AssetError("An archive or download cache is required")
        archive_path = download_archive(cache)
    source = MANIFEST["archive"]
    if digest_file(archive_path, source["size"]) != source["sha256"]:
        raise AssetError("Archive does not match the pinned official SHA256")
    if directory.exists():
        return {"assets": verify_assets(directory), "archive_sha256": source["sha256"], "cache_reused": True}
    try:
        import zstandard
    except ImportError as error:
        raise AssetError("Install the pinned zstandard build dependency") from error
    directory.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="nvidia-verified-", dir=directory.parent) as temporary:
        staging = Path(temporary) / "firmware"
        # Hash and decompress the same already-open regular file descriptor.
        with regular_file(archive_path) as handle:
            if digest_handle(handle, source["size"]) != source["sha256"]:
                raise AssetError("Archive changed before decompression")
            handle.seek(0)
            prefix = handle.read(1024 * 1024)
            offset = archive_payload_offset(prefix)
            handle.seek(offset)
            decompressor = zstandard.ZstdDecompressor(max_window_size=128 * 1024 * 1024)
            with decompressor.stream_reader(handle) as stream:
                details = extract_selected_tar(LimitedReader(stream), staging)
        assets = verify_assets(staging)
        os.rename(staging, directory)
    return {"assets": assets, "archive_sha256": source["sha256"], "cache_reused": False, **details}
