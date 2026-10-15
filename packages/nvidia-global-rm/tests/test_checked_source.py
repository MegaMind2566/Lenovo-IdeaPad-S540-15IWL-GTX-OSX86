#!/usr/bin/env python3
"""Checked-source provenance, isolation, ABI propagation and refusal regressions."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location('checked_rm_builder', ROOT / 'builders/compile_nvidia_global_rm.py')
assert SPEC is not None and SPEC.loader is not None
BUILDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILDER)
UPSTREAM = next((path for path in (ROOT / 'build-src/nvidia-upstream', ROOT.parent / 'nvidia-upstream-v9')
                 if path.exists()), ROOT / 'build-src/nvidia-upstream')


class CheckedSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.source = cls.root / 'checked-source'
        cls.original_header = (UPSTREAM / 'src/nvidia/inc/libraries/nvport/memory.h').read_bytes()
        cls.profile = BUILDER.prepare_checked_source(UPSTREAM, cls.source)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_complete_copy_and_exact_composition_preserve_baseline(self):
        profile = BUILDER.validate_checked_source(UPSTREAM, self.source)
        self.assertEqual(profile, self.profile)
        self.assertEqual(profile['file_count'], 4005)
        self.assertEqual(len(profile['changed_files']), 9)
        self.assertEqual(len(profile['patches']), 7)
        self.assertFalse(profile['source_semantics_unchanged'])
        self.assertFalse(profile['production_candidate_allowed'])
        self.assertNotEqual(profile['upstream_tree_sha256'], profile['tree_sha256'])
        header = 'src/nvidia/inc/libraries/nvport/memory.h'
        self.assertEqual((UPSTREAM / header).read_bytes(), self.original_header)
        self.assertNotEqual((self.source / header).read_bytes(), self.original_header)
        self.assertFalse((self.source / '.git').exists())

    def test_reused_workspace_is_refused(self):
        with self.assertRaisesRegex(ValueError, 'fresh workspace'):
            BUILDER.prepare_checked_source(UPSTREAM, self.source)

    def test_workspace_cannot_be_created_inside_pinned_checkout(self):
        with self.assertRaisesRegex(ValueError, 'isolated from the pinned checkout'):
            BUILDER.prepare_checked_source(UPSTREAM, UPSTREAM / 'unapproved-checked-workspace')
        self.assertFalse((UPSTREAM / 'unapproved-checked-workspace').exists())

    def test_untouched_source_mutation_is_detected(self):
        source = self.source / 'README.md'
        original = source.read_bytes()
        try:
            source.write_bytes(original + b'\n/* Unapproved mutation fixture. */\n')
            with self.assertRaisesRegex(ValueError, 'complete checked source workspace'):
                BUILDER.validate_checked_source(UPSTREAM, self.source)
        finally:
            source.write_bytes(original)

    def test_extra_file_and_symlink_are_refused(self):
        extra = self.source / 'unapproved-header.h'
        try:
            extra.write_text('/* Explicit extra-file fixture. */\n')
            with self.assertRaisesRegex(ValueError, 'extra files'):
                BUILDER.validate_checked_source(UPSTREAM, self.source)
            extra.unlink()
            extra.symlink_to(UPSTREAM / 'README.md')
            with self.assertRaisesRegex(ValueError, 'symlink'):
                BUILDER.validate_checked_source(UPSTREAM, self.source)
        finally:
            extra.unlink(missing_ok=True)

    def test_rewritten_output_manifest_cannot_authorize_other_bytes(self):
        path = self.root / BUILDER.CHECKED_MANIFEST
        original = path.read_bytes()
        try:
            record = json.loads(original)
            record['tree_sha256'] = '0' * 64
            path.write_text(json.dumps(record))
            with self.assertRaisesRegex(ValueError, 'reconstructed approved profile'):
                BUILDER.validate_checked_source(UPSTREAM, self.source)
        finally:
            path.write_bytes(original)

    def test_patch_digest_is_verified_before_workspace_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / 'package'
            shutil.copytree(BUILDER.PACKAGE / 'upstream', package / 'upstream')
            patch = package / 'upstream/adapted' / BUILDER.CHECKED_PATCHES[0]
            patch.write_bytes(patch.read_bytes() + b'\n')
            with mock.patch.object(BUILDER, 'PACKAGE', package):
                with self.assertRaisesRegex(ValueError, 'patch hash changed'):
                    BUILDER.prepare_checked_source(UPSTREAM, root / 'checked-source')
            self.assertFalse((root / 'checked-source').exists())

    def test_strict_patch_has_no_fuzz_or_offset_fallback(self):
        source = {'unit.c': b'context\nold\n'}
        patch = b'--- a/unit.c\n+++ b/unit.c\n@@ -1 +1 @@\n-old\n+new\n'
        with self.assertRaisesRegex(ValueError, 'source context changed'):
            BUILDER._strict_patch(source, patch)
        with self.assertRaisesRegex(ValueError, 'hunk count'):
            BUILDER._strict_patch(source, b'--- a/unit.c\n+++ b/unit.c\n@@ -2,2 +2 @@\n-old\n+new\n')

    def test_checked_bridge_flags_compile_changed_memory_abi(self):
        # Actual compiler/type checks show the baseline remains void while the
        # explicitly selected checked header returns NV_STATUS. No code runs.
        native = sys.platform == 'darwin'
        compiler = Path('/usr/bin/clang') if native else ROOT.parent / 'rs-toolchain/bin/clang'
        if not compiler.exists():
            self.skipTest('An actual Apple or explicit Darwin cross compiler is unavailable.')
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            namespace = output / 'namespace-fixture.h'
            namespace.write_text('#define portMemInitialize s540CheckedFixture_portMemInitialize\n')
            # macOS temp directories may use /var while the compiler flags use
            # /private/var. Exercise an equivalent parent alias on every host.
            alias = output / 'checked-parent-alias'
            alias.symlink_to(self.root, target_is_directory=True)
            cases = (('baseline', None), ('checked', self.source),
                     ('checked-parent-alias', alias / self.source.name))
            for name, checked_source in cases:
                with self.subTest(source=name):
                    checked = checked_source is not None
                    source = output / ('abi-%s.c' % name)
                    source.write_text('#include "nvport/nvport.h"\n'
                                      '_Static_assert(__builtin_types_compatible_p('
                                      '__typeof__(&portMemInitialize), ' +
                                      ('NV_STATUS' if checked else 'void') +
                                      ' (*)(void)), "Memory ABI mismatch");\n')
                    flags = BUILDER.original_bridge_flags(UPSTREAM, output, compiler, namespace,
                                                           checked_source=checked_source)
                    if checked:
                        self.assertIn(str((checked_source / 'src/nvidia/inc/libraries').resolve(strict=True)), flags)
                        self.assertNotIn(str((UPSTREAM / 'src/nvidia/inc/libraries').resolve(strict=True)), flags)
                    flags += (['-mkernel', '-arch', 'x86_64', '-mmacosx-version-min=15.0'] if native
                              else ['-target', 'x86_64-macos-none', '-fPIC'])
                    obj = output / ('abi-%s.o' % name)
                    BUILDER.execute([str(compiler), *flags, '-c', str(source), '-o', str(obj)],
                                    diagnostic_log=output / ('abi-%s.log' % name))
                    BUILDER.macho_symbols(obj)

    def test_pending_and_cross_summaries_cannot_be_native_reused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            record = {'status': 'compiled', 'source_profile': BUILDER.CHECKED_PROFILE,
                      'source_semantics_unchanged': False, 'source_namespace_verified': True,
                      'namespace_applied': True, 'production_candidate_allowed': False,
                      'commit': BUILDER.COMMIT, 'dependency_controls_status': 'pending',
                      'native_apple_compiler': True, 'cross_compile_probe': False}
            path = root / 'checked-darwin-compile.json'
            for changes in ({}, {'dependency_controls_status': 'failed'},
                            {'dependency_controls_status': 'passed', 'native_apple_compiler': False,
                             'cross_compile_probe': True}):
                path.write_text(json.dumps({**record, **changes}))
                with self.assertRaisesRegex(ValueError, 'incomplete or unauthorized'):
                    BUILDER.load_checked_compilation(UPSTREAM, root)

    def test_stale_checked_compile_output_is_never_reused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'checked-namespaced').mkdir()
            with self.assertRaisesRegex(ValueError, 'fresh checked output'):
                BUILDER.compile_checked_overlays(UPSTREAM, root, Path('/usr/bin/clang'), cross_probe=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--upstream', type=Path)
    args, rest = parser.parse_known_args()
    if args.upstream is not None:
        UPSTREAM = args.upstream.resolve(strict=True)
    unittest.main(argv=[sys.argv[0], *rest])
