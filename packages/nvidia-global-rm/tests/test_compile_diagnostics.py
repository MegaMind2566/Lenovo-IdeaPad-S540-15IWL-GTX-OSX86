#!/usr/bin/env python3
"""Check failed-command diagnostics and preservation of completed compile evidence."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
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
            self.assertNotIn('source_namespace_verified', record)
            self.assertNotIn('dependency_controls', record)
            self.assertEqual(len(record['object_sha256']), 1)
            self.assertEqual(json.loads((output / 'compile-results.json').read_text())[0]['status'], 0)


if __name__ == '__main__':
    unittest.main()
