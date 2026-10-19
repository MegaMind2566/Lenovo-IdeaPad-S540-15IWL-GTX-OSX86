#!/usr/bin/env python3
"""Selected-root controls: exact decoding, cycles and unknowns never disappear."""
from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'builders'))
import nvidia_stack_root_closure as closure


def node(name, frame=8, calls=(), unknown=(), *, identity=None, weak=False):
    return {'id': identity or name, 'symbols': [name], 'external_symbols': [name],
        'non_strong_external_symbols': [name] if weak else [], 'static_frame_bytes': frame,
        'compiler_records': [{'source_location': name + '.c:1:' + name}],
        'calls': [{'address': index, 'kind': 'call', 'target': {'symbol': target}}
                  for index, target in enumerate(calls)], 'unknown_sites': list(unknown)}


def graph(nodes):
    return {'nodes': nodes, 'object': 'fixture.o', 'object_sha256': 'a'*64,
            'source': 'fixture.c', 'source_sha256': 'b'*64, 'capture_sha256': 'c'*64}


def analyze(nodes, root='_entry'):
    return closure.selected_roots([graph(nodes)], {'entry': root})['roots']['entry']


class ClosureControls(unittest.TestCase):
    def test_complete_chain_and_sibling_maximum(self):
        result = analyze([node('_entry', 24, ['_left', '_right']), node('_left', 8), node('_right', 40)])
        self.assertTrue(result['compiled_subgraph_complete'])
        self.assertEqual(result['compiled_subgraph_upper_bound_bytes'], 24+8+40+8)
        self.assertEqual([n['symbols'][0] for n in result['diagnostic_acyclic_frame_sum']['path']],
                         ['_entry', '_right'])
        self.assertFalse(result['diagnostic_acyclic_frame_sum']['runtime_peak_or_lower_bound'])

    def test_external_indirect_special_and_dynamic_barriers_preserved(self):
        for reason in ('indirect-control-transfer', 'unreviewed-special-control-transfer',
                       'dynamic-compiler-stack-frame', 'unreviewed-stack-pointer-write'):
            with self.subTest(reason=reason):
                result = analyze([node('_entry', unknown=[{'reason': reason}])])
                self.assertIsNone(result['compiled_subgraph_upper_bound_bytes'])
                self.assertEqual(result['barrier_reason_counts'], {reason: 1})
        result = analyze([node('_entry', calls=['_IOKit'])])
        self.assertIsNone(result['compiled_subgraph_upper_bound_bytes'])
        self.assertEqual(result['barrier_reason_counts'], {'external-stack-bound-unavailable': 1})

    def test_missing_and_ambiguous_roots_and_exports_remain_unknown(self):
        cases = [([node('_other')], 'missing-root-definition'),
                 ([node('_entry'), node('_entry', identity='duplicate')], 'ambiguous-root-definition'),
                 ([node('_entry', calls=['_child']), node('_child'), node('_child', identity='duplicate')],
                  'ambiguous-external-definition'),
                 ([node('_entry', weak=True)], 'non-strong-root-definition'),
                 ([node('_entry', calls=['_child']), node('_child', weak=True)], 'non-strong-external-definition')]
        for nodes, reason in cases:
            with self.subTest(reason=reason):
                result = analyze(nodes)
                self.assertIsNone(result['compiled_subgraph_upper_bound_bytes'])
                self.assertIn(reason, result['barrier_reason_counts'])

    def test_duplicate_measured_identity_is_not_silently_merged(self):
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            analyze([node('_entry'), node('_entry')])

    def test_missing_inventory_blocks_even_a_retained_leaf_root(self):
        result = closure.selected_roots([graph([node('_entry')])], {'entry': '_entry'},
            inventory_barriers=[{'reason': 'incomplete-project-input-inventory', 'missing_unit_count': 1}])['roots']['entry']
        self.assertIsNone(result['compiled_subgraph_upper_bound_bytes'])
        self.assertFalse(result['compiled_subgraph_complete'])
        self.assertFalse(result['diagnostic_acyclic_frame_sum']['is_complete_bound'])
        self.assertEqual(result['barrier_reason_counts'], {'incomplete-project-input-inventory': 1})

    def test_recursive_components_are_exact_and_reported_once(self):
        result = analyze([node('_entry', calls=['_a', '_self']), node('_a', calls=['_b']),
                          node('_b', calls=['_a']), node('_self', calls=['_self'])])
        self.assertIsNone(result['compiled_subgraph_upper_bound_bytes'])
        self.assertEqual(result['recursive_component_count'], 2)
        self.assertEqual(result['barrier_reason_counts'], {'recursion-cycle': 2})
        groups = {frozenset(n['symbols'][0] for n in b['component_members']) for b in result['barriers']}
        self.assertEqual(groups, {frozenset(['_a', '_b']), frozenset(['_self'])})

    def test_iterative_walk_handles_deep_call_chains(self):
        count = 1800
        result = analyze([node('_n'+str(i), calls=['_n'+str(i+1)] if i+1<count else [])
                          for i in range(count)], root='_n0')
        self.assertEqual(result['reachable_function_count'], count)
        self.assertEqual(result['compiled_subgraph_upper_bound_bytes'], count*16)
        self.assertFalse(result['diagnostic_acyclic_frame_sum']['runtime_peak_or_lower_bound'])

    def test_ranked_sources_and_shortest_path_preserve_provenance(self):
        nodes = [node('_entry', calls=['_child']), node('_child', calls=['_SDK'])]
        result = analyze(nodes)
        barrier = result['barriers'][0]
        self.assertEqual(barrier['shortest_compiled_path'], ['_entry', '_child'])
        self.assertEqual(barrier['function']['source_sha256'], 'b'*64)
        self.assertEqual(result['ranked_barrier_sources'][0]['barrier_count'], 1)

    def test_repeated_analysis_does_not_mutate_measured_graphs(self):
        graphs = [graph([node('_entry', calls=['_SDK'])])]
        before = deepcopy(graphs)
        self.assertEqual(closure.selected_roots(graphs, {'entry': '_entry'}),
                         closure.selected_roots(graphs, {'entry': '_entry'}))
        self.assertEqual(graphs, before)


class ActualObjects(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cc = os.environ.get('S540_STACK_TEST_CLANG') or shutil.which('clang') or shutil.which('clang-18')
        if not cls.cc:
            raise unittest.SkipTest('Actual Clang required.')
        objdump = os.environ.get('S540_STACK_TEST_OBJDUMP') or shutil.which('llvm-objdump-18') or shutil.which('llvm-objdump')
        if sys.platform == 'darwin':
            cls.decoder = ['/usr/bin/xcrun', 'otool', '-tv']
        elif objdump:
            cls.decoder = [objdump, '--macho', '--disassemble', '--no-show-raw-insn', '--no-symbolic-operands']
        else:
            raise unittest.SkipTest('Actual Mach-O disassembler required.')

    def actual(self, root, text):
        root = root.resolve()
        source = root/'fixture.c'; obj = root/'fixture.o'; source.write_text(text)
        command = [self.cc, '-target', 'x86_64-apple-macos15', '-O2', '-ffreestanding', '-fstack-usage',
                   '-c', str(source), '-o', str(obj)]
        subprocess.run(command, capture_output=True, check=True)
        reference = closure.stack.capture_usage(source, obj, command, cwd=root)
        return reference, {'capture': Path(reference['path']), 'unit': closure.stack.load_capture(reference),
                           'object': obj, 'image': closure.macho.Object(obj, allow_empty_code_without_symbols=True)}

    def test_readonly_redecoder_matches_frozen_collector_on_actual_objects(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reference, checked = self.actual(root,
                'extern int external(int);\n'
                '__attribute__((noinline)) static int leaf(int a) {return a+1;}\n'
                'int entry(int a, int (*callback)(int)) {return external(leaf(a)) + callback(a);}\n')
            actual = closure.fresh_graph(checked, self.decoder)
            self.assertFalse((root/'fixture.stack-graph.json').exists())
            frozen = closure.stack.extract_graph(reference, decoder=self.decoder)
            for node in actual['nodes']:
                node.pop('non_strong_external_symbols')
            self.assertEqual(actual['nodes'], frozen['nodes'])
            self.assertEqual(actual['decoder_output_sha256'], frozen['decoder_output_sha256'])

    def test_changed_object_is_rejected_even_with_previously_parsed_image(self):
        with tempfile.TemporaryDirectory() as directory:
            reference, checked = self.actual(Path(directory), 'int entry(void) {return 1;}\n')
            checked['object'].write_bytes(checked['object'].read_bytes()+b'changed')
            with self.assertRaisesRegex(ValueError, 'changed before decoding'):
                closure.fresh_graph(checked, self.decoder)

    def test_actual_same_unit_weak_definition_is_never_treated_as_private_leaf(self):
        with tempfile.TemporaryDirectory() as directory:
            reference, checked = self.actual(Path(directory),
                '__attribute__((noinline,weak)) int child(int x) {return x+1;}\n'
                'int entry(int x) {return child(x)+2;}\n')
            measured = closure.fresh_graph(checked, self.decoder)
            result = closure.selected_roots([measured], {'entry': '_entry'})['roots']['entry']
            self.assertIsNone(result['compiled_subgraph_upper_bound_bytes'])
            self.assertIn('non-strong-code-definition', result['barrier_reason_counts'])

    def test_actual_same_unit_external_definition_keeps_global_uniqueness_check(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root/'a').mkdir(); (root/'b').mkdir()
            _, first = self.actual(root/'a',
                '__attribute__((noinline)) int child(int x) {return x+1;}\n'
                'int entry(int x) {return child(x)+2;}\n')
            _, second = self.actual(root/'b', '__attribute__((noinline)) int child(int x) {return x+2;}\n')
            measured = [closure.fresh_graph(unit, self.decoder) for unit in (first, second)]
            result = closure.selected_roots(measured, {'entry': '_entry'})['roots']['entry']
            self.assertIsNone(result['compiled_subgraph_upper_bound_bytes'])
            self.assertIn('ambiguous-code-definition', result['barrier_reason_counts'])

    def test_private_edge_cannot_hide_weak_or_duplicate_export(self):
        entry = node('_entry')
        entry['calls'] = [{'address': 0, 'kind': 'call', 'target': {'node': '_child'}}]
        for children, reason in (([node('_child', weak=True)], 'non-strong-code-definition'),
                ([node('_child'), node('_child', identity='duplicate')], 'ambiguous-code-definition')):
            with self.subTest(reason=reason):
                result = analyze([entry, *children])
                self.assertIsNone(result['compiled_subgraph_upper_bound_bytes'])
                self.assertIn(reason, result['barrier_reason_counts'])

    def test_empty_actual_object_remains_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            reference, checked = self.actual(Path(directory), 'typedef unsigned int CompiledOut;\n')
            result = closure.fresh_graph(checked, self.decoder)
            self.assertEqual(result['nodes'], [])
            self.assertEqual(result['object_sha256'], closure.stack.sha(checked['object']))

    def test_project_manifest_checks_real_inputs_and_refuses_changed_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reference, checked = self.actual(root, 'int entry(void) {return 1;}\n')
            manifest = root/'manifest.json'; closure.stack.usage_manifest([reference], manifest)
            units, missing = closure.project_manifest(manifest, closure.binding.Paths(), expected_count=1)
            self.assertEqual(len(units), 1)
            self.assertEqual(missing, [])
            checked['object'].write_bytes(checked['object'].read_bytes()+b'changed')
            with self.assertRaisesRegex(ValueError, 'hash changed'):
                closure.project_manifest(manifest, closure.binding.Paths(), expected_count=1, allow_missing=True)

    def test_missing_archived_project_object_is_explicit_never_zero(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reference, checked = self.actual(root, 'int entry(void) {return 1;}\n')
            manifest = root/'manifest.json'; closure.stack.usage_manifest([reference], manifest)
            checked['object'].unlink()
            with self.assertRaises(FileNotFoundError):
                closure.project_manifest(manifest, closure.binding.Paths(), expected_count=1)
            units, missing = closure.project_manifest(manifest, closure.binding.Paths(), expected_count=1, allow_missing=True)
            self.assertEqual(units, [])
            self.assertEqual(len(missing), 1)
            self.assertEqual(missing[0]['missing_paths'], [str(checked['object'])])
            self.assertIn('no stack bound admitted', missing[0]['reason'])


if __name__ == '__main__':
    unittest.main()
