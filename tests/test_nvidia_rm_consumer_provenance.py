#!/usr/bin/env python3
"""Verify original RM containers and the single documented vector bug fix."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'packages/nvidia-nvport-runtime'
UPSTREAM = SOURCE / 'upstream/consumer'
COMMIT = '1a82fbfda8f321b056eb3568850f9316c5e465c5'
PINNED = json.loads("{\"list.c\":[\"src/nvidia/src/libraries/containers/list.c\",\"4f5155b7be4b6da05d077b7f1100ae082054d916\"],\"reference/vector.c\":[\"src/nvidia/src/libraries/containers/vector.c\",\"82af7c7a585fe0becc69323ec9412531d9689672\"],\"include/containers/vector.h\":[\"src/nvidia/inc/libraries/containers/vector.h\",\"6554e5d56ef4875360721e8c78ad169327645ba4\"],\"include/containers/list.h\":[\"src/nvidia/inc/libraries/containers/list.h\",\"629f33c3c857e8e006054b2e998018c1dcedcf88\"],\"include/containers/type_safety.h\":[\"src/nvidia/inc/libraries/containers/type_safety.h\",\"90a9afa9abfc7646f4ac8a829a67f74abd187b55\"],\"reference/nvassert.h\":[\"src/nvidia/inc/libraries/utils/nvassert.h\",\"b1a8b2d8763e7542b8802a091862116e3664ea6e\"],\"reference/rs_client.c\":[\"src/nvidia/src/libraries/resserv/src/rs_client.c\",\"0fa885c984f806703b927eb4c61db3f82020d8a8\"]}")

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

class NvidiaRmConsumerProvenance(unittest.TestCase):
    def setUp(self) -> None:
        self.report = json.loads((UPSTREAM / 'PROVENANCE.json').read_text())

    def test_pinned_original_sources(self) -> None:
        self.assertEqual(self.report['commit'], COMMIT)
        self.assertEqual(self.report['release'], '615.78.08')
        self.assertEqual({item['path'] for item in self.report['upstream_files']}, set(PINNED))
        for item in self.report['upstream_files']:
            path = UPSTREAM / item['path']
            self.assertFalse(path.is_symlink())
            data = path.read_bytes()
            self.assertEqual([item['source_path'], item['git_blob_sha1']], PINNED[item['path']])
            blob = b'blob ' + str(len(data)).encode() + b'\0' + data
            self.assertEqual(hashlib.sha1(blob).hexdigest(), item['git_blob_sha1'])
            self.assertEqual(sha(data), item['sha256'])
            self.assertEqual(len(data), item['bytes'])
            self.assertFalse(item['modified'])
            self.assertIn(b'Permission is hereby granted', data)

    def test_exact_single_vector_fix(self) -> None:
        original = (UPSTREAM / 'reference/vector.c').read_text()
        old = '        PORT_FREE(pVector->pAllocator, pVector->pHead);\n        pNewArray = pCopiedArray;\n    }\n\n    pVector->pHead'
        fixed = '        pNewArray = pCopiedArray;\n    }\n\n    PORT_FREE(pVector->pAllocator, pVector->pHead);\n    pVector->pHead'
        self.assertEqual(original.count(old), 1)
        compiled = (UPSTREAM / 'vector.c').read_text()
        self.assertEqual(compiled, original.replace(old, fixed, 1))
        unit = self.report['adapted_translation_unit']
        self.assertEqual(unit['path'], 'vector.c')
        self.assertEqual(unit['source_reference'], 'reference/vector.c')
        self.assertEqual(unit['changed_function'], '_vectReallocHelper')
        self.assertEqual(unit['sha256'], sha(compiled.encode()))

    def test_real_rm_call_sites(self) -> None:
        list_source = (UPSTREAM / 'reference/rs_client.c').read_text()
        calls = self.report['rm_call_sites']
        self.assertEqual(calls[0]['source_path'], PINNED['reference/rs_client.c'][0])
        self.assertIn(calls[0]['expression'], list_source)
        self.assertEqual(calls[1]['source_path'], 'src/nvidia/src/kernel/gpu/intr/intr.c')
        self.assertEqual(calls[1]['git_blob_sha1'], '16010bfe9194fee3e286eefedec22681f8f26f87')
        self.assertEqual(calls[1]['line'], 776)
        self.assertIn('vectInit(&pIntr->intrTable', calls[1]['expression'])

    def test_explicit_profile_bridges(self) -> None:
        for item in self.report['interfaces']:
            self.assertEqual(sha((UPSTREAM / item['path']).read_bytes()), item['sha256'])
        profile = (UPSTREAM / 'include/nvport/nvport.h').read_text()
        asserts = (UPSTREAM / 'include/utils/nvassert.h').read_text()
        self.assertIn('#define PORT_IS_CHECKED_BUILD 0', profile)
        self.assertIn('nvport_lifecycle.h', profile)
        self.assertIn('s540NvidiaCallerAssertionFailed', asserts)
        self.assertIn('portDbgPrintf', asserts)
        self.assertIn('return (value)', asserts)
        self.assertNotIn('return NV_OK', asserts)

    def test_production_owns_no_global_lifecycle(self) -> None:
        compiled = (SOURCE / 'src/S540NvidiaRmConsumer.cpp').read_text()
        self.assertNotIn('s540NvportMemoryInitialize(', compiled)
        self.assertNotIn('portMemShutdown(', compiled)
        self.assertIn('s540NvportMemoryIsInitialized()', compiled)
        self.assertIn('portMemExTrackingGetActiveStats', compiled)
        self.assertIn('vectReserve_IMPL(&vector, 32)', compiled)
        self.assertIn('vectTrim_IMPL(&vector, 0)', compiled)
        self.assertIn('vector.pHead == head && vector.capacity == 2 && vector.size == 0', compiled)
        self.assertIn('listAppendValue_IMPL(&list, &retained[1]) == nullptr', compiled)
        self.assertIn('PORT_FREE(allocator, memory)', compiled)
        self.assertNotRegex(compiled, r'(?i)IOMap|IOMemory|pciRead|pciWrite|BAR0|DMA')
        bounds = self.report['bounds']
        self.assertEqual(bounds['element_bytes'], 4)
        self.assertEqual(bounds['production_vector_max_capacity'], 32)
        self.assertLess(bounds['native_vector_max_capacity'] * bounds['element_bytes'],
                        bounds['reserve_slot_bytes'])

    def test_native_failure_and_stress_are_not_kernel_claims(self) -> None:
        native = (SOURCE / 'tests/check_rm_consumer_native.cpp').read_text()
        self.assertIn('allocator->_portAlloc = failNth', native)
        self.assertIn('allocator->_portAlloc = originalAllocate', native)
        self.assertIn('failureAttempt <= 12', native)
        self.assertIn('cycle < 64', native)
        self.assertIn('step < 128', native)
        self.assertIn('native-user-space', native)
        self.assertIn('not_tested', native)
        scope = self.report['scope']
        self.assertTrue(scope['real_original_containers'])
        self.assertTrue(scope['real_tracked_allocator'])
        for key in ('full_resource_manager', 'gpu_access', 'thread_safe_containers',
                    'checked_capacity_arithmetic', 'self_insert_alias_support'):
            self.assertFalse(scope[key])

if __name__ == '__main__':
    unittest.main()
