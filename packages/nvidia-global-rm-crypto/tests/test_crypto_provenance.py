#!/usr/bin/env python3
"""Check the exact upstream ABI and source-profile evidence; no GPU access."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import unittest

PACKAGE = Path(__file__).resolve().parents[1]
REPOSITORY = PACKAGE.parents[1]
UPSTREAM: Path | None = None
MANIFEST = json.loads((PACKAGE / "upstream/PROVENANCE.json").read_text())


class CryptoProvenance(unittest.TestCase):
    def test_pinned_source(self):
        self.assertEqual(MANIFEST["upstream"]["repository"],
                         "NVIDIA/open-gpu-kernel-modules")
        self.assertEqual(MANIFEST["upstream"]["commit"],
                         "1a82fbfda8f321b056eb3568850f9316c5e465c5")
        self.assertEqual(MANIFEST["upstream"]["libspdm_version"], "3.5.0")

    def test_reference_headers_are_unmodified(self):
        self.assertEqual(len(MANIFEST["references"]), 9)
        for reference in MANIFEST["references"]:
            with self.subTest(path=reference["path"]):
                data = (PACKAGE / "upstream" / reference["path"]).read_bytes()
                self.assertEqual(hashlib.sha256(data).hexdigest(),
                                 reference["sha256"])
                if UPSTREAM:
                    self.assertEqual(data,
                                     (UPSTREAM / reference["source_path"]).read_bytes())

    def test_selected_global_closure_matches_exact_symbol_set(self):
        closure = json.loads((REPOSITORY /
            "builders/reference/nvidia-rm-full-closure.json").read_text())
        symbols = [row["original"] for row in MANIFEST["symbols"]]
        self.assertEqual(len(symbols), 64)
        for profile in closure["profiles"].values():
            selected = profile["selected_rm_startup"]["relocation_required_undefined"]
            self.assertEqual(set(MANIFEST["selected_global_only_symbols"]),
                             {symbol for symbol in selected if symbol.startswith("libspdm_")})
            complete = profile["all_exported_rm"]["relocation_required_undefined"]
            self.assertEqual(set(symbols),
                             {symbol for symbol in complete if symbol.startswith("libspdm_")})
        self.assertEqual(set(symbols),
                         set(MANIFEST["selected_global_adapter_isr_symbols"]))
        self.assertEqual([row["bit"] for row in MANIFEST["symbols"]],
                         list(range(64)))
        for row in MANIFEST["symbols"]:
            self.assertEqual(row["facade"], "s540Global_" + row["original"])

    def test_explicit_unavailable_contract(self):
        self.assertFalse(MANIFEST["crypto_implemented"])
        self.assertTrue(MANIFEST["success_requires_lifetime_unavailable_calls_zero"])
        self.assertFalse(MANIFEST["counter_reset_supported"])
        self.assertEqual(MANIFEST["profile"], "tu117-no-spdm-crypto-backend")

    def test_profile_evidence_is_pinned(self):
        self.assertEqual(len(MANIFEST["source_evidence"]), 6)
        if not UPSTREAM:
            self.skipTest("Pass --upstream to verify the complete pinned NVIDIA source tree")
        for evidence in MANIFEST["source_evidence"]:
            with self.subTest(path=evidence["source_path"]):
                data = (UPSTREAM / evidence["source_path"]).read_bytes()
                self.assertEqual(hashlib.sha256(data).hexdigest(), evidence["sha256"])
                lines = data.decode().splitlines()
                self.assertIn(evidence["anchor"], lines[evidence["line"] - 1])

    def test_license_preserved(self):
        reference = MANIFEST["license"]
        data = (PACKAGE / "upstream" / reference["path"]).read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(), reference["sha256"])
        self.assertIn(b"BSD 3-Clause License", data)
        self.assertIn(b"Distributed Management Task Force", data)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", type=Path)
    arguments, remaining = parser.parse_known_args()
    UPSTREAM = arguments.upstream
    unittest.main(argv=[__file__, *remaining])
