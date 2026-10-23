#!/usr/bin/env python3
"""Explicit experimental allowances over fresh current native measurements."""
from __future__ import annotations
import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
ALLOWANCES = {'framework_allowance_bytes': 2048, 'unknown_allowance_bytes': 4096,
              'recursion_allowance_bytes': 1024, 'exception_allowance_bytes': 1024}
POLICY_STACK_CAPACITY_BYTES = 16384
PAGE_BYTES = 4096


def require(value, reason):
    if not value:
        raise ValueError(reason)


def codec():
    path = HERE.parent / 'prospective-runtime-coordinator/profile.py'
    spec = importlib.util.spec_from_file_location('s540_experimental_native_profile_codec', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def rounded(value):
    return (value + PAGE_BYTES - 1) // PAGE_BYTES * PAGE_BYTES


def derive(measurement, *, worker_capacity_bytes=POLICY_STACK_CAPACITY_BYTES,
           irq_capacity_bytes=POLICY_STACK_CAPACITY_BYTES):
    require(measurement.get('status') == 'complete-current-native-stack-graph-measured' and
            measurement.get('complete_native_object_inventory') is True and
            measurement.get('original_translation_units') == 1100 and
            isinstance(measurement.get('project_translation_units'), int) and
            measurement['project_translation_units'] > 0,
            'A fresh complete current native object graph is required')
    require(measurement.get('dynamic_function_count') == 0,
            'A known dynamic compiler stack frame cannot receive a guessed experimental capacity')
    for capacity in (worker_capacity_bytes, irq_capacity_bytes):
        require(type(capacity) is int and capacity > 0 and capacity % PAGE_BYTES == 0,
                'An explicit positive aligned experimental capacity is required')
    roots = measurement.get('roots', {})
    require(roots and 'interrupt_top' in roots, 'Physical IRQ and ordinary execution roots are required')
    known, barriers = {}, {}
    for label, row in roots.items():
        require(row.get('definition_count') == 1, 'An actual root is absent/ambiguous: ' + label)
        demand = row.get('diagnostic_acyclic_frame_sum', {}).get('bytes')
        require(type(demand) is int and demand > 0,
                'The actual root lacks a positive measured acyclic path: ' + label)
        known[label] = demand
        barriers[label] = {'count': row.get('barrier_count'),
            'reason_counts': row.get('barrier_reason_counts'),
            'recursive_component_count': row.get('recursive_component_count')}
    # Physical top-half and ordinary worker roots have independent stacks.
    # Deferred bottom halves are measured as ordinary work, not summed onto a
    # physical IRQ top-half chain. Framework/nesting remains an explicit reserve.
    physical_irq = lambda label: label in ('interrupt_top', 'interrupt_context_top', 'interrupt_mmu_fault') or \
        label.startswith(('interrupt_backend_prefix_', 'interrupt_bound_top_'))
    irq_known = max(v for k, v in known.items() if physical_irq(k))
    worker_known = max(v for k, v in known.items() if not physical_irq(k))
    def maximum(prefixes=(), labels=()):
        return max((v for k, v in known.items() if k in labels or k.startswith(prefixes)), default=0)
    # Cross-thread invoke waits on its caller's stack; it does not put the
    # worker's RM chain on that caller. Registered callback prefixes, however,
    # remain live while their separately measured indirect body executes.
    # Add those KNOWN prefixes conservatively instead of spending an unknown
    # allowance on bytes already measured. Possible overlap only overcounts.
    joined = {
        'dispatcher_callback': maximum(('worker_dispatch_prefix_',)) + maximum(('worker_owner_dispatch_',)),
        'timer_callback': maximum(('callout_timer_prefix_',)) + maximum(labels=('recovery_timer', 'nano_timer')),
        'work_callback': maximum(('callout_work_prefix_',)) + maximum(labels=('work_item_execute',)),
        'deferred_bottom_callback': maximum(('deferred_bottom_prefix_',)) + maximum(labels=(
            'interrupt_locked_bottom', 'interrupt_unlocked_bottom', 'context_locked_bottom', 'context_unlocked_bottom')),
        'physical_irq_callback': maximum(('interrupt_backend_prefix_',)) + maximum(
            ('interrupt_bound_top_',), ('interrupt_top', 'interrupt_context_top', 'interrupt_mmu_fault')),
    }
    worker_known = max(worker_known, *(v for k, v in joined.items() if k != 'physical_irq_callback'))
    irq_known = max(irq_known, joined['physical_irq_callback'])
    allowance = sum(ALLOWANCES.values())
    worker_demand, irq_demand = worker_known + allowance, irq_known + allowance
    worker_required, irq_required = rounded(worker_demand), rounded(irq_demand)
    require(worker_required <= worker_capacity_bytes,
            'Known ordinary frame demand plus explicit reserves exceeds experimental stack capacity')
    require(irq_required <= irq_capacity_bytes,
            'Known physical IRQ frame demand plus explicit reserves exceeds experimental stack assumption')
    return {'format': 1, 'status': 'fits-explicit-retained-experiment-stack-policy',
        'root_diagnostic_acyclic_bytes': known, 'unknown_barriers': barriers,
        'worker_known_acyclic_bytes': worker_known, 'irq_known_acyclic_bytes': irq_known,
        'known_registered_callback_prefix_sums': joined,
        'registered_callback_prefix_overlap_conservatively_overcounted': True,
        **ALLOWANCES, 'total_allowance_bytes': allowance,
        'worker_demand_with_allowances_bytes': worker_demand,
        'irq_demand_with_allowances_bytes': irq_demand,
        'worker_required_stack_bytes': worker_required, 'irq_required_stack_bytes': irq_required,
        'experimental_worker_capacity_bytes': worker_capacity_bytes,
        'experimental_irq_capacity_assumption_bytes': irq_capacity_bytes,
        'worker_rounding_margin_bytes': worker_required - worker_demand,
        'irq_rounding_margin_bytes': irq_required - irq_demand,
        'capacity_equality_allowed': True,
        'actual_target_stack_bytes': None, 'irq_capacity_observed': False,
        'formal_stack_bound_proven': False, 'unknown_contributions_bounded_by_measurement': False,
        'scheduler_completion_bound_proven': False, 'production_candidate_allowed': False,
        'measurement_graph_sha256': measurement['graph_sha256'],
        'measurement_final_image': measurement.get('final_image_selection'),
        'policy_scope': 'once-per-boot retained experiment with explicit acknowledged allowances'}


def build_profile(measurement, code_contract_sha256, *, target_build='25G241'):
    report = derive(measurement)
    encoded = codec().encode_profile(code_contract_sha256,
        report['worker_required_stack_bytes'], report['irq_required_stack_bytes'],
        target_build=target_build, **ALLOWANCES)
    require(len(encoded) == 104, 'The actual immutable native profile ABI must be104 bytes')
    report['encoded_profile'] = codec().decode_profile(encoded)
    return encoded, report


def verify_profile(measurement, profile_bytes, code_contract_sha256):
    profile = codec().decode_profile(profile_bytes)
    # Codec spelling is normalized here only at its documented Python API;
    # none of these fields is caller-supplied runtime readiness authority.
    contract = profile.get('code_contract_sha256', profile.get('codeContractSha256'))
    if isinstance(contract, bytes):
        contract = contract.hex()
    require(contract == code_contract_sha256, 'Immutable native code-contract digest changed')
    def field(snake, camel):
        value = profile.get(snake, profile.get(camel))
        require(type(value) is int, 'Immutable native profile field missing: ' + snake)
        return value
    for snake, camel in (('framework_allowance_bytes', 'frameworkAllowanceBytes'),
                        ('unknown_allowance_bytes', 'unknownAllowanceBytes'),
                        ('recursion_allowance_bytes', 'recursionAllowanceBytes'),
                        ('exception_allowance_bytes', 'exceptionAllowanceBytes')):
        require(field(snake, camel) == ALLOWANCES[snake], 'Immutable experimental allowance changed')
    report = derive(measurement,
        worker_capacity_bytes=field('worker_stack_bytes', 'workerStackBytes'),
        irq_capacity_bytes=field('irq_stack_bytes', 'irqStackBytes'))
    report['encoded_profile'] = profile
    report['status'] = 'actual-final-native-measurement-fits-immutable-experimental-profile'
    return report
