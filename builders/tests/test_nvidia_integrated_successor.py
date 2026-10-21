"""Integration/refusal controls against an actual verified parent composition.

Run with S540_INTEGRATED_PARENT=/absolute/path/to/compose-check-public.
No native compiler, hardware access or CI request is used by these controls.
"""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import prepare_nvidia_integrated_successor as integrated


@unittest.skipUnless(os.environ.get('S540_INTEGRATED_PARENT'), 'actual composed parent required')
class IntegratedSuccessorControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='s540-integrated-controls-')
        cls.output = Path(cls.temporary.name)/'candidate'
        cls.parent = Path(os.environ['S540_INTEGRATED_PARENT'])
        cls.parent_digest = integrated.composer.sha(cls.parent/'composition.json')
        cls.value = integrated.prepare(cls.parent, cls.output)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def tearDown(self):
        integrated.composer.write_json(self.output/'composition.json', self.value)

    def changed_manifest(self, edit):
        value = copy.deepcopy(self.value)
        edit(value)
        integrated.composer.write_json(self.output/'composition.json', value)

    def test_actual_overlapping_record_and_sources_compose_once(self):
        actual = integrated.verify(self.output)
        record = self.output/'project'/integrated.RECORD
        text = record.read_text()
        self.assertEqual(text.count('NvBool s540FirstTxnGlobalRetainConstruction('), 1)
        self.assertEqual(text.count('NV_STATUS s540FirstTxnIrqBind('), 1)
        self.assertEqual(len(actual['project_translation_units']), 61)
        self.assertEqual(integrated.composer.sha(self.parent/'composition.json'), self.parent_digest)

    def test_runtime_admission_bit_refused(self):
        self.changed_manifest(lambda v: v['integrated_successor'].update(target_package_ready=True))
        with self.assertRaisesRegex(ValueError, 'cannot grant target_package_ready'):
            integrated.verify(self.output)

    def test_nested_source_profile_cannot_issue_stop_receipt(self):
        self.changed_manifest(lambda v: v['fixed_source_profiles'].update(stop_receipt_issued=True))
        with self.assertRaisesRegex(ValueError, 'cannot grant stop_receipt_issued'):
            integrated.verify(self.output)

    def test_duplicate_translation_unit_refused(self):
        self.changed_manifest(lambda v: v['project_translation_units'].append(v['project_translation_units'][0]))
        with self.assertRaisesRegex(ValueError, 'sixty parent units'):
            integrated.verify(self.output)

    def test_irq_compile_binding_refused(self):
        def edit(v):
            row = next(r for r in v['project_translation_units'] if r['source'] == integrated.IRQ_ORIGINAL)
            row['compile_definitions'].pop('S540_NVIDIA_IRQ_CALLBACK_CLOSURE')
        self.changed_manifest(edit)
        with self.assertRaisesRegex(ValueError, 'compile profile missing'):
            integrated.verify(self.output)

    def test_helper_hash_mismatch_refused(self):
        def edit(v):
            helpers = v['integrated_successor']['helper_source_sha256']
            helpers[next(iter(helpers))] = '0'*64
        self.changed_manifest(edit)
        with self.assertRaisesRegex(ValueError, 'Successor helper changed'):
            integrated.verify(self.output)

    def test_missing_helper_bindings_refused(self):
        self.changed_manifest(lambda v: v['integrated_successor'].update(helper_source_sha256={}))
        with self.assertRaisesRegex(ValueError, 'exact input bindings missing'):
            integrated.verify(self.output)

    def test_rehashed_runtime_gate_binding_cannot_replace_reviewed_gate(self):
        self.changed_manifest(lambda v: v['integrated_successor']['unchanged_runtime_gates'].update(
            {integrated.GATE_FILES[0]: '0'*64}))
        with self.assertRaisesRegex(ValueError, 'Exact runtime gate bindings required'):
            integrated.verify(self.output)

    def test_different_consistently_inventoried_parent_is_refused(self):
        with self.assertRaisesRegex(ValueError, 'exact reviewed closed parent'):
            integrated.verify_parent(self.output)

    def test_gate_edit_refused_even_with_updated_inventory(self):
        relative = integrated.GATE_FILES[0]
        path = self.output/'project'/relative
        before = path.read_bytes()
        try:
            path.write_bytes(before+b'\n/* altered gate */\n')
            def edit(v):
                v['project_files'][relative]['sha256'] = integrated.composer.sha(path)
                next(r for r in v['project_translation_units'] if r['source'] == relative)['sha256'] = integrated.composer.sha(path)
            self.changed_manifest(edit)
            with self.assertRaisesRegex(ValueError, 'runtime gate changed'):
                integrated.verify(self.output)
        finally:
            path.write_bytes(before)

    def test_source_mutation_refused(self):
        path = self.output/'project'/integrated.IRQ_ORIGINAL
        before = path.read_bytes()
        try:
            path.write_bytes(before+b'\n/* stale source */\n')
            with self.assertRaisesRegex(ValueError, 'inventory changed'):
                integrated.verify(self.output)
        finally:
            path.write_bytes(before)

    def test_output_cannot_overlap_parent(self):
        with self.assertRaisesRegex(ValueError, 'overlaps an input'):
            integrated.prepare(self.parent, self.parent/'integrated-successor')


if __name__ == '__main__':
    unittest.main()
