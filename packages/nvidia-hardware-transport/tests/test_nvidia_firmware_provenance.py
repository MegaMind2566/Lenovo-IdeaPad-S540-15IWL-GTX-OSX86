#!/usr/bin/env python3
"""Offline pin and contract checks for the CPU firmware/RPC preflight."""
import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1] / "firmware"
MANIFEST = json.loads((ROOT / "PROVENANCE.json").read_text())


class Provenance(unittest.TestCase):
    def test_source_pin(self):
        self.assertEqual(MANIFEST["repository"], "NVIDIA/open-gpu-kernel-modules")
        self.assertEqual(MANIFEST["commit"], "1a82fbfda8f321b056eb3568850f9316c5e465c5")
        self.assertEqual(MANIFEST["release"], "615.78.08")
        self.assertEqual(MANIFEST["license"], "MIT")

    def test_reference_hashes(self):
        self.assertEqual(len(MANIFEST["inputs"]), 11)
        for entry in MANIFEST["inputs"]:
            data = (ROOT / entry["local_path"]).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), entry["local_sha256"])
            if entry["mode"] == "verbatim":
                blob = b"blob " + str(len(data)).encode() + b"\0" + data
                self.assertEqual(hashlib.sha1(blob).hexdigest(), entry["blob_sha"])

    def test_source_license_retained(self):
        for entry in MANIFEST["inputs"]:
            text = (ROOT / entry["local_path"]).read_text()
            self.assertIn("SPDX-License-Identifier: MIT", text)
            self.assertIn("NVIDIA CORPORATION", text)

    def test_actual_section_and_family_definitions(self):
        text = (ROOT / "reference/gsp_section_names.h.in").read_text()
        for section in (".fwversion", ".fwimage", ".fwsignature_", ".note.gnu.build-id"):
            self.assertIn(section, text)
        select = (ROOT / "reference/nv-firmware-chip-family-select.h").read_text()
        self.assertIn("gpuImpl <= GPU_IMPLEMENTATION_TU106", select)
        self.assertIn("return NV_FIRMWARE_CHIP_FAMILY_TU11X", select)
        arch = (ROOT / "reference/target_arch.h.in").read_text()
        self.assertIn("GPU_IMPLEMENTATION_TU117         0x07", arch)
        self.assertIn("GPU_IMPLEMENTATION_TU106         0x06", arch)

    def test_rpc_layout(self):
        text = (ROOT / "reference/g_rpc-message-header.h").read_text()
        fields = ("header_version", "signature", "length", "function", "rpc_result;", "rpc_result_private", "sequence")
        indexes = [text.index(field) for field in fields]
        self.assertEqual(indexes, sorted(indexes))
        self.assertIn("0x43505256", (ROOT / "reference/rpc_headers.h").read_text())
        self.assertIn("0x25", (ROOT / "reference/nvdm_format.h").read_text())

    def test_firmware_absence_is_explicit(self):
        self.assertEqual(MANIFEST["firmware_assets"], [])
        self.assertEqual(MANIFEST["approved_image_hashes"], [])
        self.assertIs(MANIFEST["synthetic_fixture_only"], True)
        self.assertEqual(list(ROOT.rglob("*.bin")), [])

    def test_excerpt_functions(self):
        entry = next(item for item in MANIFEST["inputs"] if item["mode"] == "exact-function-excerpts")
        self.assertEqual(len(entry["functions"]), 4)
        text = (ROOT / entry["local_path"]).read_text()
        for function in entry["functions"]:
            self.assertIn(function + "\n(", text)
        self.assertIn("NV_VERSION_STRING", text)
        self.assertIn("elfClass64", text)


if __name__ == "__main__":
    unittest.main()
