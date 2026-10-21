import importlib.util
from pathlib import Path
import unittest
from types import SimpleNamespace

SPEC = importlib.util.spec_from_file_location('stack_admission_check',
    Path(__file__).resolve().parents[1] / 'check.py')
check = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(check)


def node(name, calls=(), externals=None):
    return {'id': name, 'symbols': ['_' + name], 'external_symbols': externals or ['_' + name],
            'calls': [{'address': 16 + i, 'kind': 'call', 'target': target}
                      for i, target in enumerate(calls)]}


def result(barriers, *, bound=None):
    reasons = {}
    for barrier in barriers:
        reasons[barrier['reason']] = reasons.get(barrier['reason'], 0) + 1
    return {'object_count': 1, 'function_count': 1, 'roots': {'first': {
        'symbol': '_first', 'definition_count': 1, 'reachable_function_count': 1,
        'barrier_count': len(barriers), 'barrier_reason_counts': reasons,
        'compiled_subgraph_complete': not barriers,
        'compiled_subgraph_upper_bound_bytes': bound,
        'recursive_component_count': sum(v['reason'] == 'recursion-cycle' for v in barriers),
        'barriers': barriers, 'diagnostic_acyclic_frame_sum': {'bytes': 32,
            'runtime_peak_or_lower_bound': False}}}}


class StackWitnessControls(unittest.TestCase):
    def test_constant_rsp_lea_bytes_are_equivalent_to_fixed_adjustment(self):
        self.assertEqual(check.rsp_lea_displacement(bytes.fromhex('488d642410')), (16, 5))
        self.assertEqual(check.rsp_lea_displacement(bytes.fromhex('488d6424f0')), (-16, 5))
        self.assertEqual(check.rsp_lea_displacement(bytes.fromhex('488da42400010000')), (256, 8))
        for code in ('488d644410', '488d6510', '488d6424', '8d642410', '488b642410'):
            self.assertIsNone(check.rsp_lea_displacement(bytes.fromhex(code)))

    def test_rsp_refinement_requires_bytes_decoder_and_static_frame_agreement(self):
        def fixture(code, instruction='leaq 0x10(%rsp), %rsp', frame=32):
            image = SimpleNamespace(data=bytes.fromhex(code),
                sections=[SimpleNamespace(name='__text', address=0, offset=0)])
            graphs = [{'object_sha256': 'hash', 'nodes': [{'id': 'a', 'symbols': ['_a'],
                'start': 0, 'end': len(image.data), 'static_frame_bytes': frame,
                'unknown_sites': [{'reason': 'unreviewed-stack-pointer-write',
                    'address': 0, 'instruction': instruction}]}]}]
            units = [{'unit': {'object_sha256': 'hash'}, 'image': image}]
            return check.refine_constant_rsp_lea(graphs, units)
        graphs, receipts = fixture('488d642410')
        self.assertFalse(graphs[0]['nodes'][0]['unknown_sites'])
        self.assertEqual(receipts[0]['rsp_constant_delta_bytes'], 16)
        for code, instruction, frame in [('488d644410', 'leaq 0x10(%rsp), %rsp', 32),
                ('488d642410', 'leaq 0x20(%rsp), %rsp', 32),
                ('488d642410', 'leaq 0x10(%rsp), %rsp', None)]:
            graphs, receipts = fixture(code, instruction, frame)
            self.assertEqual(len(graphs[0]['nodes'][0]['unknown_sites']), 1)
            self.assertFalse(receipts)

    def test_local_root_selection_cannot_create_symbolic_edges(self):
        graphs = [{'object_sha256': 'obj', 'source_sha256': 'src', 'nodes': [
            node('local', externals=['_other'])]}]
        selected, receipts = check.select_local_roots(graphs,
            {'dispatcher_thread_entry': '_local'})
        self.assertEqual(receipts[0]['new_machine_edges'], 0)
        self.assertNotIn('_local', graphs[0]['nodes'][0]['external_symbols'])
        graphs[0]['nodes'].append(node('caller', [{'symbol': '_local'}]))
        with self.assertRaisesRegex(ValueError, 'alter symbolic machine edge'):
            check.select_local_roots(graphs, {'dispatcher_thread_entry': '_local'})

    def test_actual_self_edge_is_closed_cycle(self):
        graphs = [{'nodes': [node('a', [{'node': 'a'}])]}]
        nodes, edges = check.linked_edges(graphs)
        cycle = check.cycle_witness(['a'], nodes, edges)
        self.assertEqual(cycle, [{'caller': ['_a'], 'callee': ['_a'],
            'machine_address': 16, 'transfer_kind': 'call'}])

    def test_cycle_witness_uses_actual_edge_addresses(self):
        graphs = [{'nodes': [node('a', [{'node': 'dead'}, {'symbol': '_b'}]),
            node('b', [{'node': 'c'}]), node('c', [{'node': 'a'}]), node('dead')]}]
        nodes, edges = check.linked_edges(graphs)
        cycle = check.cycle_witness(['a', 'b', 'c'], nodes, edges)
        self.assertEqual([v['machine_address'] for v in cycle], [17, 16, 16])
        self.assertEqual([v['caller'][0] for v in cycle], ['_a', '_b', '_c'])
        self.assertEqual(cycle[-1]['callee'], cycle[0]['caller'])

    def test_acyclic_member_list_is_rejected(self):
        graphs = [{'nodes': [node('a', [{'node': 'b'}]), node('b')]}]
        nodes, edges = check.linked_edges(graphs)
        with self.assertRaisesRegex(ValueError, 'closed edge witness'):
            check.cycle_witness(['a', 'b'], nodes, edges)

    def test_ambiguous_definition_is_not_selected_for_cycle(self):
        graphs = [{'nodes': [node('a', [{'symbol': '_weak'}]),
            node('b', [{'node': 'a'}], ['_weak']), node('c', [], ['_weak'])]}]
        nodes, edges = check.linked_edges(graphs)
        self.assertFalse(edges['a'])
        with self.assertRaises(ValueError):
            check.cycle_witness(['a', 'b'], nodes, edges)

    def test_duplicate_machine_identity_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Duplicate actual machine node'):
            check.linked_edges([{'nodes': [node('a'), node('a')]}])

    def test_all_unknown_reasons_remain_explicit_and_unbounded(self):
        reasons = ['external-stack-bound-unavailable', 'indirect-control-transfer',
                   'dynamic-compiler-stack-frame', 'unreviewed-stack-pointer-write',
                   'missing-root-definition']
        barriers = [{'reason': reason, 'distance_from_root': i,
                     'shortest_compiled_path': ['_first', '_blocker']}
                    for i, reason in enumerate(reasons)]
        compact = check.compact_result(result(barriers), [{'nodes': [node('first')]}])
        root = compact['roots']['first']
        self.assertEqual(set(root['blocker_witnesses']), set(reasons))
        for name in ('aggregate_upper_bound_bytes', 'target_stack_capacity_bytes',
                     'framework_entry_headroom_bytes', 'external_callback_reentry_bound_bytes',
                     'interrupt_nesting_headroom_bytes', 'compiled_subgraph_upper_bound_bytes'):
            self.assertIsNone(root[name])
        self.assertFalse(compact['aggregate_stack_proven'])
        self.assertFalse(root['original_entry_admission'])

    def test_a_guessed_finite_unknown_bound_is_rejected(self):
        barriers = [{'reason': 'external-stack-bound-unavailable'}]
        with self.assertRaisesRegex(ValueError, 'finite compiled bound'):
            check.compact_result(result(barriers, bound=32), [{'nodes': [node('first')]}])

    def test_finite_compiled_graph_still_does_not_grant_target_entry(self):
        compact = check.compact_result(result([], bound=32), [{'nodes': [node('first')]}])
        root = compact['roots']['first']
        self.assertTrue(root['compiled_subgraph_complete'])
        self.assertEqual(root['compiled_subgraph_upper_bound_bytes'], 32)
        self.assertIsNone(root['aggregate_upper_bound_bytes'])
        self.assertFalse(root['original_entry_admission'])

    def test_each_recursive_component_retains_its_closed_walk_and_unknown_depth(self):
        graphs = [{'nodes': [node('a', [{'node': 'b'}]), node('b', [{'node': 'a'}])]}]
        barriers = [{'reason': 'recursion-cycle', 'shortest_compiled_path': ['_a'],
            'component_members': [{'id': 'a', 'symbols': ['_a'], 'static_frame_bytes': 8},
                                  {'id': 'b', 'symbols': ['_b'], 'static_frame_bytes': 16}]}]
        compact = check.compact_result(result(barriers), graphs)
        component = compact['roots']['first']['recursive_components'][0]
        catalog = compact['recursive_component_catalog'][component['component_id']]
        self.assertEqual(len(catalog['closed_machine_walk']), 2)
        self.assertIsNone(component['maximum_nested_activations'])
        self.assertFalse(component['depth_bound_established'])


if __name__ == '__main__':
    unittest.main()
