#!/usr/bin/env python3
"""Validate pinned NVPort lifecycle inputs, exact caller bodies and explicit profile."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT / "packages/nvidia-nvport-lifecycle/upstream"
COMMIT = "1a82fbfda8f321b056eb3568850f9316c5e465c5"
PINNED = {'../../nvidia-os-adapter/upstream/include/nvtypes.h': ('src/common/sdk/nvidia/inc/nvtypes.h', 'cb6d906a34cf6ace3d852657cf8dde4a587d7721'), '../../nvidia-os-adapter/upstream/include/cpuopsys.h': ('src/common/sdk/nvidia/inc/cpuopsys.h', '6467b396a696a47fa71d4ad41e32d27f344fcdce'), '../../nvidia-os-adapter/upstream/include/nvstatus.h': ('src/common/sdk/nvidia/inc/nvstatus.h', '4f5284db2b1e6af1c2c0c85bc39dfc14daccc9fd'), '../../nvidia-os-adapter/upstream/include/nvstatuscodes.h': ('src/common/sdk/nvidia/inc/nvstatuscodes.h', '430eed77a03f2f15bf058d3c49931a9f89ace08e'), '../../nvidia-os-adapter/upstream/include/nv-kernel-interface-api.h': ('kernel-open/common/inc/nv-kernel-interface-api.h', '183f9b4312eb0913c0a0a97e4db1f62a50b442c5'), '../../nvidia-os-adapter/upstream/reference/os-interface.h': ('src/nvidia/arch/nvalloc/unix/include/os-interface.h', '03de89a28a2611bca2fb2a3d85c7f617a681a20a'), '../../nvidia-os-adapter/upstream/reference/memory.h': ('src/nvidia/inc/libraries/nvport/memory.h', '595eafee880dccd54ca2f382fb77afc918793e1d'), '../../nvidia-os-adapter/upstream/reference/debug.h': ('src/nvidia/inc/libraries/nvport/debug.h', 'c2929200e628022149e6c2fb1581469946ffe05a'), '../../nvidia-caller-integration/upstream/reference/memory_tracking.h': ('src/nvidia/inc/libraries/nvport/inline/memory_tracking.h', '37f11e95b6d6d4a02eefe1d66a0567a6baaed070'), '../../nvidia-caller-integration/upstream/reference/sync_unix_kernel_os.c': ('src/nvidia/src/libraries/nvport/sync/sync_unix_kernel_os.c', '9a545779dda38f261977a0da6b130ab62cf67f41'), '../../nvidia-caller-integration/upstream/reference/sync_unix_kernel_os_def.h': ('src/nvidia/src/libraries/nvport/sync/inc/sync_unix_kernel_os_def.h', 'b12c4ad3506d39de835d3bce5e45bb8c8eeafe70'), '../../nvidia-caller-integration/upstream/reference/sync.h': ('src/nvidia/inc/libraries/nvport/sync.h', '29e472dedf677501e11c22cb043431750c9f8f30'), 'reference/memory_tracking.c': ('src/nvidia/src/libraries/nvport/memory/memory_tracking.c', '4a23295fee7afd5472587ac223ff3ee7e82cbd13'), 'reference/sync_common.h': ('src/nvidia/src/libraries/nvport/sync/sync_common.h', 'babb90f5acf3c47bcbd3d8be4c276ec7d1063c95'), 'reference/safe_generic.h': ('src/nvidia/inc/libraries/nvport/inline/safe_generic.h', 'e701c2cecde7816760291c78b3fea5507acc82a5'), 'reference/safe.h': ('src/nvidia/inc/libraries/nvport/safe.h', '2847c71fffa39623abdd2748dadabb1f47deed45')}

def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def function(text: str, name: str) -> str:
    match = re.search(r"(?m)^" + re.escape(name) + r"\s*(?=\()", text)
    if match is None:
        raise ValueError("Missing function: " + name)
    start = text.rfind("\n", 0, match.start() - 1) + 1
    brace = text.index("{", match.end())
    depth, state, i = 0, "normal", brace
    while i < len(text):
        char, pair = text[i], text[i:i + 2]
        if state == "normal":
            if pair == "//":
                state, i = "line", i + 2
                continue
            if pair == "/*":
                state, i = "comment", i + 2
                continue
            if char == '"':
                state = "string"
            elif char == "'":
                state = "char"
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return text[start:i + 1] + "\n"
        elif state == "line":
            if char == "\n":
                state = "normal"
        elif state == "comment":
            if pair == "*/":
                state, i = "normal", i + 2
                continue
        elif state in ("string", "char"):
            if char == "\\":
                i += 2
                continue
            if (state == "string" and char == '"') or (state == "char" and char == "'"):
                state = "normal"
        i += 1
    raise ValueError("Unterminated function: " + name)


def macro(text: str, name: str) -> str:
    lines = text.splitlines(True)
    start = next(i for i, line in enumerate(lines)
                 if line.startswith("#define " + name + "(") or
                 line.startswith("#define " + name + " "))
    end = start + 1
    while lines[end - 1].rstrip().endswith("\\"):
        end += 1
    return "".join(lines[start:end])


class NvidiaLifecycleProvenance(unittest.TestCase):
    def setUp(self) -> None:
        self.report = json.loads((UPSTREAM / "PROVENANCE.json").read_text())

    def test_pinned_references(self) -> None:
        self.assertEqual(self.report["commit"], COMMIT)
        self.assertEqual(self.report["release"], "615.78.08")
        self.assertEqual({x["path"] for x in self.report["upstream_files"]}, set(PINNED))
        for item in self.report["upstream_files"]:
            path = UPSTREAM / item["path"]
            self.assertFalse(path.is_symlink())
            data = path.read_bytes()
            self.assertEqual((item["source_path"], item["git_blob_sha1"]), PINNED[item["path"]])
            blob = b"blob " + str(len(data)).encode() + b"\0" + data
            self.assertEqual(hashlib.sha1(blob).hexdigest(), item["git_blob_sha1"])
            self.assertEqual(sha256(data), item["sha256"])
            self.assertEqual(len(data), item["bytes"])
            self.assertFalse(item["modified"])
            self.assertIn(b"Permission is hereby granted", data)

    def test_exact_original_function_bodies(self) -> None:
        count = 0
        for unit in self.report["adapted_translation_units"]:
            data = (UPSTREAM / unit["path"]).read_bytes()
            self.assertEqual(sha256(data), unit["sha256"])
            self.assertFalse(unit["complete_upstream_translation_unit"])
            for item in unit["functions"]:
                source = (UPSTREAM / item["source_reference"]).read_text()
                original = function(source, item["source_function"])
                compiled = function(data.decode(), item["compiled_function"])
                self.assertEqual(sha256(original.encode()), item["source_body_sha256"])
                self.assertEqual(sha256(compiled.encode()), item["compiled_body_sha256"])
                if item["source_function"] != "portMemInitialize":
                    self.assertEqual(original, compiled)
                    self.assertEqual(item["changes"], [])
                    count += 1
        self.assertEqual(count, 41)

    def test_bootstrap_is_explicit_failure_atomic_adaptation(self) -> None:
        text = (UPSTREAM / "nvport_memory_lifecycle.c").read_text()
        body = function(text, "s540NvportMemoryInitialize")
        self.assertIn("NV_STATUS\ns540NvportMemoryInitialize", body)
        self.assertNotRegex(text, r"(?m)^portInitialize\(")
        self.assertNotRegex(text, r"(?m)^portMemInitialize\(")
        context = body.index("if (!s540NvportLifecycleContextAllowed())")
        allocation = body.index("pBootstrapLock = _portMemAllocNonPagedUntracked")
        null_check = body.index("if (pBootstrapLock == NULL)")
        spin_init = body.index("status = portSyncSpinlockInitialize(pBootstrapLock)")
        status_check = body.index("if (status != NV_OK)")
        cleanup = body.index("_portMemFreeUntracked(pBootstrapLock)")
        publication = body.index("portMemGlobals.mainTracking.pAllocator")
        self.assertLess(context, allocation)
        self.assertLess(allocation, null_check)
        self.assertLess(null_check, spin_init)
        self.assertLess(spin_init, status_check)
        self.assertLess(status_check, cleanup)
        self.assertLess(cleanup, publication)
        self.assertNotIn("PORT_MEM_LOCK_INIT(", text)
        self.assertIn("return status;", body)
        self.assertIn("return NV_ERR_NO_MEMORY;", body)
        self.assertIn("portMemGlobals.trackingLock = pBootstrapLock;", body)
        self.assertTrue(self.report["bootstrap_adaptation"]["failure_atomic"])
        self.assertFalse(self.report["bootstrap_adaptation"]["full_core_included"])

    def test_fixed_counter_only_profile(self) -> None:
        text = (UPSTREAM / "nvport_lifecycle_profile.h").read_text()
        values = dict(re.findall(r"(?m)^#define\s+(\w+)\s+(\d+)\s*$", text))
        self.assertEqual(values["PORT_MEM_TRACK_USE_COUNTER"], "1")
        for name in ("FENCEPOSTS", "ALLOCLIST", "CALLERINFO", "LOGGING", "LIMIT"):
            self.assertEqual(values["PORT_MEM_TRACK_USE_" + name], "0")
        self.assertEqual(values["PORT_MEM_TRACK_ALLOC_SIZE"], "0")
        self.assertEqual(values["PORT_MEM_STAGING_SIZE"], "0")
        self.assertIn("#define PORT_ASSERT_CHECKED(x)\n", text)
        self.assertIn("s540NvidiaCallerAssertionFailed", text)
        self.assertIn("#error", text)
        self.assertFalse(self.report["profile"]["allocation_byte_size"])

    def test_safe_length_add_is_original_macro_expansion(self) -> None:
        original = (UPSTREAM / "reference/safe_generic.h").read_text()
        compiled = (UPSTREAM / "nvport_safe_length.h").read_text()
        for name in ("PORT_EXPAND", "PORT_SAFE_Add_IMPL_U", "PORT_SAFE_Add_IMPL_",
                     "PORT_SAFE_DEFINE_MATH_FUNC"):
            self.assertEqual(macro(original, name), macro(compiled, name))
        self.assertIn("PORT_SAFE_DEFINE_MATH_FUNC(Add, , Length)", compiled)
        self.assertIn("PORT_SAFE_DEFINE_MATH_FUNC(Add, , Length)", original)
        self.assertIn("NvLength *pResult", (UPSTREAM / "reference/safe.h").read_text())

    def test_owned_objects_use_real_tracked_free(self) -> None:
        text = (UPSTREAM / "nvport_owned_sync.c").read_text()
        header = (UPSTREAM / "nvport_lifecycle.h").read_text()
        self.assertIn("#define PORT_FREE(pAlloc, pMem) _portMemAllocatorFree(pAlloc, pMem)", header)
        self.assertNotIn("unsupported", function(text, "portSyncMutexDestroy"))
        self.assertIn("PORT_FREE(pAllocator, pMutex);", function(text, "portSyncMutexCreate"))
        self.assertIn("PORT_FREE(pAllocator, pSpinlock);", function(text, "portSyncSpinlockCreate"))
        self.assertIn("PORT_FREE(pMutex->pAllocator, pMutex);", function(text, "portSyncMutexDestroy"))
        self.assertIn("PORT_FREE(pSpinlock->pAllocator, pSpinlock);", function(text, "portSyncSpinlockDestroy"))
        self.assertEqual(self.report["link_contract"]["exclude"],
                         ["../../nvidia-caller-integration/upstream/nvport_mutex_callers.c"])

    def test_interfaces_and_scope(self) -> None:
        for item in self.report["interfaces"]:
            self.assertEqual(sha256((UPSTREAM / item["path"]).read_bytes()), item["sha256"])
        scope = self.report["scope"]
        for name in ("tracked_allocator", "global_allocator", "owned_mutex", "owned_spinlock"):
            self.assertTrue(scope[name])
        for name in ("full_nvport_core", "existing_block_allocator", "fencepost_validation",
                     "per_allocation_size_query", "arbitrary_allocator_ownership_validation",
                     "interrupt_handlers", "DMA", "MMIO", "resource_manager", "GPU_initialization"):
            self.assertFalse(scope[name])


if __name__ == "__main__":
    unittest.main()
