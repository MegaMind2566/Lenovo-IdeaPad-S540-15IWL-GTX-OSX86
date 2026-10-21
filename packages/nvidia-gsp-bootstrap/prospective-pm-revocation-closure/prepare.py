#!/usr/bin/env python3
"""Opt-in actual cancellation/endpoint acceptance ordering; no PM admission."""
from pathlib import Path
import argparse
import hashlib
import json
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DIRECTORY = 'packages/nvidia-gsp-bootstrap/prospective-pm-revocation-closure'
CANCEL = 'packages/nvidia-gsp-bootstrap/cancellation/S540NvidiaGspCancellation.c'
BRIDGE = 'packages/nvidia-gsp-bootstrap/cancellation/S540NvidiaGspCancellationOriginal.c'
TIMERS = 'packages/nvidia-gsp-bootstrap/timers/S540NvidiaGspTimersOriginal.c'
BACKEND = 'packages/nvidia-device-transport/src/S540NvidiaDarwinDevice.cpp'
TX = 'src/nvidia/src/kernel/gpu/gsp/message_queue_cpu.c'
INPUTS = (CANCEL, BRIDGE, TIMERS, BACKEND)
ORIGINAL_INPUTS = (TX,)
BASE_SHA256 = {
    CANCEL: 'c379d1513e592ce0916e3db11ec089bd144b4fa4e184097015af762b6d7bac22',
    BRIDGE: '6ea70a348aafb70b4c03ca393bab95939526bf995c583ab73f141d844f76c334',
    TIMERS: '901c8bd01dce3eacf0c8856f36d6827a4ee417d62d413a8946be303a294c77fe',
    BACKEND: '1f80b3739bce641959066e2f873f2118d2163fd7a0cf51bb77f578031b2254b3',
    TX: '7280805221de30bd1e68841584a14bdb8a8e945da58963d6cba16173da4066a0'}
COMPANIONS = {DIRECTORY + '/S540NvidiaGspCommit.h': HERE / 'S540NvidiaGspCommit.h'}
PROJECT_UNITS = ()
INCLUDE_DIRECTORIES = (DIRECTORY,)
COMPILE_DEFINITIONS = {}
EXPORTS = {
    CANCEL: ('s540GspCancellationCommitEnterState', 's540GspCancellationSubmitEnterState',
        's540GspCancellationCommitLeaveState', 's540GspCancellationCommitReadState'),
    BRIDGE: ('s540GspCancellationSubmitEnterGpu', 's540GspCancellationCommitLeaveGpu')}
sys.path.insert(0, str(ROOT / 'packages/nvidia-gsp-bootstrap/cancellation'))
from prepare_wait_candidates import function_span


def once(text, before, after):
    if text.count(before) != 1:
        raise ValueError('Exact PM commit anchor absent/ambiguous: ' + before[:90])
    return text.replace(before, after)


def modify(text, name, transform):
    first, last = function_span(text, name)
    return text[:first] + transform(text[first:last]) + text[last:]


def authenticate(values, expected):
    if set(values) != set(expected):
        raise ValueError('Exact PM commit input set required.')
    for name, value in values.items():
        if hashlib.sha256(value.encode()).hexdigest() != BASE_SHA256[name]:
            raise ValueError('PM commit source/writer inventory changed: ' + name)


def transforms(values):
    authenticate(values, INPUTS)
    out = dict(values)
    out[CANCEL] = once(out[CANCEL], '#include "Participants.h"',
        '#include "Participants.h"\n#include "S540NvidiaGspCommit.h"')
    out[CANCEL] = once(out[CANCEL], '       CAPTURE_BUSY = 32, SHIFT = 6 };',
        '       CAPTURE_BUSY = 32, COMMIT_BUSY = 64, SHIFT = 7 };')
    out[CANCEL] = modify(out[CANCEL], 's540GspCancellationPendingLeases', lambda body:
        once(body, '    return n;',
            '    /* A reservation is retained even before its token is published. */\n'
            '    return n + ((word() & COMMIT_BUSY) ? 1U : 0U);'))
    out[CANCEL] = modify(out[CANCEL], 's540GspCancellationBeginCleanupState', lambda body:
        once(body, 'if (value & CAPTURE_BUSY)', 'if (value & (CAPTURE_BUSY | COMMIT_BUSY))'))
    out[CANCEL] = modify(out[CANCEL], 's540GspCancellationFinish', lambda body:
        once(body, 'if(value&(CAPTURE_BUSY|PUBLISHING))', 'if(value&(CAPTURE_BUSY|PUBLISHING|COMMIT_BUSY))'))
    out[CANCEL] = modify(out[CANCEL], 's540GspCancellationUnbind', lambda body:
        once(body, '(OPERATION | CLEANUP | PUBLISHING | CAPTURE_BUSY)',
            '(OPERATION | CLEANUP | PUBLISHING | CAPTURE_BUSY | COMMIT_BUSY)'))
    out[CANCEL] += '\n' + (HERE / 'commit-api.c.inc').read_text()

    out[BRIDGE] = once(out[BRIDGE], '#include "S540NvidiaGspCancellationOriginal.h"',
        '#include "S540NvidiaGspCancellationOriginal.h"\n#include "S540NvidiaGspCommit.h"')
    out[BRIDGE] += '''
NV_STATUS s540GspCancellationSubmitEnterGpu(OBJGPU *gpu,
    S540GspCancellationCommitLease *out) {
    if (!gpu) { if (out) *out = 0; return NV_ERR_INVALID_ARGUMENT; }
    return s540GspCancellationSubmitEnterState(NV_GET_NV_STATE(gpu), out);
}
NV_STATUS s540GspCancellationCommitLeaveGpu(OBJGPU *gpu,
    S540GspCancellationCommitLease lease) {
    if (!gpu) return NV_ERR_INVALID_ARGUMENT;
    return s540GspCancellationCommitLeaveState(NV_GET_NV_STATE(gpu), lease);
}
'''

    helper = '''static NV_STATUS s540PmTimerArm(nv_state_t *nv, S540DarwinTimer *timer, NvU64 delay) {
    S540GspCancellationCommitLease commit = 0;
    NV_STATUS status = s540GspCancellationCommitEnterState(nv, &commit);
    NV_STATUS leave;
    if (status != NV_OK) return status;
    status = s540DarwinTimerArm(timer, delay);
    leave = s540GspCancellationCommitLeaveState(nv, commit);
    /* Failure does not establish that an arm was rejected or cancelled. */
    return status != NV_OK ? status : leave;
}
'''
    out[TIMERS] = once(out[TIMERS], '#include "S540NvidiaGspTimers.h"',
        '#include "S540NvidiaGspTimers.h"\n#include "S540NvidiaGspCommit.h"')
    for before, after in [
        ('s540DarwinTimerArm(device->rc, 1000000000ULL)', 's540PmTimerArm(device->nv, device->rc, 1000000000ULL)'),
        ('s540DarwinTimerArm(item->timer, delay)', 's540PmTimerArm(nv, item->timer, delay)')]:
        if out[TIMERS].count(before) != 2:
            raise ValueError('Exact RC/nano arm call set changed.')
        out[TIMERS] = out[TIMERS].replace(before, after)
    out[TIMERS] = once(out[TIMERS], 'static NV_STATUS rc_arm_locked(', helper + 'static NV_STATUS rc_arm_locked(')

    out[BACKEND] = '#include "S540NvidiaGspCommit.h"\n' + out[BACKEND]
    def irq(body):
        body = once(body, '    // Failure from enableInterrupt',
            '    S540GspCancellationCommitLease commit = 0;\n'
            '    NV_STATUS accepted = s540GspCancellationCommitEnterState(p->interrupt.originalState, &commit);\n'
            '    if (accepted != NV_OK) return accepted;\n'
            '    // Failure from enableInterrupt')
        body = once(body, '    if (p->provider->enableInterrupt(0) != kIOReturnSuccess) {',
            '    const auto enabled = p->provider->enableInterrupt(0);\n'
            '    const NV_STATUS leave = s540GspCancellationCommitLeaveState(p->interrupt.originalState, commit);\n'
            '    if (enabled != kIOReturnSuccess) {')
        body = once(body, '    p->irqEnabled = true;\n    return NV_OK;',
            '    p->irqEnabled = true;\n'
            '    if (leave != NV_OK) __atomic_store_n(&p->accepting, false, __ATOMIC_RELEASE);\n'
            '    return leave;')
        return body
    out[BACKEND] = modify(out[BACKEND], 'armInterrupt', irq)
    return out


def original_transforms(values):
    authenticate(values, ORIGINAL_INPUTS)
    text = once(values[TX], '#include "S540NvidiaGspCancellationOriginal.h"',
        '#include "S540NvidiaGspCancellationOriginal.h"\n#include "S540NvidiaGspCommit.h"')
    text = once(text, '    nRet = msgqTxSubmitBuffers(pMQI->hQueue, nElements);', '''    {
        S540GspCancellationCommitLease commit = 0;
        NV_STATUS leave;
        nvStatus = s540GspCancellationSubmitEnterGpu(pGpu, &commit);
        if (nvStatus != NV_OK) goto done;
        nRet = msgqTxSubmitBuffers(pMQI->hQueue, nElements);
        leave = s540GspCancellationCommitLeaveGpu(pGpu, commit);
        /* Preserve a real submit failure. An end failure after accepted work
         * retains its reservation; neither result implies rollback/drain. */
        if (nRet == 0 && leave != NV_OK) { nvStatus = leave; goto done; }
    }''')
    return {TX: text}


def prepare(base, output):
    if output.exists():
        raise ValueError('Fresh PM commit output required.')
    base = base.resolve(strict=True)
    output.mkdir(parents=True)
    rows = []
    for scope, inputs, transform in [('project', INPUTS, transforms), ('source', ORIGINAL_INPUTS, original_transforms)]:
        values = {name: (base / scope / name).read_text() for name in inputs}
        for name, text in transform(values).items():
            path = output / scope / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
            rows.append(dict(scope=scope, source=name, input_sha256=BASE_SHA256[name],
                output_sha256=hashlib.sha256(text.encode()).hexdigest()))
    for name, source in COMPANIONS.items():
        path = output / 'project' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(source.read_bytes())
    report = dict(format=1, status='source-only-revocation-commit-plan', sources=rows,
        original_entry_admission=False, pm_30_second_shutdown_bound_proven=False,
        physical_release_authorized=False, hardware_stop_proven=False)
    (output / 'pm-commit-source.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.base, args.output)))
