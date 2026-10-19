#!/usr/bin/env python3
"""Check failed-command diagnostics and preservation of completed compile evidence."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import platform
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location(
    'compile_nvidia_global_rm', ROOT / 'builders/compile_nvidia_global_rm.py')
assert SPEC is not None and SPEC.loader is not None
BUILDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILDER)


class CompileDiagnosticsTests(unittest.TestCase):
    def link_command_fixture(self, *, cross_probe=False, extra_export=False):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            commands = []

            def link_fixture(args, **_kwargs):
                commands.append(args)
                Path(args[args.index('-o') + 1]).write_bytes(b'explicit-link-output-fixture')
                return subprocess.CompletedProcess(args, 0, '', '')

            def symbol_fixture(path, *, expected_type):
                self.assertEqual(expected_type, 8 if cross_probe else 11)
                roots = BUILDER.GLOBAL_ROOTS if path.name.startswith('global') else BUILDER.ADAPTER_ROOTS
                exports = {BUILDER.PREFIX + root for root in roots}
                if extra_export:
                    exports.add(BUILDER.PREFIX + 'unexpected_callback')
                return exports, {BUILDER.PREFIX + 'fixture_required'}, []

            with mock.patch.object(BUILDER, 'execute', side_effect=link_fixture), \
                 mock.patch.object(BUILDER, 'macho_symbols', side_effect=symbol_fixture):
                records = BUILDER.link_dependency_controls(
                    [output / 'fixture.o'], output, ['fixture-ld'], cross_probe=cross_probe)
            return commands, records

    def test_native_controls_use_kernel_profile_and_keep_exact_roots(self):
        commands, records = self.link_command_fixture()
        for command, roots in zip(commands, (BUILDER.GLOBAL_ROOTS, BUILDER.ADAPTER_ROOTS)):
            self.assertIn('-kext', command)
            self.assertNotIn('-bundle', command)
            self.assertNotIn('-lSystem', command)
            self.assertNotIn('-fPIC', command)
            self.assertIn('-dead_strip', command)
            self.assertEqual(command[command.index('-undefined') + 1], 'dynamic_lookup')
            exports = [command[i + 1] for i, arg in enumerate(command) if arg == '-exported_symbol']
            self.assertEqual(exports, ['_' + BUILDER.PREFIX + root for root in roots])
        for record in records.values():
            self.assertEqual(record['mach_o_filetype'], 11)
            self.assertEqual(record['image_type'], 'MH_KEXT_BUNDLE')
            self.assertEqual(record['link_profile'], 'native-kernel-non-pic')
            self.assertFalse(record['dynamic_libraries_linked'])
            self.assertFalse(record['image_executed'])
            self.assertFalse(record['production_candidate_allowed'])

    def test_pic_cross_probe_is_separate_from_native_kernel_profile(self):
        commands, records = self.link_command_fixture(cross_probe=True)
        for command in commands:
            self.assertIn('-bundle', command)
            self.assertNotIn('-kext', command)
        for record in records.values():
            self.assertEqual(record['mach_o_filetype'], 8)
            self.assertEqual(record['link_profile'], 'explicit-pic-cross-probe')
            self.assertFalse(record['production_candidate_allowed'])

    def test_kernel_control_does_not_accept_extra_exports(self):
        with self.assertRaisesRegex(ValueError, 'exports differ'):
            self.link_command_fixture(extra_export=True)

    def test_kernel_image_rejects_dylib_dependencies_and_wrong_filetype(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / 'fixture.bundle'
            for command in BUILDER.DYLIB_LOAD_COMMANDS:
                # Explicit parser-only fixture, not a link or execution proof.
                image.write_bytes(struct.pack('<8I', 0xfeedfacf, 0x01000007, 3,
                                              11, 1, 8, 0, 0) + struct.pack('<2I', command, 8))
                with self.assertRaisesRegex(ValueError, 'dynamic library'):
                    BUILDER.macho_symbols(image, expected_type=11)
            image.write_bytes(struct.pack('<8I', 0xfeedfacf, 0x01000007, 3, 8, 0, 0, 0, 0))
            with self.assertRaisesRegex(ValueError, 'thin x86_64'):
                BUILDER.macho_symbols(image, expected_type=11)

    @unittest.skipUnless(sys.platform == 'darwin' and platform.machine() == 'x86_64',
                         'Actual Apple kernel-profile linking requires Intel macOS.')
    def test_actual_native_non_pic_kernel_link_smoke(self):
        # This is an actual Apple compiler/linker regression, not an original
        # RM or kernel execution control. It runs before the expensive full RM
        # compile when this test file is invoked by the development workflow.
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            source = output / 'kernel-link-fixture.c'
            obj = output / 'kernel-link-fixture.o'
            source.write_text(
                'static int fixtureKernelData = 7;\n'
                'extern int s540Global_fixture_required(void *);\n'
                'extern int s540Global_fixture_unreachable(void);\n' +
                ''.join('int ' + BUILDER.PREFIX + root + '(void) { return '
                        's540Global_fixture_required(&fixtureKernelData); }\n'
                        for root in BUILDER.ADAPTER_ROOTS) +
                'int s540Global_fixture_unreachable_callback(void) { return '
                's540Global_fixture_unreachable(); }\n')
            BUILDER.execute(['/usr/bin/xcrun', 'clang', '-arch', 'x86_64',
                             '-mmacosx-version-min=15.0', '-mkernel', '-mcmodel=kernel',
                             '-fno-pic', '-fno-pie', '-ffreestanding', '-fno-stack-protector',
                             '-mno-red-zone', '-O1', '-Wall', '-Wextra', '-Werror',
                             '-c', str(source), '-o', str(obj)],
                            diagnostic_log=output / 'native-fixture-compile.log')
            records = BUILDER.link_dependency_controls([obj], output, ['/usr/bin/xcrun', 'ld'])
            for name, roots in (('global', BUILDER.GLOBAL_ROOTS), ('adapter', BUILDER.ADAPTER_ROOTS)):
                exports, imports, _ = BUILDER.macho_symbols(
                    output / (name + '-dependency-control.bundle'), expected_type=11)
                self.assertEqual(exports, {BUILDER.PREFIX + root for root in roots})
                self.assertEqual(imports, {'s540Global_fixture_required'})
                self.assertFalse(records[name]['dynamic_libraries_linked'])
                self.assertEqual(records[name]['mach_o_filetype'], 11)
                self.assertFalse(records[name]['image_executed'])

    def test_failed_link_keeps_full_diagnostics_and_bounds_display(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / 'global-dependency-control.log'
            detail = 'diagnostic-prefix\n' + 'x' * 12000 + '\nld: actual failure reason'
            command = [sys.executable, '-c',
                       'import sys; print("link stdout"); sys.stderr.write(' +
                       repr(detail) + '); sys.exit(7)', *['object-%d.o' % i for i in range(1100)]]
            with self.assertRaises(RuntimeError) as raised:
                BUILDER.execute(command, diagnostic_log=log)
            message = str(raised.exception)
            self.assertIn('exit status 7', message)
            self.assertIn('ld: actual failure reason', message)
            self.assertIn(str(log), message)
            self.assertNotIn('object-1099.o', message)
            self.assertLess(len(message), 8500)
            self.assertIn(detail, log.read_text())
            self.assertIn('link stdout', log.read_text())

    def test_timeout_keeps_partial_diagnostics_without_object_argv(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / 'adapter-dependency-control.log'
            command = ['linker', 'object.o', 'private-large-object-list.o']
            error = subprocess.TimeoutExpired(command, 300, output=b'partial stdout',
                                              stderr=b'partial linker diagnostic')
            with mock.patch.object(BUILDER.subprocess, 'run', side_effect=error):
                with self.assertRaises(RuntimeError) as raised:
                    BUILDER.execute(command, timeout=300, diagnostic_log=log)
            self.assertIn('timed out after 300 seconds', str(raised.exception))
            self.assertIn('partial linker diagnostic', str(raised.exception))
            self.assertNotIn('private-large-object-list.o', str(raised.exception))
            self.assertIn('partial stdout', log.read_text())

    def test_successful_link_log_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / 'global-dependency-control.log'
            result = BUILDER.execute([sys.executable, '-c',
                                      'import sys; print("output"); sys.stderr.write("warning")'],
                                     diagnostic_log=log)
            self.assertEqual(result.returncode, 0)
            self.assertIn('output', log.read_text())
            self.assertIn('warning', log.read_text())

    def test_compile_record_survives_later_link_failure_without_reuse_authorization(self):
        # A single fake compiler unit isolates record ordering. It is not an
        # original-RM compile or linker correctness control.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            upstream = root / 'upstream'
            source = upstream / 'src/nvidia/unit.c'
            source.parent.mkdir(parents=True)
            source.write_text('/* Explicit synthetic compiler fixture. */\n')
            namespace = root / 'namespace.h'
            namespace.write_text('/* Explicit namespace audit fixture. */\n')
            output = root / 'namespaced'
            summary = root / 'darwin-compile.json'
            obj = output / 'unit.o'
            command = ['fixture-clang', '-c', 'unit.c', '-o', str(obj)]

            def compile_fixture(args, **_kwargs):
                obj.write_bytes(b'explicit-object-fixture')
                return subprocess.CompletedProcess(args, 0, '', '')

            def metadata_fixture(args, **_kwargs):
                text = BUILDER.COMMIT if args[-2:] == ['rev-parse', 'HEAD'] else ''
                if '--version' in args:
                    text = 'Explicit compiler metadata fixture'
                return subprocess.CompletedProcess(args, 0, text, '')

            with mock.patch.object(BUILDER, 'execute', side_effect=metadata_fixture), \
                 mock.patch.object(BUILDER, 'original_commands', return_value=[command]), \
                 mock.patch.object(BUILDER.subprocess, 'run', side_effect=compile_fixture), \
                 mock.patch.object(BUILDER.stack_usage, 'verify_codegen',
                                   return_value={'explicit_stack_fixture': True}), \
                 mock.patch.object(BUILDER.stack_usage, 'capture_usage',
                                   return_value={'explicit_stack_fixture': True}), \
                 mock.patch.object(BUILDER.stack_usage, 'usage_manifest',
                                   return_value={'explicit_stack_fixture': True}), \
                 mock.patch.object(BUILDER, 'audit_namespace', return_value={'fixture': True}), \
                 mock.patch.object(BUILDER, 'link_dependency_controls',
                                   side_effect=RuntimeError('ld: explicit failure fixture')):
                with self.assertRaisesRegex(RuntimeError, 'explicit failure fixture'):
                    BUILDER.compile_original(upstream, output, Path('fixture-clang'),
                                             cross_probe=True, namespace=namespace,
                                             linker=Path('fixture-linker'), summary_path=summary)

            record = json.loads(summary.read_text())
            self.assertEqual(record, json.loads((output / 'darwin-compile.json').read_text()))
            self.assertEqual(record['status'], 'compiled')
            self.assertEqual(record['dependency_controls_status'], 'failed')
            self.assertTrue(record['namespace_applied'])
            self.assertFalse(record['global_rm_executed'])
            self.assertEqual(record['stack_usage'], {'explicit_stack_fixture': True})
            self.assertNotIn('source_namespace_verified', record)
            self.assertNotIn('dependency_controls', record)
            self.assertEqual(len(record['object_sha256']), 1)
            self.assertEqual(json.loads((output / 'compile-results.json').read_text())[0]['status'], 0)


if __name__ == '__main__':
    unittest.main()
