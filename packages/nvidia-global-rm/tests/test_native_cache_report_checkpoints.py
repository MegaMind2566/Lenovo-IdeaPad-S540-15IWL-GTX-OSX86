#!/usr/bin/env python3
"""Exercise real 1,100-future collection while measuring diagnostic writes.

Only the logging/control-flow layer is under test. Compiler/cache rows and the
final native verifier are explicit mocks; no Apple execution is claimed.
"""
from contextlib import ExitStack
from copy import deepcopy
import importlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'builders'))
import compose_nvidia_first_transaction as composition
sys.path.insert(0, str(composition.FIRST / 'original'))
common = importlib.import_module('common')


class OriginalCacheReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.output = self.base / 'composition'
        self.source_root = self.output / 'source/src/nvidia'
        self.source_root.mkdir(parents=True)
        self.upstream = self.base / 'upstream'
        self.upstream.mkdir()
        self.manifest = {'namespace': 'S540ComposedNamespace.h',
                         'fixed_source_profiles': {'per_original_source_compile_definitions': {}}}
        (self.output / 'composition.json').write_text(json.dumps(self.manifest))
        (self.output / 'S540ComposedNamespace.h').write_text('/* fixture namespace */\n')
        self.commands = []
        for index in range(1100):
            name = 'unit-%04d.c' % index
            (self.source_root / name).write_text('/* source fixture ' + str(index) + ' */\n')
            self.commands.append(['/usr/bin/clang', '-O2', '-c', name, '-o',
                                  str(self.output / 'original-objects' / name.replace('.c', '.o'))])
        self.cache = Mock()
        self.expected_rows = {}
        self.fail_source = None
        self.worker_error = None
        def reuse(**values):
            relative = values['source'].relative_to(self.output / 'source').as_posix()
            if relative == self.fail_source:
                raise self.worker_error or ValueError('controlled cache mismatch')
            row = {'source': relative, 'source_sha256': '1' * 64,
                'object': values['obj'].name, 'object_sha256': '2' * 64,
                'definitions': ['fixture_' + values['obj'].stem], 'imports': [],
                'command': values['command'], 'cwd': str(values['cwd']),
                'dependency_sha256': {str(values['source']): '1' * 64},
                'stack_usage': {'path': str(values['obj'].with_suffix('.stack.json')), 'sha256': '3' * 64},
                'native_cache_reuse': {'compiled_this_run': False,
                    'object_bytes_unchanged': True, 'fixture_provenance': relative}}
            self.expected_rows[relative] = deepcopy(row)
            return row
        self.cache.reuse.side_effect = reuse
        self.snapshots = []
        self.final_reports = []

    def patches(self):
        stack = ExitStack()
        stack.enter_context(patch.object(common, 'compiler', return_value=Path('/usr/bin/clang')))
        stack.enter_context(patch.object(common, 'execution_identity', return_value={
            'authoritative_darwin_execution': True, 'host_control': False,
            'host_system': 'Darwin', 'compilers': {'fixture': 'mocked Apple compiler identity'}}))
        stack.enter_context(patch.object(composition.original, '_pinned_upstream', return_value=self.upstream))
        stack.enter_context(patch.object(composition.original, 'original_commands', return_value=self.commands))
        stack.enter_context(patch.object(composition, 'verify_composition', return_value=self.manifest))
        self.compiler = stack.enter_context(patch.object(composition.original, 'execute'))
        real_write = composition.write_json
        def write(path, record):
            if path.name == 'full-original-compilation.json':
                self.snapshots.append((record['status'], len(record['results']), len(record['failures'])))
            return real_write(path, record)
        stack.enter_context(patch.object(composition, 'write_json', side_effect=write))
        def finalize(output, report):
            # The unchanged real native verifier owns source/symbol/stack
            # validation; this mock models only its sorted final report write.
            report['results'].sort(key=lambda row: row['source'])
            report.update(status='compiled-full-original-source-only', original_objects=1100)
            self.final_reports.append(deepcopy(report))
            composition.write_json(output / 'full-original-compilation.json', report)
            return report
        self.finalize = stack.enter_context(patch.object(composition, 'finalize_original_compilation', side_effect=finalize))
        return stack

    def run_matrix(self):
        return composition.compile_original_objects(self.upstream, self.output,
            Path('/usr/bin/clang'), host_control=False, native_cache=self.cache)

    def test_full_matrix_preserves_rows_and_provenance_with_bounded_report_writes(self):
        with self.patches():
            result = self.run_matrix()
            self.compiler.assert_not_called()
            self.cache.record_compiled.assert_not_called()
            self.finalize.assert_called_once()
        # This is an operational bound over the actual 1,100-future function,
        # independent of the chosen checkpoint arithmetic implementation.
        self.assertLessEqual(len(self.snapshots), 15)
        self.assertEqual(self.cache.reuse.call_count, 1100)
        self.assertEqual(len(result['results']), 1100)
        self.assertEqual({r['source'] for r in result['results']}, set(self.expected_rows))
        for row in result['results']:
            self.assertEqual(row, self.expected_rows[row['source']])
        stored = json.loads((self.output / 'full-original-compilation.json').read_bytes())
        self.assertEqual(stored, result)
        self.assertEqual(self.snapshots[0], ('running', 0, 0))
        self.assertEqual(self.snapshots[-1], ('compiled-full-original-source-only', 1100, 0))

    def test_failed_worker_retains_every_available_row_and_failure(self):
        self.fail_source = 'src/nvidia/unit-0500.c'
        with self.patches():
            with self.assertRaisesRegex(ValueError, 'full original compilation failed'):
                self.run_matrix()
            self.finalize.assert_not_called()
            self.compiler.assert_not_called()
        stored = json.loads((self.output / 'full-original-compilation.json').read_bytes())
        self.assertEqual(stored['status'], 'failed')
        self.assertEqual(len(stored['results']), 1099)
        self.assertEqual(len(stored['failures']), 1)
        self.assertEqual(stored['failures'][0]['index'], 500)
        self.assertIn('controlled cache mismatch', stored['failures'][0]['error'])
        self.assertLessEqual(len(self.snapshots), 15)

    def assert_interruption_preserved(self, interruption):
        real_completed = composition.concurrent.futures.as_completed
        def interrupted(futures):
            for index, future in enumerate(real_completed(futures)):
                if index == 17:
                    raise interruption
                yield future
        with self.patches(), patch.object(composition.concurrent.futures, 'as_completed', side_effect=interrupted):
            with self.assertRaises(type(interruption)):
                self.run_matrix()
            self.finalize.assert_not_called()
            self.compiler.assert_not_called()
        stored = json.loads((self.output / 'full-original-compilation.json').read_bytes())
        self.assertEqual(stored['status'], 'failed')
        self.assertEqual(stored['failure_type'], type(interruption).__name__)
        self.assertEqual(stored['error'], str(interruption))
        self.assertEqual(len(stored['results']), 1100)
        self.assertEqual(len({r['source'] for r in stored['results']}), 1100)
        self.assertEqual(stored['failures'], [])
        self.assertLessEqual(len(self.snapshots), 3)

    def test_keyboard_interrupt_preserves_full_available_matrix_before_propagating(self):
        self.assert_interruption_preserved(KeyboardInterrupt('cancel requested'))

    def test_unexpected_collector_exception_preserves_matrix_before_propagating(self):
        self.assert_interruption_preserved(RuntimeError('unexpected collector failure'))

    def test_worker_cancellation_records_its_failure_and_all_other_available_rows(self):
        self.fail_source = 'src/nvidia/unit-0500.c'
        self.worker_error = KeyboardInterrupt('worker interrupted')
        with self.patches():
            with self.assertRaises(KeyboardInterrupt):
                self.run_matrix()
            self.finalize.assert_not_called()
        stored = json.loads((self.output / 'full-original-compilation.json').read_bytes())
        self.assertEqual(stored['status'], 'failed')
        self.assertEqual(len(stored['results']), 1099)
        self.assertEqual(len(stored['failures']), 1)
        self.assertEqual(stored['failures'][0], {'index': 500, 'error': 'worker interrupted'})

    def test_checkpoint_writer_exception_preserves_current_matrix_before_propagating(self):
        with self.patches():
            real_write = composition.write_json
            triggered = False
            def interrupted_write(path, record):
                nonlocal triggered
                if not triggered and len(record['results']) >= 100:
                    triggered = True
                    raise OSError('temporary diagnostic write failure')
                return real_write(path, record)
            with patch.object(composition, 'write_json', side_effect=interrupted_write):
                with self.assertRaisesRegex(OSError, 'diagnostic write failure'):
                    self.run_matrix()
            self.finalize.assert_not_called()
        stored = json.loads((self.output / 'full-original-compilation.json').read_bytes())
        self.assertEqual(stored['status'], 'failed')
        self.assertEqual(stored['failure_type'], 'OSError')
        self.assertEqual(len(stored['results']), 1100)
        self.assertEqual(stored['failures'], [])


if __name__ == '__main__':
    unittest.main()
