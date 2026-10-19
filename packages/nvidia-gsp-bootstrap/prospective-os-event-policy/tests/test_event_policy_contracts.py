#!/usr/bin/env python3
"""Source/composition invariants for an unavailable OS-event feature profile."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
from prepare_event_policy import FUNCTIONS, SOURCES, V3_TREE, function, prepare
V3 = None
UPSTREAM = None

class EventPolicyContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.contract = json.loads((HERE / 'OS-EVENT-POLICY-CONTRACTS.json').read_text())
    def test_exact_candidate_sources(self):
        for name, expected in self.contract['source_sha256'].items():
            self.assertEqual(hashlib.sha256((HERE / name).read_bytes()).hexdigest(), expected, name)
    def test_exact_original_sources(self):
        self.assertEqual(self.contract['base_sources_sha256'], SOURCES)
        if UPSTREAM:
            for name, expected in self.contract['supporting_original_source_sha256'].items():
                self.assertEqual(hashlib.sha256((UPSTREAM / name).read_bytes()).hexdigest(), expected, name)
    def test_reproduces_exact_frozen_v3_composition(self):
        if not V3: self.skipTest('Frozen V3 output required')
        with tempfile.TemporaryDirectory() as tmp:
            result = prepare(V3 / 'source', Path(tmp))
            self.assertEqual(result['base_v3_tree_sha256'], V3_TREE)
            self.assertEqual(result['composed_tree_sha256'], self.contract['composed_tree_sha256'])
            self.assertEqual(result['proposed_source_sha256'], self.contract['proposed_source_sha256'])
            self.assertEqual(result['additions_patch_sha256'], self.contract['additions_patch_sha256'])
            self.assertEqual((Path(tmp) / 'os-event-additions-to-v3.patch').read_bytes(),
                (HERE / 'os-event-additions-to-v3.patch').read_bytes())
    def test_wrong_base_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / 'base'; base.mkdir()
            with self.assertRaisesRegex(ValueError, 'exact frozen V3'):
                prepare(base, Path(tmp) / 'out')
    def test_guards_precede_os_resources_and_output_writes(self):
        if not V3: self.skipTest('Frozen V3 output required')
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp); prepare(V3 / 'source', out)
            for name, relative in FUNCTIONS.items():
                text = (out / 'source' / relative).read_text()
                body = function(text, name)[2]
                guard = body.index('return NV_ERR_NOT_SUPPORTED;')
                boundary = ('_eventRpcForType(' if name.startswith('eventapi') else
                    'pRmClient = dynamicCast(' if name.startswith('eventbuffer') else
                    'rmStatus = osUserHandleToKernelPtr(')
                self.assertLess(guard, body.index(boundary))
                if name.startswith('eventbuffer'):
                    self.assertLess(guard, body.index('pAllocParams->bufferHeader  = NvP64_NULL;'))
    def test_real_importer_kernel_callback_and_zero_public_handle_preserved(self):
        if not V3: self.skipTest('Frozen V3 output required')
        text = (V3 / 'source/src/nvidia/src/kernel/gpu/gpu_op_event_import.c').read_text()
        callback = function(text, '_goeimportAllocCallbackEvent')[2]
        buffer = function(text, '_goeimportAllocEventBuffer')[2]
        self.assertIn('eventParams.hClass        = NV01_EVENT_KERNEL_CALLBACK_EX;', callback)
        self.assertIn('eventParams.data          = NV_PTR_TO_NvP64(&pImporter->callback);', callback)
        self.assertIn('bufParams.notificationHandle   = 0;', buffer)
        self.assertFalse(self.contract['gpu_op_event_import_source_changed'])
    def test_nvoc_outer_allocation_failure_cleanup_is_explicit(self):
        if not V3: self.skipTest('Frozen V3 output required')
        for name in ('EventApi', 'EventBuffer'):
            relative = 'src/nvidia/generated/g_' + ('event_api' if name == 'EventApi' else 'event_buffer') + '_nvoc.c'
            text = (V3 / 'source' / relative).read_text()
            body = function(text, '__nvoc_objCreate_' + name)[2]
            self.assertIn('portMemAllocNonPaged(sizeof(' + name + '))', body)
            self.assertIn('portMemFree(__nvoc_pThis);', body)
            self.assertIn('*__nvoc_ppThis = NULL;', body)
            self.assertFalse(self.contract['constructor_guard_prevents_outer_nvoc_object_allocation'])
    def test_no_production_inclusion_or_fake_callback_claim(self):
        sys.path.insert(0, str(ROOT / 'builders'))
        import build_nvidia_execution
        sources = [p for group in build_nvidia_execution.project_sources() for p in group]
        self.assertFalse(any(p.is_relative_to(HERE) for p in sources))
        self.assertFalse(self.contract['original_callbacks_implemented'])
        self.assertFalse(self.contract['whole_bootstrap_exclusion_proven'])
        self.assertFalse(self.contract['production_candidate_allowed'])

if __name__ == '__main__':
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--upstream', type=Path); parser.add_argument('--v3-output', type=Path)
    args, rest = parser.parse_known_args(); UPSTREAM = args.upstream; V3 = args.v3_output
    unittest.main(argv=[sys.argv[0], *rest])
