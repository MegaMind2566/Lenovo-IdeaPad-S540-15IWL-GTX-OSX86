#!/usr/bin/env python3
"""Targeted development-runner diagnostics and partial-progress regressions."""
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'builders'))
import nvidia_execution_commands as commands
import check_nvidia_execution as execution


class ExecutionDiagnosticsTests(unittest.TestCase):
    def test_failed_command_persists_actual_stderr_and_bounded_error(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            with self.assertRaisesRegex(RuntimeError, 'actual compiler error') as caught:
                with commands.diagnostics(output):
                    commands.run(sys.executable, '-c',
                                 'import sys; print("partial stdout"); '
                                 'sys.stderr.write("actual compiler error"); sys.exit(9)',
                                 *['object-%d.o' % i for i in range(1100)])
            record = json.loads((output / 'command-logs/command-records.json').read_text())
            self.assertEqual(record['status'], 'failed')
            self.assertEqual(record['commands'][0]['status'], 'failed')
            self.assertIn('partial stdout', Path(record['commands'][0]['log']).read_text())
            self.assertIn('actual compiler error', Path(record['commands'][0]['log']).read_text())
            self.assertNotIn('object-1099.o', str(caught.exception))

    def test_unchanged_nested_helper_failure_is_not_hidden(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            with self.assertRaisesRegex(RuntimeError, 'nested SDK diagnostic'):
                with commands.diagnostics(output):
                    raise subprocess.CalledProcessError(4, ['fixture-sdk-helper', 'fixture.o'],
                                                        output='nested stdout', stderr='nested SDK diagnostic')
            record = json.loads((output / 'command-logs/command-records.json').read_text())
            self.assertEqual(record['status'], 'failed')
            self.assertEqual(record['commands'][0]['status'], 'failed')
            self.assertIn('nested SDK diagnostic', Path(record['commands'][0]['log']).read_text())

    def test_nested_context_restores_outer_command_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            with commands.diagnostics(output):
                commands.run(sys.executable, '-c', 'print("outer before")')
                with commands.diagnostics(output / 'crypto'):
                    commands.run(sys.executable, '-c', 'print("inner")')
                commands.run(sys.executable, '-c', 'print("outer after")')
            outer = json.loads((output / 'command-logs/command-records.json').read_text())
            inner = json.loads((output / 'crypto/command-logs/command-records.json').read_text())
            self.assertEqual(outer['status'], 'passed')
            self.assertEqual(len(outer['commands']), 2)
            self.assertEqual(len(inner['commands']), 1)

    def test_partial_component_report_keeps_only_completed_checks(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / 'execution-checks.json'
            progress = commands.ComponentProgress(report, {'gpu_access': False})
            progress.component('first', lambda: {'status': 'passed', 'checks': 3})
            with self.assertRaisesRegex(ValueError, 'fixture failure'):
                progress.component('second', lambda: (_ for _ in ()).throw(ValueError('fixture failure')))
            record = json.loads(report.read_text())
            self.assertEqual(record['status'], 'failed')
            self.assertEqual(record['active_component'], 'second')
            self.assertEqual(record['native_execution'], {'first': {'status': 'passed', 'checks': 3}})
            self.assertFalse(record['gpu_access'])

    def test_failure_before_first_component_marks_existing_report_failed(self):
        @commands.logged(output_argument=1, report='execution-kernel-build.json')
        def fixture_kernel(_upstream, output):
            (output / 'execution-kernel-build.json').write_text(json.dumps(
                {'status': 'running', 'production_candidate_allowed': False}))
            raise ValueError('fixture validation refusal')
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            with self.assertRaisesRegex(ValueError, 'fixture validation refusal'):
                fixture_kernel(Path('fixture-upstream'), output)
            record = json.loads((output / 'execution-kernel-build.json').read_text())
            self.assertEqual(record['status'], 'failed')
            self.assertFalse(record['production_candidate_allowed'])

    def test_services_preflight_reuses_case_without_assets_or_upstream(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            fixture = {'native': {'checks': 166}, 'sanitized': {'checks': 166}}
            with mock.patch.object(execution, 'services_case', return_value=fixture) as case:
                record = execution.services_preflight(output, host_control=True)
            case.assert_called_once_with(output, host_control=True)
            self.assertEqual(record['status'], 'passed')
            self.assertEqual(record['native_execution'], {'darwin_services': fixture})
            self.assertFalse(record['production_candidate_allowed'])
            self.assertFalse(record['gpu_access'])
            self.assertEqual(record['kernel_runtime'], 'not_tested')

    def test_services_preflight_cli_does_not_require_assets(self):
        with mock.patch.object(sys, 'argv', ['check_nvidia_execution.py', '--services-preflight',
                                           '--output-dir', 'fixture-output', '--host-control']), \
             mock.patch.object(execution, 'services_preflight') as check, mock.patch('builtins.print'):
            self.assertEqual(execution.main(), 0)
        check.assert_called_once_with(Path('fixture-output'), host_control=True)

    def test_early_refusal_invalidates_prior_success_without_old_checks(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            report = output / 'services-preflight.json'
            report.write_text(json.dumps({'status': 'passed',
                                          'native_execution': {'old': {'checks': 999}},
                                          'authoritative_darwin_execution': True}))
            with mock.patch.object(execution.sys, 'platform', 'linux'):
                with self.assertRaisesRegex(ValueError, 'requires Intel macOS'):
                    execution.services_preflight(output)
            record = json.loads(report.read_text())
            self.assertEqual(record['status'], 'failed')
            self.assertTrue(record['previous_report_discarded'])
            self.assertTrue(record['early_refusal'])
            self.assertEqual(record['failure_type'], 'ValueError')
            self.assertEqual(record['native_execution'], {})
            self.assertNotIn('authoritative_darwin_execution', record)
            self.assertFalse(record['production_candidate_allowed'])


if __name__ == '__main__':
    unittest.main()
