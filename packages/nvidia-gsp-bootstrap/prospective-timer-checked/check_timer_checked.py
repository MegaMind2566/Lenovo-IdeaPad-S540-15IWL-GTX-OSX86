#!/usr/bin/env python3
"""Reproduce the isolated checked-timer proposal; never admits original entry."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
GSP = ROOT / 'packages/nvidia-gsp-bootstrap'
PORT = GSP / 'timers'
sys.path.insert(0, str(ROOT / 'builders'))
import check_nvidia_execution as execution
import compile_nvidia_global_rm as original
sys.path.insert(0, str(GSP / 'cancellation'))
from prepare_wait_candidates import function_span

TIMER = 'src/nvidia/src/kernel/gpu/timer/timer.c'
OSTIMER = 'src/nvidia/src/kernel/gpu/timer/timer_ostimer.c'
OS = 'src/nvidia/arch/nvalloc/unix/src/os.c'

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def checked_inputs(root: Path, expected: dict[str, str]) -> dict[str, bytes]:
    data = {name: (root / name).read_bytes() for name in expected}
    for name, digest in expected.items():
        if sha(data[name]) != digest:
            raise ValueError('Frozen checked-timer input changed: ' + name)
    return data

def body(text: bytes, name: str, kind: str) -> str:
    decoded = text.decode()
    first, last = function_span(decoded, name)
    return kind + '\n' + decoded[first:last] + '\n'

def order_bodies(source: dict[str, bytes], candidate: bool) -> str:
    selected = [(TIMER, 'tmrIsOSTimer', 'static NV_INLINE NvBool'),
        (TIMER, '_tmrGetNextAlarmTime', 'static NV_STATUS'),
        (OSTIMER, 'tmrEventCancelOSTimer_OSTIMER', 'NV_STATUS'),
        (OSTIMER, 'tmrEventDestroyOSTimer_OSTIMER', 'NV_STATUS'),
        (TIMER, '_tmrScanCallbackOSTimer', 'static void')]
    if candidate: selected += [(TIMER, '_s540TmrEventCancelChecked', 'static NV_STATUS')]
    selected += [(TIMER, 'tmrEventCancel_IMPL', 'void')]
    if candidate: selected += [(TIMER, '_s540TmrEventDestroyChecked', 'static NV_STATUS')]
    selected += [(TIMER, 'tmrEventDestroy_IMPL', 'void'),
        (TIMER, 'tmrCtrlCmdEventCancel', 'NV_STATUS'), (TIMER, 'tmrCtrlCmdEventDestroy', 'NV_STATUS')]
    return '\n'.join(body(source[path], name, kind) for path, name, kind in selected)

def prepare(upstream: Path, output: Path) -> tuple[dict, Path]:
    contract = json.loads((HERE / 'SOURCE-CONTRACT.json').read_bytes())
    source = checked_inputs(upstream, contract['original_source_sha256'])
    raw = dict(source)
    project = checked_inputs(ROOT, contract['original_project_sha256'])
    for index, patch in enumerate(contract['patches']):
        data = (HERE / patch['path']).read_bytes()
        if sha(data) != patch['sha256']:
            raise ValueError('Frozen checked-timer patch changed: ' + patch['path'])
        if index == 3: project.update(original._strict_patch(project, data))
        else: source.update(original._strict_patch(source, data))
    for name, digest in contract['final_source_sha256'].items():
        if sha(source[name]) != digest: raise ValueError('Composed source differs: ' + name)
        target = output / 'source' / name
        target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(source[name])
    bridge = output / 'bridge'; bridge.mkdir(parents=True, exist_ok=True)
    for name, digest in contract['final_project_sha256'].items():
        if sha(project[name]) != digest: raise ValueError('Composed project bridge differs: ' + name)
        (bridge / Path(name).name).write_bytes(project[name])
    for label, data in [('baseline', raw), ('proposed', source)]:
        (bridge / (label + '-os-bodies.inc')).write_text('\n'.join(
            body(data[OS], name, 'NV_STATUS') for name in ('osCancelNanoTimer', 'osDestroyNanoTimer')))
    order = output / 'order'; order.mkdir(parents=True, exist_ok=True)
    (order / 'baseline-bodies.inc').write_text(order_bodies(raw, False))
    (order / 'candidate-bodies.inc').write_text(order_bodies(source, True))
    status = output / 'status'; status.mkdir(parents=True, exist_ok=True)
    for label, data in [('baseline', raw), ('proposed', source)]:
        (status / (label + '-bodies.inc')).write_text('\n'.join(
            body(data[path], name, 'NV_STATUS') for path, name in (
                (OSTIMER, 'tmrEventCancelOSTimer_OSTIMER'), (TIMER, 'tmrStateUnload_IMPL'))))
    (output / 'prepared-source.json').write_text(json.dumps(contract, indent=2) + '\n')
    return contract, bridge

def check(upstream: Path, namespace: Path, output: Path, host_control: bool) -> dict:
    contract, bridge = prepare(upstream, output)
    services = [execution.SERVICES / ('src/S540NvidiaDarwin' + name + '.cpp')
                for name in execution.SERVICE_NAMES]
    tests = HERE / 'tests'
    def run(which: str, baseline: bool = False) -> dict:
        c_flags = ['-std=gnu11', '-Werror', '-Wno-unused-parameter']
        if which == 'bridge':
            c = [bridge / 'S540NvidiaGspTimersOriginal.c', tests / 'check_checked_bridge.c']
            cpp = services
            expected = {'component': 'nvidia-gsp-checked-timer-bridge', 'checks': 16,
                'actual_original_bodies': 2, 'real_timer_backend': True,
                'direct_callback_return_verified': True, 'accepted_event_borrowers_drained': False,
                'original_entry_admission': False}
            c_flags += ['-I', str(bridge), '-I', str(PORT), '-DS540_TIMER_OS_BASELINE=' + str(int(baseline))]
        elif which == 'order':
            c = [tests / 'check_event_order_bodies.c']; cpp = [tests / 'check_event_order_native.cpp']
            expected = {'component': 'nvidia-gsp-timer-event-order', 'checks': 384,
                'actual_original_bodies': 9, 'prospective_helpers': 0 if baseline else 2,
                'callback_return_proven': False, 'accepted_work_borrowers_closed': False,
                'all_void_owner_callers_statusful': False, 'original_entry_admission': False}
            c_flags += ['-I', str(output / 'order'), '-DS540_TIMER_ORDER_BASELINE=' + str(int(baseline))]
        elif which == 'status':
            c = [tests / 'check_cancel_status_bodies.c']; cpp = [tests / 'check_cancel_status_native.cpp']
            expected = {'component': 'nvidia-gsp-timer-cancel-status', 'checks': 49,
                'actual_original_bodies': 2, 'backend_cancellation_status_proven': False,
                'callback_return_proven': False, 'original_entry_admission': False}
            c_flags += ['-I', str(output / 'status'), '-DS540_TIMER_BASELINE=' + str(int(baseline))]
        else:
            c = [bridge / 'S540NvidiaGspTimersOriginal.c', PORT / 'tests/check_gsp_timers_native.c']
            cpp = services
            expected = {'component': 'nvidia-gsp-timers', 'checks': 34,
                'rc_callbacks': 1, 'nano_callbacks': 2, 'callback_fixture': True,
                'stack_abi_verified': True, 'quarantine_retention_verified': True, 'cleanup': True}
            c_flags += ['-I', str(bridge), '-I', str(PORT)]
        normal = execution.expect
        def baseline_expect(record: dict, fields: dict, description: str) -> None:
            failures = {'bridge': 4, 'order': 165, 'status': 10}[which]
            normal(record, {**fields, 'status': 'failed', 'failures': failures}, description)
        if baseline: execution.expect = baseline_expect
        try:
            return execution.original_header_case(output / 'controls', 'timer-checked-' + which +
                ('-baseline' if baseline else '-candidate'), upstream, namespace, c, cpp, expected,
                host_control=host_control, dead_strip=True, extra_c_flags=c_flags)
        finally: execution.expect = normal
    results = {which: {'candidate': run(which), 'baseline': run(which, True)}
               for which in ('bridge', 'order', 'status')}
    results['legacy_void_abi'] = run('legacy')
    record = {'format': 1, 'status': 'passed-isolated-timer-cpu-controls',
        'source_contract': contract, 'controls': results,
        'namespace_sha256': sha(namespace.read_bytes()),
        'accepted_work_borrowers_closed': False, 'aggregate_pm_deadline_proven': False,
        'dma_stop_receipt_issued': False, 'original_entry_admission': False,
        'kernel_execution': 'not_tested', 'gpu_access': False}
    (output / 'timer-checked-controls.json').write_text(json.dumps(record, indent=2) + '\n')
    return record

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--upstream', required=True, type=Path)
    parser.add_argument('--namespace', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--host-control', action='store_true')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    result = check(args.upstream.resolve(strict=True), args.namespace.resolve(strict=True),
                   args.output.resolve(), args.host_control)
    print(json.dumps({'status': result['status'], 'checks_each_variant': 483,
        'accepted_work_borrowers_closed': False, 'original_entry_admission': False}))
