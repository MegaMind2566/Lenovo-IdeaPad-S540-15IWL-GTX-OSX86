#!/usr/bin/env python3
"""Local controls for operational composition ordering and closed boundaries."""
import copy
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import prepare_nvidia_operational_successor as candidate
import compile_nvidia_operational_successor as compiler


class SourcePlanTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.base = self.root / 'base'
        (self.base / 'source').mkdir(parents=True)
        self.record = 'packages/record.c'
        self.lifecycle = ('NV_STATUS s540GlobalRmInitialize(void)\n{\n'
            '#if defined(KERNEL)\n    return NV_ERR_NOT_READY;\n#endif\n'
            '    status=coreInitializeRm();\n    return status;\n}\n')
        files = {candidate.LIFECYCLE: self.lifecycle, candidate.LOADER_GATE: 'loader: closed\n',
                 candidate.BOOT: candidate.integrated.REFUSAL, self.record: 'record: base\n'}
        for relative, text in files.items():
            path = self.base / 'project' / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        self.before = dict(original_files={}, project_files=candidate.composer.inventory(self.base / 'project'),
            project_translation_units=[dict(source=self.record, kind='plain-c',
                sha256=candidate.composer.sha(self.base / 'project' / self.record))],
            fixed_source_profiles=dict(original_entry_admission=False, hardware_admission=False,
                final_release_issued=False, stop_receipt_issued=False, exact_source_replacements=[],
                additional_project_exports={}, source_row_requirements={}, per_source_compile_definitions={}))

    def module(self, inputs=(), transform=None, **extra):
        here = self.root / ('module-' + str(len(list(self.root.glob('module-*')))))
        here.mkdir()
        return SimpleNamespace(HERE=here, INPUTS=inputs,
            transforms=transform if transform is not None else lambda values: values, **extra)

    def plan(self, modules):
        return candidate.build_plan(self.base, self.before, tuple(modules), modules, {'prepare.py': 'bound'})

    def test_profiles_are_explicit_unique_and_ordered(self):
        self.assertEqual(candidate.selected_profiles(['allocator-stack', 'global-result']),
                         ('global-result', 'allocator-stack'))
        self.assertEqual(candidate.selected_profiles(['rc-dispatch', 'irq-installation']),
                         ('irq-installation', 'rc-dispatch'))
        for invalid in ([], ['unknown'], ['global-result', 'global-result']):
            with self.assertRaises(ValueError):
                candidate.selected_profiles(invalid)

    def test_blocked_dma_profile_refused_before_any_input_or_output_work(self):
        self.assertNotIn('dma-containment', candidate.PROFILE_DIRECTORIES)
        with patch.object(candidate, 'verify_base', side_effect=AssertionError('base must not be touched')):
            with self.assertRaisesRegex(ValueError, 'BAR0 BME writer bypass'):
                candidate.prepare(Path('/missing-parent'), Path('/missing-base'),
                                  Path('/must-not-be-created'), ['dma-containment'])

    def test_overlapping_profiles_replay_once_and_preserve_parent(self):
        modules = {
            'irq-installation': self.module((self.record,), lambda v: {k: t + 'irq\n' for k, t in v.items()}),
            'rc-dispatch': self.module((self.record,), lambda v: {k: t + 'rc\n' for k, t in v.items()})}
        original = copy.deepcopy(self.before)
        value, replay = self.plan(modules)
        self.assertEqual(replay.current('project', self.record), 'record: base\nirq\nrc\n')
        self.assertEqual(replay.edits[1]['input_sha256'], replay.edits[0]['output_sha256'])
        self.assertEqual(self.before, original)
        self.assertEqual((self.base / 'project' / self.record).read_text(), 'record: base\n')
        for key, denied in candidate.DENIED.items():
            self.assertEqual(value['operational_successor'][key], denied)

    def test_exact_result_change_after_core_keeps_refusal_prefix(self):
        module = self.module((candidate.LIFECYCLE,), lambda values: {
            key: text.replace('    return status;', '    return out->startupStatus=status;')
            for key, text in values.items()})
        _, replay = self.plan({'global-result': module})
        candidate.lifecycle_guard(self.lifecycle, replay.current('project', candidate.LIFECYCLE))

    def test_global_kernel_refusal_cannot_change(self):
        module = self.module((candidate.LIFECYCLE,), lambda values: {
            key: text.replace('return NV_ERR_NOT_READY;', 'return NV_OK;') for key, text in values.items()})
        with self.assertRaisesRegex(ValueError, 'pre-original'):
            self.plan({'global-result': module})

    def test_other_profile_cannot_claim_lifecycle_or_loader_gate(self):
        for relative in (candidate.LIFECYCLE, candidate.LOADER_GATE):
            with self.subTest(relative=relative), self.assertRaises(ValueError):
                self.plan({'irq-installation': self.module((relative,))})

    def test_new_unit_companion_export_and_macro_have_exact_bindings(self):
        module = self.module()
        (module.HERE / 'epoch.c').write_text('int epoch(void) { return 0; }\n')
        source = 'packages/allocator/epoch.c'
        module.COMPANIONS = {source: module.HERE / 'epoch.c'}
        module.PROJECT_UNITS = ({'source': source, 'kind': 'plain-c'},)
        module.EXPORTS = {source: ('epoch',)}
        module.COMPILE_DEFINITIONS = {source: {'S540_EPOCH': '1'}}
        module.INCLUDE_DIRECTORIES = ('packages/allocator',)
        value, _ = self.plan({'allocator-stack': module})
        row = next(row for row in value['project_translation_units'] if row['source'] == source)
        self.assertEqual(row['compile_definitions'], {'S540_EPOCH': '1'})
        self.assertEqual(value['operational_successor']['new_project_exports'], {'epoch': source})
        self.assertEqual(value['fixed_source_profiles']['additional_project_exports'], {'epoch': source})
        self.assertEqual(value['operational_successor']['include_directories'], ['packages/allocator'])

    def test_duplicate_exports_are_refused(self):
        a = self.module(EXPORTS={self.record: ('owner',)})
        b = self.module(EXPORTS={self.record: ('owner',)})
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            self.plan({'irq-installation': a, 'rc-dispatch': b})

    def test_companion_cannot_replace_gate(self):
        module = self.module()
        p = module.HERE / 'gate.c'
        p.write_text('opened')
        module.COMPANIONS = {candidate.LIFECYCLE: p}
        with self.assertRaisesRegex(ValueError, 'runtime gate'):
            self.plan({'irq-installation': module})

    def test_private_original_export_is_recorded_in_its_own_scope(self):
        original = 'src/original.c'
        path = self.base / 'source' / original
        path.parent.mkdir(parents=True)
        path.write_text('original body\n')
        self.before['original_files'] = candidate.composer.inventory(self.base / 'source')
        module = self.module(ORIGINAL_INPUTS=(original,), original_transforms=lambda values: {
            name: text + 'new status body\n' for name, text in values.items()},
            EXPORTS={original: ('s540Global_newStatus',)})
        value, _ = self.plan({'rc-dispatch': module})
        self.assertEqual(value['operational_successor']['new_original_exports'], {'s540Global_newStatus': original})
        self.assertEqual(value['operational_successor']['new_project_exports'], {})
        self.assertEqual(value['fixed_source_profiles']['additional_private_original_exports'],
                         {'s540Global_newStatus': original})

    def test_wrong_base_digest_is_refused_before_old_verifiers(self):
        (self.base / 'composition.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'integrated-successor-5'):
            candidate.verify_base(self.base, self.base)


class ActualOwnerPolicyTests(unittest.TestCase):
    def test_new_symbol_requires_exact_sole_strong_project_owner(self):
        before = {'fixed_source_profiles': {'additional_project_exports': {}}}
        value = {'fixed_source_profiles': {'additional_project_exports': {'newEpoch': 'epoch.c'}},
                 'operational_successor': {'new_project_exports': {'newEpoch': 'epoch.c'}}}
        row = {'source': 'epoch.c', 'object': 'epoch.o', 'definitions': ['newEpoch']}
        with patch.object(compiler.previous, 'project_definition_strength', return_value={'newEpoch': 'strong'}):
            self.assertEqual(compiler.export_owners(before, value, [('project', [row], Path('/objects'))]),
                             {'project': {'newEpoch': 'epoch.c'}, 'source': {}})
        for strength, scope in (('weak', 'project'), ('strong', 'source')):
            with self.subTest(strength=strength, scope=scope), patch.object(
                    compiler.previous, 'project_definition_strength', return_value={'newEpoch': strength}):
                with self.assertRaisesRegex(ValueError, 'sole declared strong owner'):
                    compiler.export_owners(before, value, [(scope, [row], Path('/objects'))])

    def test_duplicate_strong_compiled_symbol_is_refused(self):
        before = {'fixed_source_profiles': {'additional_project_exports': {}}}
        value = {'fixed_source_profiles': {'additional_project_exports': {}},
                 'operational_successor': {'new_project_exports': {}}}
        rows = [{'source': name, 'object': name + '.o', 'definitions': ['collision']} for name in ('a.c', 'b.c')]
        with patch.object(compiler.previous, 'project_definition_strength', return_value={'collision': 'strong'}):
            with self.assertRaisesRegex(ValueError, 'Duplicate strong'):
                compiler.export_owners(before, value, [('project', rows, Path('/objects'))])

    def test_original_new_symbol_requires_actual_source_object(self):
        before = {'fixed_source_profiles': {'additional_project_exports': {}, 'additional_private_original_exports': {}}}
        value = {'fixed_source_profiles': {'additional_project_exports': {},
            'additional_private_original_exports': {'s540Global_status': 'original.c'}},
            'operational_successor': {'new_project_exports': {}, 'new_original_exports': {'s540Global_status': 'original.c'}}}
        row = {'source': 'original.c', 'object': 'original.o', 'definitions': ['s540Global_status']}
        with patch.object(compiler.previous, 'project_definition_strength', return_value={'s540Global_status': 'strong'}):
            self.assertEqual(compiler.export_owners(before, value, [('source', [row], Path('/objects'))]),
                             {'project': {}, 'source': {'s540Global_status': 'original.c'}})
            with self.assertRaisesRegex(ValueError, 'original export lacks'):
                compiler.export_owners(before, value, [('project', [row], Path('/objects'))])


if __name__ == '__main__':
    unittest.main()
