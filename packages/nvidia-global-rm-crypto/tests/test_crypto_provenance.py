#!/usr/bin/env python3
"""Check the exact upstream ABI and source-profile evidence; no GPU access."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import unittest

PACKAGE = Path(__file__).resolve().parents[1]
REPOSITORY = PACKAGE.parents[1]
UPSTREAM: Path | None = None
MANIFEST = json.loads((PACKAGE / "upstream/PROVENANCE.json").read_text())
REACHABILITY = json.loads((PACKAGE / "CRYPTO-REACHABILITY.json").read_text())


def c_code(text: str) -> str:
    """Keep identifiers, excluding strings/comments from reference inventories."""
    lexical = re.compile(
        r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|/\*[\s\S]*?\*/|//[^\n]*')
    return lexical.sub(lambda match: "\n" * match.group().count("\n"), text)


def function_body(text: str, name: str) -> str:
    code = c_code(text)
    declaration = re.search(r"\b" + re.escape(name) + r"\s*\([^;]*?\)\s*\{", code,
                            flags=re.DOTALL)
    if declaration is None:
        raise AssertionError(f"Function definition not found: {name}")
    start = declaration.end() - 1
    depth = 0
    for offset in range(start, len(code)):
        depth += (code[offset] == "{") - (code[offset] == "}")
        if depth == 0:
            return code[start:offset + 1]
    raise AssertionError(f"Unbalanced function definition: {name}")


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

    def test_reachability_exact_boundaries_and_remaining_root(self):
        self.assertEqual(REACHABILITY["commit"], MANIFEST["upstream"]["commit"])
        self.assertEqual(REACHABILITY["counts"], {
            "symbols": 64, "with_concrete_fixed_profile_source_exclusion": 63,
            "remaining_admissible_root_exclusions": 1,
            "implemented_crypto_operations": 0})
        self.assertFalse(REACHABILITY["production_candidate_allowed"])
        self.assertFalse(REACHABILITY["gpu_access"])
        self.assertEqual(REACHABILITY["kernel_execution"], "not_tested")
        rows = REACHABILITY["symbols"]
        self.assertEqual([(row["symbol"], row["facade"], row["bit"]) for row in rows],
                         [(row["original"], row["facade"], row["bit"])
                          for row in MANIFEST["symbols"]])
        unresolved = []
        for row in rows:
            with self.subTest(symbol=row["symbol"]):
                self.assertFalse(row["operation_implemented"])
                self.assertFalse(row["whole_program_admission"])
                self.assertTrue(row["unexpected_invocation_blocks_adapter_success"])
                self.assertIn("spdm-disabled-tu117", row["guard_proofs"])
                for proof in row["guard_proofs"]:
                    self.assertIn(proof, REACHABILITY["guard_proofs"])
                if row["additional_admissible_root_proof_required"]:
                    unresolved.append(row["symbol"])
                    self.assertFalse(row["fixed_profile_source_exclusion_proved"])
                else:
                    self.assertTrue(row["fixed_profile_source_exclusion_proved"])
        self.assertEqual(unresolved, ["libspdm_random_bytes"])
        self.assertEqual(unresolved, REACHABILITY["remaining_unproved"])
        for name in ("crypto_implemented", "source_guard_is_runtime_test",
                     "lexical_reference_inventory_is_complete_callgraph",
                     "zero_observed_calls_are_source_exclusion_proof",
                     "no_userclient_is_source_exclusion_proof",
                     "runtime_GSP_client_equals_PLATFORM_GSP_build",
                     "noCC_implies_noNVLE",
                     "checked_NvLinkDisable_alone_proves_common_library_absence",
                     "counter_reset_supported", "production_candidate_allowed"):
            self.assertIs(REACHABILITY["rules"][name], False)

    def test_reachability_source_hashes(self):
        self.assertEqual(len(REACHABILITY["source_sha256"]), 36)
        for proof in REACHABILITY["guard_proofs"].values():
            for source in proof["sources"]:
                self.assertIn(source["path"], REACHABILITY["source_sha256"])
        if not UPSTREAM:
            self.skipTest("Pass --upstream to check the complete source-guard audit")
        for path, expected in REACHABILITY["source_sha256"].items():
            with self.subTest(path=path):
                self.assertEqual(hashlib.sha256((UPSTREAM / path).read_bytes()).hexdigest(),
                                 expected)

    def test_reachability_nonlibrary_entry_inventory(self):
        if not UPSTREAM:
            self.skipTest("Pass --upstream to check all nonlibrary entry references")
        symbols = {row["original"] for row in MANIFEST["symbols"]}
        primitives = re.compile(r"\b(" + "|".join(sorted(symbols)) + r")\b")
        actual = []
        for path in sorted((UPSTREAM / "src/nvidia").rglob("*.c")):
            relative = path.relative_to(UPSTREAM).as_posix()
            if "/libraries/libspdm/" in relative:
                continue
            code = c_code(path.read_text())
            calls = sorted(set(re.findall(r"\b((?:libspdm|nvspdm)_\w+)\s*\(", code)))
            references = sorted(set(primitives.findall(code)))
            if calls or references:
                actual.append({"path": relative, "library_calls": calls,
                               "crypto64_references": references})
        self.assertEqual(actual, REACHABILITY["nonlibrary_entry_inventory"]["files"])
        self.assertEqual(len(actual), 8)

    def test_reachability_guard_order_and_firmware_separation(self):
        if not UPSTREAM:
            self.skipTest("Pass --upstream to check the original guard bodies")
        read = lambda path: (UPSTREAM / path).read_text()
        ccsl = read("src/nvidia/src/kernel/gpu/conf_compute/ccsl.c")
        for name in ("ccslContextInitViaChannel_IMPL", "ccslContextInitViaKeyId_KERNEL"):
            body = function_body(ccsl, name)
            capability = body.index("if(!pGpuMgr->ccCaps.bHccFeatureCapable)")
            self.assertLess(capability, body.index("portMemAllocNonPaged(sizeof(*pCtx))"))
            self.assertLess(capability, body.index("libspdm_aead_gcm_prealloc"))
        spdm = read("src/nvidia/src/kernel/gpu/spdm/spdm.c")
        body = function_body(spdm, "spdmContextInit_IMPL")
        self.assertLess(body.index("libspdm_check_crypto_backend"),
                        body.index("libspdm_init_context"))
        body = function_body(spdm, "_spdmClearContext")
        self.assertLess(body.index("if (pSpdm->pLibspdmContext != NULL)"),
                        body.index("libspdm_deinit_context"))
        for path in (
                "src/nvidia/src/kernel/gpu/gsp/kernel_gsp_booter.c",
                "src/nvidia/src/kernel/gpu/gsp/kernel_gsp_fwsec.c",
                "src/nvidia/src/kernel/gpu/gsp/arch/turing/kernel_gsp_booter_tu102.c",
                "src/nvidia/src/kernel/gpu/gsp/arch/turing/kernel_gsp_frts_tu102.c",
                "src/nvidia/src/kernel/gpu/gsp/arch/turing/kernel_gsp_falcon_tu102.c"):
            self.assertNotRegex(c_code(read(path)), r"\b(?:libspdm|nvspdm)_\w+")
        nvlink = read("src/nvidia/src/kernel/gpu/nvlink/kernel_nvlink.c")
        self.assertIn("libspdm_random_bytes",
                      function_body(nvlink, "knvlinkRotateEncryptionKeys_IMPL"))
        # A no-caller token inventory is deliberately still an unresolved root.
        references = []
        for path in sorted((UPSTREAM / "src/nvidia").rglob("*")):
            if path.suffix in (".c", ".h") and re.search(
                    r"\bknvlinkRotateEncryptionKeys(?:_IMPL)?\b", c_code(path.read_text())):
                references.append(path.relative_to(UPSTREAM).as_posix())
        self.assertEqual(references, [
            "src/nvidia/generated/g_kernel_nvlink_nvoc.h",
            "src/nvidia/src/kernel/gpu/nvlink/kernel_nvlink.c"])
        self.assertEqual(REACHABILITY["remaining_unproved"], ["libspdm_random_bytes"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", type=Path)
    arguments, remaining = parser.parse_known_args()
    UPSTREAM = arguments.upstream
    unittest.main(argv=[__file__, *remaining])
