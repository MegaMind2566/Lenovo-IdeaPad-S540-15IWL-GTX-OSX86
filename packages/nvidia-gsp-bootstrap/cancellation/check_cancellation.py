#!/usr/bin/env python3
"""CPU checks for isolated prospective cancellation; never enables entry."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'builders'))
import check_nvidia_execution as execution
from prepare_wait_candidates import prepare

def check(output: Path, upstream: Path, namespace: Path, host_control: bool) -> dict:
    here = Path(__file__).resolve().parent
    proposed = output / 'prospective'
    source = prepare(upstream, proposed)
    services = [execution.SERVICES / ('src/S540NvidiaDarwin' + name + '.cpp')
                for name in execution.SERVICE_NAMES]
    c_flags = ['-std=gnu11', '-Werror', '-Wno-unused-parameter',
               '-I', str(here), '-I', str(proposed)]
    record = execution.original_header_case(output, 'gsp-cancellation-record', upstream,
        namespace, [here / 'S540NvidiaGspCancellation.c'],
        [here / 'check_cancellation_native.cpp', *services],
        {'component': 'nvidia-gsp-cancellation', 'checks': 38,
         'concurrent_revocation_producers': 16, 'deadline_extension_refused': True,
         'cleanup_phase_distinct': True, 'original_entry_admission': False},
        host_control=host_control, dead_strip=True, extra_c_flags=c_flags)
    waits = execution.original_header_case(output, 'gsp-original-cancellation-waits',
        upstream, namespace, [here / 'S540NvidiaGspCancellation.c',
            here / 'S540NvidiaGspCancellationOriginal.c',
            here / 'check_original_wait_bodies.c'],
        [here / 'check_original_waits_native.cpp', *services],
        {'component': 'nvidia-gsp-original-wait-cancellation', 'checks': 40,
         'actual_original_wait_bodies': 4, 'revoked_during_wait': True,
         'hardware_cleanup_proven': False, 'original_entry_admission': False},
        host_control=host_control, dead_strip=True, extra_c_flags=c_flags)
    result = {'format': 1, 'status': 'passed-isolated-prospective-cpu-controls',
        'source_profile': source, 'record': record, 'original_waits': waits,
        'hardware_cleanup_proven': False, 'power_lifetime_gate_blocked': True,
        'production_candidate_allowed': False, 'gpu_access': False,
        'kernel_execution': 'not_tested'}
    (output / 'cancellation-checks.json').write_text(json.dumps(result, indent=2) + '\n')
    return result

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--upstream', type=Path, required=True)
    parser.add_argument('--namespace', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--host-control', action='store_true')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    result = check(args.output, args.upstream, args.namespace, args.host_control)
    print(json.dumps({'status': result['status'], 'checks_per_variant': 78,
        'original_wait_bodies': 4, 'power_lifetime_gate_blocked': True}))
