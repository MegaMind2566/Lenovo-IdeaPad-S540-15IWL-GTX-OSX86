#!/usr/bin/env python3
"""Isolated policy controls, never native/target execution evidence."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('isolated_experimental_budget', HERE / 'native_budget.py')
budget = importlib.util.module_from_spec(spec)
spec.loader.exec_module(budget)


def fixture(worker=8192, irq=8192):
    def root(demand):
        return {'definition_count': 1, 'diagnostic_acyclic_frame_sum': {'bytes': demand},
            'barrier_count': 7, 'barrier_reason_counts': {'indirect-control-transfer': 4, 'recursion-cycle': 3},
            'recursive_component_count': 3}
    return {'status': 'complete-current-native-stack-graph-measured',
        'complete_native_object_inventory': True, 'original_translation_units': 1100,
        'project_translation_units': 66, 'dynamic_function_count': 0, 'graph_sha256': '1' * 64,
        'roots': {'context_initialize_wrapper': root(worker), 'interrupt_top': root(irq)}}


class PolicyControls(unittest.TestCase):
    def test_exact_capacity_is_accepted_but_not_certified(self):
        value = budget.derive(fixture())
        self.assertEqual(value['worker_required_stack_bytes'], 16384)
        self.assertEqual(value['irq_required_stack_bytes'], 16384)
        self.assertFalse(value['formal_stack_bound_proven'])
        self.assertFalse(value['unknown_contributions_bounded_by_measurement'])
        self.assertEqual(value['unknown_barriers']['interrupt_top']['count'], 7)

    def test_one_extra_measured_byte_cannot_fit_by_rounding_down(self):
        with self.assertRaises(ValueError):
            budget.derive(fixture(worker=8193))

    def test_irq_overflow_is_independent(self):
        with self.assertRaises(ValueError):
            budget.derive(fixture(worker=100, irq=8193))

    def test_no_fabricated_minimum_capacity(self):
        value = budget.derive(fixture(worker=100, irq=100))
        self.assertEqual(value['worker_required_stack_bytes'], 12288)

    def test_incomplete_original_inventory_is_rejected(self):
        value = fixture()
        value['original_translation_units'] -= 1
        with self.assertRaises(ValueError):
            budget.derive(value)

    def test_missing_or_ambiguous_root_is_rejected(self):
        for count in (0, 2):
            value = fixture()
            value['roots']['interrupt_top']['definition_count'] = count
            with self.assertRaises(ValueError):
                budget.derive(value)

    def test_no_known_frame_measurement_is_rejected(self):
        value = fixture()
        value['roots']['interrupt_top']['diagnostic_acyclic_frame_sum']['bytes'] = None
        with self.assertRaises(ValueError):
            budget.derive(value)

    def test_known_dynamic_frame_is_not_an_unknown_allowance(self):
        value = fixture()
        value['dynamic_function_count'] = 1
        with self.assertRaises(ValueError):
            budget.derive(value)

    def test_unknowns_do_not_change_into_zero_cost_or_formal_proof(self):
        value = budget.derive(fixture(worker=1, irq=1))
        self.assertEqual(value['total_allowance_bytes'], 8192)
        self.assertFalse(value['irq_capacity_observed'])
        self.assertFalse(value['scheduler_completion_bound_proven'])

    def test_immutable_profile_round_trip(self):
        encoded, result = budget.build_profile(fixture(), '2' * 64)
        self.assertEqual(len(encoded), 104)
        checked = budget.verify_profile(fixture(), encoded, '2' * 64)
        self.assertEqual(checked['worker_required_stack_bytes'], 16384)
        self.assertFalse(checked['formal_stack_bound_proven'])

    def test_immutable_profile_rejects_new_demand(self):
        encoded, _ = budget.build_profile(fixture(), '2' * 64)
        with self.assertRaises(ValueError):
            budget.verify_profile(fixture(worker=8193), encoded, '2' * 64)

    def test_native_contract_substitution_is_rejected(self):
        encoded, _ = budget.build_profile(fixture(), '2' * 64)
        with self.assertRaises(ValueError):
            budget.verify_profile(fixture(), encoded, '3' * 64)

    def test_known_dispatcher_prefix_cannot_hide_inside_unknown_allowance(self):
        value = fixture(worker=8000, irq=100)
        value['roots']['worker_owner_dispatch_0'] = deepcopy(value['roots']['context_initialize_wrapper'])
        value['roots']['worker_dispatch_prefix_0'] = deepcopy(value['roots']['interrupt_top'])
        value['roots']['worker_dispatch_prefix_0']['diagnostic_acyclic_frame_sum']['bytes'] = 300
        with self.assertRaises(ValueError):
            budget.derive(value)

    def test_known_physical_irq_prefix_is_added_to_actual_wrapper(self):
        value = fixture(worker=100, irq=7500)
        value['roots']['interrupt_context_top'] = deepcopy(value['roots']['interrupt_top'])
        value['roots']['interrupt_backend_prefix_0'] = deepcopy(value['roots']['interrupt_top'])
        value['roots']['interrupt_backend_prefix_0']['diagnostic_acyclic_frame_sum']['bytes'] = 1000
        with self.assertRaises(ValueError):
            budget.derive(value)

    def test_blocked_user_rpc_and_worker_are_separate_stacks(self):
        value = fixture(worker=7500, irq=100)
        value['roots']['privileged_target_request_0'] = deepcopy(value['roots']['context_initialize_wrapper'])
        for label, size in [('worker_owner_dispatch_0', 4000), ('worker_dispatch_prefix_0', 256)]:
            value['roots'][label] = deepcopy(value['roots']['interrupt_top'])
            value['roots'][label]['diagnostic_acyclic_frame_sum']['bytes'] = size
        result = budget.derive(value)
        self.assertEqual(result['worker_known_acyclic_bytes'], 7500)
        self.assertEqual(result['known_registered_callback_prefix_sums']['dispatcher_callback'], 4256)


if __name__ == '__main__':
    unittest.main()
