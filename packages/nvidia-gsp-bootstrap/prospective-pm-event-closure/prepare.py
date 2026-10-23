#!/usr/bin/env python3
"""Order actual PM callback revocation before public event or delayed hook."""
from pathlib import Path
import hashlib
import json
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DIRECTORY = 'packages/nvidia-gsp-bootstrap/prospective-pm-event-closure'
POWER = 'packages/nvidia-gsp-bootstrap/platform/S540NvidiaGspPower.cpp'
HEADER = POWER[:-3] + 'hpp'
CANCEL = 'packages/nvidia-gsp-bootstrap/cancellation/S540NvidiaGspCancellation.c'
BOOT = 'packages/nvidia-gsp-bootstrap/src/S540NvidiaGspBootstrap.cpp'
INPUTS = (POWER, HEADER, CANCEL, BOOT)
ORIGINAL_INPUTS = ()
COMPANIONS = {DIRECTORY + '/S540NvidiaPowerCoupling.h': HERE / 'S540NvidiaPowerCoupling.h'}
PROJECT_UNITS = ()
INCLUDE_DIRECTORIES = (DIRECTORY,)
COMPILE_DEFINITIONS = {}
EXPORTS = {CANCEL: ('s540GspCancellationPowerAcquireState',
    's540GspCancellationPowerReleaseState', 's540GspCancellationPowerRevokeAtState')}
SOURCE_FILES = ('BASE-SHA256.json', 'check.py', 'tests/check_pm_event.cpp', 'SOURCE-CONTRACT.json')
BASE_SHA256 = json.loads((HERE / 'BASE-SHA256.json').read_text())
sys.path.insert(0, str(ROOT / 'packages/nvidia-gsp-bootstrap/cancellation'))
from prepare_wait_candidates import function_span


def once(text, before, after):
    if text.count(before) != 1:
        raise ValueError('Exact PM event anchor missing/ambiguous: ' + before[:100])
    return text.replace(before, after)


def modify(text, name, transform):
    first, last = function_span(text, name)
    return text[:first] + transform(text[first:last]) + text[last:]


def transforms(values):
    if set(values) != set(INPUTS) or set(BASE_SHA256) != set(INPUTS):
        raise ValueError('Exact reviewed PM event source set required')
    for name, text in values.items():
        if hashlib.sha256(text.encode()).hexdigest() != BASE_SHA256[name]:
            raise ValueError('PM event parent source changed: ' + name)
    out = dict(values)
    out[CANCEL] = once(out[CANCEL], '#include "S540NvidiaGspCommit.h"',
        '#include "S540NvidiaGspCommit.h"\n#include "S540NvidiaPowerCoupling.h"')
    out[CANCEL] = once(out[CANCEL], 'CAPTURE_BUSY = 32, COMMIT_BUSY = 64, SHIFT = 7',
        'CAPTURE_BUSY = 32, COMMIT_BUSY = 64, POWER_COUPLED = 128, SHIFT = 8')
    out[CANCEL] = modify(out[CANCEL], 's540GspCancellationUnbind', lambda body: once(body,
        'CAPTURE_BUSY | COMMIT_BUSY)', 'CAPTURE_BUSY | COMMIT_BUSY | POWER_COUPLED)'))
    out[CANCEL] = modify(out[CANCEL], 's540GspCancellationRevokeAt', lambda body: once(once(body,
        '    if (!eventNs || eventNs > now) return NV_ERR_INVALID_ARGUMENT;\n'
        '    deadline = eventNs > ~(NvU64)0 - PM_BUDGET_NS ? ~(NvU64)0 : eventNs + PM_BUDGET_NS;',
        '    const NvBool clockValid = eventNs && now && eventNs <= now;\n'
        '    /* Even a failed clock closes OPERATION. It grants no cleanup\n'
        '     * deadline and a later event cannot fabricate one. */\n'
        '    deadline = !clockValid ? 0 : eventNs > ~(NvU64)0 - PM_BUDGET_NS ?\n'
        '        ~(NvU64)0 : eventNs + PM_BUDGET_NS;'),
        '    return NV_OK;\n}',
        '    return clockValid ? NV_OK : NV_ERR_INVALID_ARGUMENT;\n}'))
    out[CANCEL] += '\n' + (HERE / 'power-coupling.c.inc').read_text()
    header = out[HEADER]
    header = once(header, '    NvU64 revocationEventNs() const;\n    void completed();',
        '    NvU64 revocationEventNs() const;\n'
        '    NV_STATUS coupleCancellation(const void *, NvU64);\n'
        '    NV_STATUS releaseCancellation();\n'
        '    NV_STATUS closeCancellation(NvU64);\n'
        '    bool cancellationCoupled() const;\n'
        '    void completed();')
    header = once(header, '    bool lastOn_;',
        '    bool lastOn_;\n    const void *cancellationState_;\n    NvU64 cancellationToken_;')
    header = once(header, '    NV_STATUS acknowledgeRevocation();',
        '    NV_STATUS acknowledgeRevocation();\n'
        '    NV_STATUS coupleCancellation(const void *, NvU64);\n'
        '    NV_STATUS releaseCancellation();')
    out[HEADER] = header
    power = out[POWER]
    power = once(power, '#include "S540NvidiaGspPower.hpp"',
        '#include "S540NvidiaGspPower.hpp"\n#include "S540NvidiaPowerCoupling.h"')
    power = once(power, 'Protocol::Protocol() : state_{}, lastOn_(false) {}',
        'Protocol::Protocol() : state_{}, lastOn_(false), cancellationState_(nullptr), cancellationToken_(0) {}')
    power = once(power, 'void Protocol::completed() {',
        (HERE / 'power-protocol.cpp.inc').read_text() + '\nvoid Protocol::completed() {')
    power = once(power,
        '        if (post) protocol.revocationObserved(s540Darwin_os_get_monotonic_time_ns());',
        '        const NvU64 eventNs = post ? s540Darwin_os_get_monotonic_time_ns() : 0;\n'
        '        const NV_STATUS closed = post ? protocol.closeCancellation(eventNs) : NV_STATUS(NV_OK);\n'
        '        if (post) protocol.revocationObserved(eventNs);')
    power = once(power, 'IOLockLock(guard); protocol.posted(status);',
        'IOLockLock(guard); protocol.posted(closed != NV_OK ? closed : status);')
    power = once(power, 'if (protocol.snapshot().acknowledgementPending || revocationHooksInFlight)',
        'if (protocol.snapshot().acknowledgementPending || revocationHooksInFlight || protocol.cancellationCoupled())')
    power = once(power, 'if (impl_->protocol.snapshot().acknowledgementPending || impl_->revocationHooksInFlight)',
        'if (impl_->protocol.snapshot().acknowledgementPending || impl_->revocationHooksInFlight || impl_->protocol.cancellationCoupled())')
    power = once(power, 'Snapshot Lease::snapshot() const {',
        (HERE / 'power-lease.cpp.inc').read_text() + '\nSnapshot Lease::snapshot() const {')
    def native_revoke(body):
        body = once(body, '    Revocation action{};',
            '    Revocation action{};\n    NV_STATUS closed = NV_OK;')
        body = once(body,
            '        data->protocol.revocationObserved(s540Darwin_os_get_monotonic_time_ns());',
            '        const NvU64 eventNs = s540Darwin_os_get_monotonic_time_ns();\n'
            '        closed = data->protocol.closeCancellation(eventNs);\n'
            '        data->protocol.revocationObserved(eventNs);')
        body = once(body, 'data->protocol.posted(status);',
            'data->protocol.posted(closed != NV_OK ? closed : status);')
        return once(body, '    return status;', '    return closed != NV_OK ? closed : status;')
    power = modify(power, 'Lease::revokeNativeForTest', native_revoke)
    out[POWER] = power
    boot = out[BOOT]
    first, last = function_span(boot, 'postRevocation')
    prior = boot[first:last]
    replacement = '''postRevocation(void *owner) {
        auto *self = static_cast<Impl *>(owner);
        if (!self) return NV_ERR_INVALID_STATE;
        // The actual Power guard already closed this exact cancellation
        // generation before publishing its event or calling this delayed hook.
        return self->dispatcher.post(PowerRevoked);
    }'''
    boot = boot[:first] + replacement + boot[last:]
    boot = once(boot, '        __atomic_store_n(&cancellationToken, token, __ATOMIC_RELEASE);',
        '        __atomic_store_n(&cancellationToken, token, __ATOMIC_RELEASE);\n'
        '        status = power.coupleCancellation(nv, token);\n'
        '        if (status != NV_OK) return failed(status);')
    boot = once(boot, '        status = power.acknowledgeRevocation();',
        '        status = power.releaseCancellation(); if (status != NV_OK) goto retained;\n'
        '        status = power.acknowledgeRevocation();')
    out[BOOT] = boot
    return out
