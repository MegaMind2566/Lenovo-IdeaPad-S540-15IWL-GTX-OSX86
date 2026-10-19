#!/usr/bin/env python3
"""Integrity/refusal checks for exact source composition; no RM/GPU fixtures."""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'builders'))
import compose_nvidia_first_transaction as compose


class CompositionIntegrity(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()

    def tearDown(self):
        self.temporary.cleanup()

    def fixture(self):
        (self.root / 'source').mkdir()
        (self.root / 'project').mkdir()
        (self.root / 'source/one.c').write_text('int one;\n')
        (self.root / 'project/port.c').write_text('int port;\n')
        (self.root / 'namespace.h').write_text('#define one private_one\n')
        value = {'format': 1, 'status': 'materialized-source-only',
            'original_entry_admission': False, 'production_candidate_allowed': False,
            'hardware_admission': False, 'kernel_execution': 'not_tested', 'gpu_access': False,
            'original_files': compose.inventory(self.root / 'source'),
            'project_files': compose.inventory(self.root / 'project'),
            'namespace': 'namespace.h', 'namespace_sha256': compose.sha(self.root / 'namespace.h')}
        compose.write_json(self.root / 'composition.json', value)
        return value

    def test_original_and_project_inventory_are_independently_sealed(self):
        value = self.fixture()
        self.assertEqual(compose.verify_composition(self.root), value)
        (self.root / 'project/extra.c').write_text('int extra;\n')
        with self.assertRaisesRegex(ValueError, 'project'):
            compose.verify_composition(self.root)

    def test_same_count_original_substitution_is_detected(self):
        self.fixture()
        (self.root / 'source/one.c').write_text('int replacement;\n')
        with self.assertRaisesRegex(ValueError, 'source'):
            compose.verify_composition(self.root)

    def test_namespace_rebinding_is_detected(self):
        self.fixture()
        (self.root / 'namespace.h').write_text('#define one foreign_one\n')
        with self.assertRaisesRegex(ValueError, 'namespace'):
            compose.verify_composition(self.root)

    def test_source_profile_cannot_grant_runtime_admission(self):
        value = self.fixture()
        value['original_entry_admission'] = True
        compose.write_json(self.root / 'composition.json', value)
        with self.assertRaisesRegex(ValueError, 'runtime admission'):
            compose.verify_composition(self.root)

    def test_symlink_cannot_hide_out_of_tree_source(self):
        self.fixture()
        (self.root / 'source/link.c').symlink_to(self.root / 'project/port.c')
        with self.assertRaisesRegex(ValueError, 'symlink'):
            compose.inventory(self.root / 'source')

    def test_output_cannot_replace_input_or_reuse_existing_workspace(self):
        self.fixture()
        with self.assertRaisesRegex(ValueError, 'overlaps'):
            compose.new_output(self.root / 'source/out', [self.root / 'source'])
        with self.assertRaisesRegex(ValueError, 'fresh'):
            compose.new_output(self.root / 'project', [self.root / 'source'])

    def test_inventory_traversal_and_absolute_paths_are_refused(self):
        for path in ['../escape.c', '/tmp/foreign.c', '.', 'a/../../escape.c']:
            with self.subTest(path=path), self.assertRaises(ValueError):
                compose.checked_relative(path)

    def test_successor_rejects_all_changes_before_writing_any(self):
        self.fixture()
        (self.root / 'replacement.c').write_text('int replacement;\n')
        original = (self.root / 'source/one.c').read_bytes()
        manifest = {'format': 1, 'sources': {
            'one.c': {'input_sha256': compose.sha(self.root / 'source/one.c'),
                'output_sha256': compose.sha(self.root / 'replacement.c'), 'source': 'replacement.c'},
            'z-missing.c': {'input_sha256': '0' * 64, 'output_sha256': '0' * 64, 'source': 'replacement.c'}}}
        compose.write_json(self.root / 'successor.json', manifest)
        with self.assertRaises((ValueError, FileNotFoundError)):
            compose.apply_exact_successor(self.root / 'source', self.root / 'successor.json')
        self.assertEqual((self.root / 'source/one.c').read_bytes(), original)

    def test_successor_is_recorded_as_exact_source_change(self):
        self.fixture()
        (self.root / 'replacement.c').write_text('int replacement;\n')
        manifest = {'format': 1, 'sources': {'one.c': {
            'input_sha256': compose.sha(self.root / 'source/one.c'),
            'output_sha256': compose.sha(self.root / 'replacement.c'), 'source': 'replacement.c'}}}
        compose.write_json(self.root / 'successor.json', manifest)
        result = compose.apply_exact_successor(self.root / 'source', self.root / 'successor.json')
        self.assertEqual(result['sources']['one.c']['output_sha256'], compose.sha(self.root / 'source/one.c'))
        self.assertNotIn('hardware_admission', result)

    def test_final_object_hash_and_dependency_are_rechecked(self):
        obj = self.root / 'one.o'
        header = self.root / 'contract.h'
        obj.write_bytes(b'first compile')
        header.write_text('#define VALUE 1\n')
        row = {'object': 'one.o', 'object_sha256': compose.sha(obj),
               'dependency_sha256': {str(header): compose.sha(header)}}
        compose.verify_compiled_rows([row], self.root)
        header.write_text('#define VALUE 2\n')
        with self.assertRaisesRegex(ValueError, 'dependency'):
            compose.verify_compiled_rows([row], self.root)
        obj.write_bytes(b'foreign compile')
        with self.assertRaisesRegex(ValueError, 'object'):
            compose.verify_compiled_rows([row], self.root)

    def test_original_feature_macros_are_confined_to_exact_guarded_sources(self):
        value = {'fixed_source_profiles': {'live_abi_closure': True,
            'per_original_source_compile_definitions': compose.LIVE_ORIGINAL_DEFINITIONS}}
        self.assertEqual(compose.original_source_flags(value,
            'src/nvidia/arch/nvalloc/unix/src/vbioscall.c'),
            ['-DS540_NVIDIA_NONPRIMARY_X86_EMULATION=1'])
        self.assertEqual(compose.original_source_flags(value,
            'src/nvidia/src/kernel/rmapi/event_api.c'), ['-DS540_NVIDIA_NO_OS_EVENT_BACKEND=1'])
        self.assertEqual(compose.original_source_flags(value,
            'src/nvidia/arch/nvalloc/unix/src/osapi.c'), [])
        value['fixed_source_profiles']['per_original_source_compile_definitions'] = {
            **compose.LIVE_ORIGINAL_DEFINITIONS,
            'src/nvidia/arch/nvalloc/unix/src/osapi.c': {'S540_NVIDIA_NO_OS_EVENT_BACKEND': '1'}}
        with self.assertRaisesRegex(ValueError, 'per-original-source'):
            compose.original_source_flags(value, 'src/nvidia/arch/nvalloc/unix/src/osapi.c')

    def test_full_live_source_profile_refuses_missing_lifetime_dependencies(self):
        absent = self.root / 'absent'
        with self.assertRaisesRegex(ValueError, 'requires all four'):
            compose.materialize(absent, absent, absent, absent, live_abi_closure=True)
        with self.assertRaisesRegex(ValueError, 'retained diagnostic Host'):
            compose.materialize(absent, absent, absent, absent, retained_backends=True)
        with self.assertRaisesRegex(ValueError, 'Global epoch requires'):
            compose.materialize(absent, absent, absent, absent, global_epoch=True)


if __name__ == '__main__':
    unittest.main()
