#!/usr/bin/env python3
"""Object-scoped root controls; synthetic graphs are not native evidence."""
from copy import deepcopy
import hashlib
import importlib.util
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('isolated_current_root_lookup', HERE / 'check.py')
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


def graph(identity, frame, unknown=()):
    node = {'id': identity, 'symbols': ['_local_callback'], 'external_symbols': [],
        'non_strong_external_symbols': [], 'static_frame_bytes': frame,
        'compiler_records': [{'source_location': 'isolated.c:1:callback'}],
        'calls': [], 'unknown_sites': list(unknown)}
    return {'nodes': [node], 'object': identity + '.o', 'object_sha256': '1' * 64,
        'source': identity + '.c', 'source_sha256': '2' * 64, 'capture_sha256': '3' * 64}


class LocalRootControls(unittest.TestCase):
    def test_same_local_spelling_in_another_object_does_not_capture_root(self):
        graphs = [graph('current-object', 24), graph('other-object', 4000)]
        before = deepcopy(graphs)
        result = check.selected_actual_roots(graphs, {}, {'callback': ('current-object', '_local_callback')})
        root = result['roots']['callback']
        self.assertEqual(root['definition_count'], 1)
        self.assertEqual(root['diagnostic_acyclic_frame_sum']['bytes'], 32)
        self.assertEqual(root['symbol'], '_local_callback')
        self.assertFalse(root['actual_machine_linkage_changed'])
        self.assertEqual(graphs, before)

    def test_unknown_transfer_remains_a_barrier_for_an_actual_local_entry(self):
        graphs = [graph('current-object', 24, [{'reason': 'indirect-control-transfer'}])]
        result = check.selected_actual_roots(graphs, {}, {'callback': ('current-object', '_local_callback')})
        root = result['roots']['callback']
        self.assertFalse(root['compiled_subgraph_complete'])
        self.assertEqual(root['barrier_reason_counts'], {'indirect-control-transfer': 1})

    def test_missing_scoped_owner_is_rejected(self):
        with self.assertRaises(ValueError):
            check.selected_actual_roots([graph('current-object', 24)], {},
                {'callback': ('missing-object', '_local_callback')})

    def test_diagnostic_lookup_cannot_shadow_actual_machine_symbol(self):
        graphs = [graph('current-object', 24)]
        graphs[0]['nodes'][0]['symbols'].append('__s540_diagnostic_local_root_' +
            hashlib.sha256(b'current-object').hexdigest())
        with self.assertRaises(ValueError):
            check.selected_actual_roots(graphs, {}, {'callback': ('current-object', '_local_callback')})


if __name__ == '__main__':
    unittest.main()
