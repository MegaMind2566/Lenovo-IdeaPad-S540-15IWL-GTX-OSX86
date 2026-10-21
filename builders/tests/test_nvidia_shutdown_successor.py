#!/usr/bin/env python3
"""Controls for nested source replay, preserved gates and child object ownership."""
import copy
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import prepare_nvidia_shutdown_successor as candidate
import compile_nvidia_shutdown_successor as compiler


class SourcePlanTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.addCleanup(patch.stopall)
        patch.object(candidate, 'ROOT', self.root).start()
        self.base = self.root / 'base'
        (self.base / 'source').mkdir(parents=True)
        self.record = 'packages/record.c'
        files = {relative: 'immutable runtime gate ' + relative for relative in candidate.GATE_FILES}
        files.update({self.record: 'record: base\n', 'packages/old/include/Old.h': 'old header\n'})
        for relative, text in files.items():
            path = self.base / 'project' / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        (self.base / 'namespace.h').write_text('namespace: unchanged\n')
        self.before = dict(original_files={}, project_files=candidate.composer.inventory(self.base / 'project'),
            namespace='namespace.h', project_translation_units=[dict(source=self.record, kind='plain-c',
                sha256=candidate.composer.sha(self.base / 'project' / self.record))],
            operational_successor={'status': 'historical-base-evidence', 'changes': [],
                'selected_profiles': ['global-result', 'irq-installation', 'rc-dispatch', 'allocator-stack'],
                'include_directories': ['packages/old/include'], 'new_project_exports': {'historical': 'old.c'}},
            fixed_source_profiles=dict(original_entry_admission=False, hardware_admission=False,
                final_release_issued=False, stop_receipt_issued=False, exact_source_replacements=[],
                additional_project_exports={}, source_row_requirements={}, per_source_compile_definitions={}))

    def module(self, inputs=(), transform=None, **extra):
        here = self.root / 'packages/new' / ('module-' + str(len(list((self.root / 'packages/new').glob('*')))))
        here.mkdir(parents=True)
        return SimpleNamespace(HERE=here, INPUTS=inputs,
            transforms=transform if transform is not None else lambda values: values, **extra)

    def plan(self, modules):
        return candidate.build_plan(self.base, self.before, tuple(modules), modules, {'prepare.py': 'bound'})

    def test_selection_is_explicit_unique_ordered_and_dependency_checked(self):
        self.assertEqual(candidate.selected_profiles(['dma-producer', 'pm-revocation', 'stack-context']),
            ('stack-context', 'pm-revocation', 'dma-producer'))
        for invalid in ([], ['unknown'], ['stack-context', 'stack-context'], ['dma-producer']):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                candidate.selected_profiles(invalid)

    def test_unproved_whole_dma_and_missing_pm_refuse_before_any_base_io(self):
        for profiles in (['dma-containment'], ['dma-producer']):
            with self.subTest(profiles=profiles), patch.object(candidate, 'verify_base',
                    side_effect=AssertionError('base must not be read')):
                with self.assertRaises(ValueError):
                    candidate.prepare(Path('/missing'), Path('/missing'), Path('/missing'),
                                      Path('/must-not-exist'), profiles)

    def test_overlapping_edits_preserve_parent_and_historical_record(self):
        modules = {
            'stack-context': self.module((self.record,), lambda v: {k: t + 'stack\n' for k, t in v.items()}),
            'pm-revocation': self.module((self.record,), lambda v: {k: t + 'pm\n' for k, t in v.items()})}
        original = copy.deepcopy(self.before)
        value, replay = self.plan(modules)
        self.assertEqual(replay.current('project', self.record), 'record: base\nstack\npm\n')
        self.assertEqual(replay.edits[1]['input_sha256'], replay.edits[0]['output_sha256'])
        self.assertEqual(self.before, original)
        self.assertEqual(value['operational_successor'], original['operational_successor'])
        self.assertEqual((self.base / 'project' / self.record).read_text(), 'record: base\n')
        for key, denied in candidate.DENIED.items():
            self.assertEqual(value['shutdown_successor'][key], denied)

    def test_whole_global_loader_and_bootstrap_files_are_immutable(self):
        for relative in candidate.GATE_FILES:
            with self.subTest(relative=relative), self.assertRaisesRegex(ValueError, 'runtime gates are immutable'):
                self.plan({'pm-revocation': self.module((relative,))})

    def test_transform_cannot_read_outside_authenticated_inventory(self):
        module = self.module(('packages/absent.c',), lambda _: self.fail('transform must not run'))
        with self.assertRaisesRegex(ValueError, 'absent from the authenticated'):
            self.plan({'stack-context': module})

    def test_companions_cannot_replace_or_escape_their_namespace(self):
        module = self.module()
        source = module.HERE / 'new.h'
        source.write_text('new header\n')
        module.COMPANIONS = {self.record: source}
        with self.assertRaisesRegex(ValueError, 'owning module namespace'):
            self.plan({'pm-revocation': module})
        relative = source.relative_to(self.root).as_posix()
        path = self.base / 'project' / relative
        path.parent.mkdir(parents=True)
        path.write_text('pre-existing source\n')
        self.before['project_files'] = candidate.composer.inventory(self.base / 'project')
        module.COMPANIONS = {relative: source}
        with self.assertRaisesRegex(ValueError, 'existing authenticated file'):
            self.plan({'pm-revocation': module})

    def test_inherited_include_dirs_remain_bound_without_relabeling_old_record(self):
        module = self.module()
        header = module.HERE / 'New.h'
        header.write_text('new header\n')
        relative = header.relative_to(self.root).as_posix()
        directory = module.HERE.relative_to(self.root).as_posix()
        module.COMPANIONS = {relative: header}
        module.INCLUDE_DIRECTORIES = (directory,)
        value, _ = self.plan({'pm-revocation': module})
        self.assertEqual(value['shutdown_successor']['inherited_include_directories'], ['packages/old/include'])
        self.assertEqual(value['shutdown_successor']['include_directories'], ['packages/old/include', directory])
        self.assertEqual(value['operational_successor']['include_directories'], ['packages/old/include'])
        flags = compiler.include_flags(value, Path('/candidate'))
        self.assertIn('/candidate/project/packages/old/include', flags)
        self.assertIn('/candidate/project/' + directory, flags)

    def test_new_unit_export_macro_and_original_export_have_exact_scopes(self):
        original = 'src/original.c'
        path = self.base / 'source' / original
        path.parent.mkdir(parents=True)
        path.write_text('original body\n')
        self.before['original_files'] = candidate.composer.inventory(self.base / 'source')
        module = self.module(ORIGINAL_INPUTS=(original,), original_transforms=lambda values: {
            name: text + 'status body\n' for name, text in values.items()})
        source = module.HERE / 'epoch.c'
        source.write_text('int epoch(void) { return 0; }\n')
        relative = source.relative_to(self.root).as_posix()
        module.COMPANIONS = {relative: source}
        module.PROJECT_UNITS = ({'source': relative, 'kind': 'plain-c'},)
        module.EXPORTS = {relative: ('epoch',), original: ('s540Global_status',)}
        module.COMPILE_DEFINITIONS = {relative: {'S540_EPOCH': '1'}}
        value, _ = self.plan({'pm-revocation': module})
        self.assertEqual(value['shutdown_successor']['new_project_exports'], {'epoch': relative})
        self.assertEqual(value['shutdown_successor']['new_original_exports'], {'s540Global_status': original})
        row = next(row for row in value['project_translation_units'] if row['source'] == relative)
        self.assertEqual(row['compile_definitions'], {'S540_EPOCH': '1'})
        self.assertEqual(value['fixed_source_profiles']['additional_private_original_exports'],
                         {'s540Global_status': original})

    def test_parent_or_sibling_export_collision_is_refused(self):
        self.before['fixed_source_profiles']['additional_project_exports']['existing'] = self.record
        with self.assertRaisesRegex(ValueError, 'Duplicate or invalid'):
            self.plan({'pm-revocation': self.module(EXPORTS={self.record: ('existing',)})})
        a = self.module(EXPORTS={self.record: ('newCommit',)})
        b = self.module(EXPORTS={self.record: ('newCommit',)})
        with self.assertRaisesRegex(ValueError, 'Duplicate or invalid'):
            self.plan({'stack-context': a, 'pm-revocation': b})

    def test_wrong_base_sha_refuses_before_ancestor_replay(self):
        (self.base / 'composition.json').write_text('{}')
        with patch.object(candidate.operational, 'verify_plan', side_effect=AssertionError('must not replay')):
            with self.assertRaisesRegex(ValueError, 'operational-successor-2'):
                candidate.verify_base(self.base, self.base, self.base)

    def test_complete_manifest_replay_rejects_changed_historical_record(self):
        modules = {'stack-context': self.module((self.record,),
            lambda v: {k: t + 'stack\n' for k, t in v.items()})}
        value, replay = self.plan(modules)
        output = self.root / 'candidate'
        output.mkdir()
        for scope in ('project', 'source'):
            shutil.copytree(self.base / scope, output / scope)
        shutil.copyfile(self.base / 'namespace.h', output / 'namespace.h')
        for (scope, relative), text in replay.overlays.items():
            (output / scope / relative).write_text(text)
        bad = copy.deepcopy(value)
        bad['operational_successor']['status'] = 'misleading-current-proof'
        with patch.object(candidate, 'verify_base', return_value=self.before), \
             patch.object(candidate.composer, 'verify_composition', return_value=bad), \
             patch.object(candidate, 'modules_for', return_value=modules), \
             patch.object(candidate, 'helper_hashes', return_value={'prepare.py': 'bound'}):
            with self.assertRaisesRegex(ValueError, 'complete selected-profile replay'):
                candidate.verify_plan(self.base, self.base, self.base, output)


class CompiledOwnerAndDeltaTests(unittest.TestCase):
    def values(self, project=None, original=None):
        project, original = project or {}, original or {}
        before = {'fixed_source_profiles': {'additional_project_exports': {}, 'additional_private_original_exports': {}}}
        value = {'fixed_source_profiles': {'additional_project_exports': project,
            'additional_private_original_exports': original}, 'operational_successor': {'new_project_exports': {'stale': 'old.c'}},
            'shutdown_successor': {'new_project_exports': project, 'new_original_exports': original}}
        return before, value

    def test_new_owner_requires_actual_exact_strong_object_in_correct_scope(self):
        before, value = self.values({'newCommit': 'commit.c'})
        row = {'source': 'commit.c', 'object': 'commit.o', 'definitions': ['newCommit']}
        with patch.object(compiler.previous, 'project_definition_strength', return_value={'newCommit': 'strong'}):
            self.assertEqual(compiler.export_owners(before, value, [('project', [row], Path('/objects'))]),
                             {'project': {'newCommit': 'commit.c'}, 'source': {}})
        for strength, scope in (('weak', 'project'), ('strong', 'source')):
            with self.subTest(strength=strength, scope=scope), patch.object(compiler.previous,
                    'project_definition_strength', return_value={'newCommit': strength}):
                with self.assertRaisesRegex(ValueError, 'sole declared strong owner'):
                    compiler.export_owners(before, value, [(scope, [row], Path('/objects'))])

    def test_original_new_owner_requires_original_object(self):
        before, value = self.values(original={'s540Global_status': 'original.c'})
        row = {'source': 'original.c', 'object': 'original.o', 'definitions': ['s540Global_status']}
        with patch.object(compiler.previous, 'project_definition_strength', return_value={'s540Global_status': 'strong'}):
            self.assertEqual(compiler.export_owners(before, value, [('source', [row], Path('/objects'))]),
                             {'project': {}, 'source': {'s540Global_status': 'original.c'}})
            with self.assertRaisesRegex(ValueError, 'original export lacks'):
                compiler.export_owners(before, value, [('project', [row], Path('/objects'))])

    def test_duplicate_actual_strong_symbols_are_not_silently_overwritten(self):
        before, value = self.values()
        rows = [{'source': source, 'object': source + '.o', 'definitions': ['collision']}
                for source in ('one.c', 'two.c')]
        with patch.object(compiler.previous, 'project_definition_strength', return_value={'collision': 'strong'}):
            with self.assertRaisesRegex(ValueError, 'Duplicate strong'):
                compiler.export_owners(before, value, [('project', rows, Path('/objects'))])

    def test_original_subset_excludes_historical_parent_edits_and_records_headers(self):
        value = {'original_files': {'src/new.c': {}, 'inc/new.h': {}, 'src/old.c': {}},
            'operational_successor': {'changes': [{'scope': 'source', 'source': 'src/old.c'}]},
            'shutdown_successor': {'changes': [{'scope': 'project', 'source': 'packages/commit.c'},
                {'scope': 'source', 'source': 'src/new.c'}, {'scope': 'source', 'source': 'inc/new.h'}]}}
        self.assertEqual(compiler.original_delta_sources(value), ({'src/new.c'}, ['inc/new.h']))
        value['shutdown_successor']['changes'][1]['source'] = 'src/undeclared.c'
        with self.assertRaisesRegex(ValueError, 'declared C'):
            compiler.original_delta_sources(value)


if __name__ == '__main__':
    unittest.main()
