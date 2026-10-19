#!/usr/bin/env python3
"""Stack measurements are diagnostic; unknown code must never gain a bound."""
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
import subprocess

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'builders'))
import nvidia_stack_usage as stack
from test_metaclass_initializers import fixture

def node(name, frame=8, calls=(), unknown=(), external=True):
    return {'id': name, 'symbols': [name], 'external_symbols': [name] if external else [],
            'static_frame_bytes': frame,
            'calls': [{'address': index, 'kind': 'call', 'target': {'symbol': target}}
                      for index, target in enumerate(calls)],
            'unknown_sites': list(unknown)}

def analyze(nodes, root='_entry'):
    return stack.aggregate_graphs([{'nodes': deepcopy(nodes)}], roots={'entry': root})

class StackUsage(unittest.TestCase):
    def test_clang_static_and_dynamic_records(self):
        rows = stack.parse_usage('a.c:9:entry\t24\tstatic\n'
                                 'a.c:10:variable\t40\tdynamic\n'
                                 'a.c:11:bounded\t64\tdynamic,bounded\n')
        self.assertEqual(rows[0]['symbol'], '_entry')
        self.assertEqual(rows[0]['reported_bytes'], 24)
        self.assertTrue(rows[0]['static_frame_known'])
        self.assertFalse(rows[1]['static_frame_known'])
        self.assertFalse(rows[2]['static_frame_known'])

    def test_column_location_is_supported(self):
        self.assertEqual(stack.parse_usage('a.c:9:3:entry\t8\tstatic\n')[0]['compiler_function'], 'entry')

    def test_unsupported_usage_is_rejected(self):
        for raw in ('a.c:9:entry 8 static', 'a.c:9:entry\t-1\tstatic',
                    'a.c:9:entry\t8\tguessed', 'no-location\t8\tstatic'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                stack.parse_usage(raw)

    def test_duplicate_function_identity_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Repeated'):
            stack.parse_usage('a.c:1:entry\t8\tstatic\na.c:2:entry\t16\tstatic')

    def test_native_otool_and_numeric_llvm_disassembly(self):
        text = ('object.o:\n(__TEXT,__text) section\n_entry:\n'
                '0000000000000000 pushq %rbp\n'
                '       1:\t48 89 e5\tmovq\t%rsp, %rbp\n'
                '       4:\tcallq\t*0x18(%rax)\n')
        rows = stack.parse_disassembly(text)
        self.assertEqual([row['mnemonic'] for row in rows], ['pushq', 'movq', 'callq'])
        self.assertIn('*', rows[2]['operands'])

    def test_undecoded_instruction_is_preserved(self):
        rows = stack.parse_disassembly('(__TEXT,__text) section\n0:\t<unknown>\n')
        self.assertEqual(rows[0]['mnemonic'], '<undecoded>')

    def test_decoder_without_text_section_is_rejected(self):
        with self.assertRaises(ValueError):
            stack.parse_disassembly('nothing decoded')

    def test_return_address_and_complete_direct_chain(self):
        report = analyze([node('_entry', 24, ['_leaf']), node('_leaf', 8)])
        entry = report['roots']['entry']
        self.assertEqual(entry['compiled_graph_upper_bound_bytes'], 24 + 8 + 8 + 8)
        self.assertTrue(entry['compiled_graph_complete'])
        self.assertFalse(report['aggregate_stack_proven'])
        self.assertIsNone(report['framework_entry_headroom_bytes'])
        self.assertFalse(report['production_candidate_allowed'])

    def test_sibling_calls_use_maximum_not_sum(self):
        result = analyze([node('_entry', 8, ['_left', '_right']),
                          node('_left', 16), node('_right', 40)])['roots']['entry']
        self.assertEqual(result['compiled_graph_upper_bound_bytes'], 8 + 8 + 40 + 8)

    def test_external_framework_frame_is_never_zero(self):
        result = analyze([node('_entry', 8, ['_IOKitFunction'])])['roots']['entry']
        self.assertIsNone(result['compiled_graph_upper_bound_bytes'])
        self.assertEqual(result['unknown_reason_counts'], {'external-stack-bound-unavailable': 1})

    def test_indirect_callback_keeps_root_unknown(self):
        result = analyze([node('_entry', unknown=[{'reason': 'indirect-control-transfer'}])])['roots']['entry']
        self.assertIsNone(result['compiled_graph_upper_bound_bytes'])

    def test_dynamic_frame_keeps_root_unknown(self):
        result = analyze([node('_entry', frame=None,
                               unknown=[{'reason': 'dynamic-compiler-stack-frame'}])])['roots']['entry']
        self.assertFalse(result['compiled_graph_complete'])

    def test_recursion_and_mutual_recursion_are_unknown(self):
        for nodes in ([node('_entry', calls=['_entry'])],
                      [node('_entry', calls=['_other']), node('_other', calls=['_entry'])]):
            result = analyze(nodes)['roots']['entry']
            self.assertIsNone(result['compiled_graph_upper_bound_bytes'])
            self.assertIn('recursion-cycle', result['unknown_reason_counts'])

    def test_missing_entry_definition_is_unknown(self):
        result = analyze([node('_other')])['roots']['entry']
        self.assertEqual(result['unknown_reason_counts'], {'missing-root-definition': 1})
        self.assertIsNone(result['compiled_graph_upper_bound_bytes'])

    def test_large_sum_is_not_a_runtime_overflow_claim(self):
        report = analyze([node('_entry', 12000, ['_child']), node('_child', 12000)])
        self.assertGreater(report['roots']['entry']['compiled_graph_upper_bound_bytes'], 16384)
        self.assertFalse(report['aggregate_stack_proven'])

    def test_global_resolution_does_not_mutate_object_evidence(self):
        graphs = [{'nodes': [node('_entry', calls=['_unknown'])]}]
        before = deepcopy(graphs)
        first = stack.aggregate_graphs(graphs, roots={'entry': '_entry'})
        second = stack.aggregate_graphs(graphs, roots={'entry': '_entry'})
        self.assertEqual(graphs, before)
        self.assertEqual(first, second)

    def test_capture_binds_source_object_and_su(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, obj = root / 'fixture.c', root / 'fixture.o'
            source.write_text('/* fixture is not executable */\n')
            fixture(obj)
            usage = obj.with_suffix('.su')
            usage.write_text('fixture.c:1:_GLOBAL__sub_I_reference.cpp\t8\tstatic\n'
                             'fixture.c:2:_GLOBAL__D_a\t8\tstatic\n'
                             'fixture.c:3:runtime_body\t0\tstatic\n')
            record = stack.capture_usage(source, obj, ['clang', '-fstack-usage'])
            self.assertEqual(stack.load_capture(record)['object_sha256'], stack.sha(obj))
            for path in (source, obj, usage):
                before = path.read_bytes()
                path.write_bytes(before + b'x')
                with self.subTest(path=path.name), self.assertRaisesRegex(ValueError, 'input changed'):
                    stack.load_capture(record)
                path.write_bytes(before)

    def test_missing_compiler_output_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, obj = root / 'fixture.c', root / 'fixture.o'
            source.write_text('/* fixture */')
            fixture(obj)
            with self.assertRaisesRegex(ValueError, 'did not emit'):
                stack.capture_usage(source, obj, ['clang', '-fstack-usage'])

    def test_compiler_function_must_exist_in_actual_object(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, obj = root / 'fixture.c', root / 'fixture.o'
            source.write_text('/* fixture */')
            fixture(obj)
            obj.with_suffix('.su').write_text('fixture.c:1:invented_function\t8\tstatic\n')
            with self.assertRaisesRegex(ValueError, 'lack actual text definitions'):
                stack.capture_usage(source, obj, ['clang', '-fstack-usage'])

    def test_actual_indirect_instruction_is_not_omitted_from_graph(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, obj = root / 'fixture.c', root / 'fixture.o'
            source.write_text('/* explicit binary parser fixture, never executed */')
            fixture(obj)
            obj.with_suffix('.su').write_text('fixture.c:1:_GLOBAL__sub_I_reference.cpp\t8\tstatic\n'
                                             'fixture.c:2:_GLOBAL__D_a\t8\tstatic\n'
                                             'fixture.c:3:runtime_body\t0\tstatic\n')
            capture = stack.capture_usage(source, obj, ['clang', '-fstack-usage'])
            disassembly = '(__TEXT,__text) section\n0:\tcallq\t*%rax\n30:\tretq\n40:\tretq\n'
            with mock.patch.object(stack.subprocess, 'run', return_value=
                    subprocess.CompletedProcess(['fixture-decoder'], 0, disassembly, '')):
                graph = stack.extract_graph(capture, decoder=['fixture-decoder'])
            entry = next(value for value in graph['nodes'] if value['start'] == 0)
            self.assertEqual(entry['unknown_sites'][0]['reason'], 'indirect-control-transfer')

    def test_legacy_cache_without_usage_cannot_prove_any_stack(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            obj = root / 'old.o'
            fixture(obj)
            output = root / 'audit.json'
            result = stack.audit([None], output, expected_objects=[obj])
            record = __import__('json').loads(output.read_text())
            self.assertEqual(result['missing_usage_manifests'], 1)
            self.assertEqual(record['missing_object_measurements'], [str(obj)])
            self.assertFalse(record['aggregate_stack_proven'])
            self.assertTrue(all(value['compiled_graph_upper_bound_bytes'] is None
                                for value in record['roots'].values()))

if __name__ == '__main__':
    unittest.main()
