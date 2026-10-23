#!/usr/bin/env python3
"""Attempt genuine shutdown/CPU stops while retaining every experimental owner."""
from pathlib import Path
import hashlib
import json
import sys
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DIRECTORY = 'packages/nvidia-gsp-bootstrap/prospective-retained-stop'
BOOT = 'packages/nvidia-gsp-bootstrap/src/S540NvidiaGspBootstrap.cpp'
HEADER = BOOT[:-3] + 'hpp'
SERVICES = 'packages/nvidia-gsp-bootstrap/prospective-first-transaction/services/S540NvidiaFirstTxnServices.cpp'
BRIDGE = DIRECTORY + '/S540NvidiaRetainedShutdown.c'
INPUTS = (BOOT, HEADER, SERVICES)
ORIGINAL_INPUTS = ()
COMPANIONS = {DIRECTORY + '/' + name: HERE / name for name in
    ('S540NvidiaRetainedStop.h', 'S540NvidiaRetainedShutdown.c')}
PROJECT_UNITS = ({'source': BRIDGE, 'kind': 'original-c'},)
EXPORTS = {BRIDGE: ('s540RetainedShutdownRun',)}
INCLUDE_DIRECTORIES = (DIRECTORY,)
COMPILE_DEFINITIONS = {}
SOURCE_FILES = ('BASE-SHA256.json', 'SOURCE-CONTRACT.json', 'check.py', 'tests/check_stop.cpp')
BASE_SHA256 = json.loads((HERE / 'BASE-SHA256.json').read_text())
sys.path.insert(0, str(ROOT / 'packages/nvidia-gsp-bootstrap/cancellation'))
from prepare_wait_candidates import function_span


def once(text, before, after):
    if text.count(before) != 1:
        raise ValueError('Exact retained stop source anchor changed: ' + before[:100])
    return text.replace(before, after)


def transforms(values):
    if set(values) != set(INPUTS) or set(BASE_SHA256) != set(INPUTS):
        raise ValueError('Exact post-coordinator retained stop source set required')
    for name, text in values.items():
        if hashlib.sha256(text.encode()).hexdigest() != BASE_SHA256[name]:
            raise ValueError('Retained stop prerequisite source changed: ' + name)
    out = dict(values)
    boot = out[BOOT]
    boot = once(boot, 'struct Owner::Impl {',
        'struct Owner::Impl {\n'
        '    mutable NvU32 retainedStopGuard = 0;\n'
        '    NvU32 retainedStopAttempts = 0;\n'
        '    S540RetainedStopSnapshot retainedStopPublished{};')
    boot = once(boot, '    NV_STATUS stop() {',
        (HERE / 'owner-stop.cpp.inc').read_text() + '\n    NV_STATUS stop() {')
    old = '''        // No disable, queue/timer stop, unbind, backing release, PM ack
        // or member destructor is authorized after this lifetime starts.
        if (diagnosticLifetimeHeld || transport.hardwareDmaLifetimeHeld()) {
            // Revoke/drain the actual IRQ producers on their retained owner worker.
            // Full mask refusal is retained; it cannot acknowledge PM or release storage.
            if (irqBinding.snapshot().installationAttempted) {
                const NV_STATUS irq = irqBinding.quiesce();
                if (irq != NV_OK) { state.quarantined = true; state.cleanupStatus = irq; return irq; }
            }
            state.quarantined = true; state.cleanupStatus = NV_ERR_IN_USE;
            return NV_ERR_IN_USE;
        }
'''
    boot = once(boot, old,
        '        // Retention prevents reclamation; it does not skip actual stop attempts.\n'
        '        if (diagnosticLifetimeHeld || transport.hardwareDmaLifetimeHeld())\n'
        '            return stopRetainedExperiment();\n')
    boot = once(boot, 'Snapshot Owner::snapshot() const {', '''S540RetainedStopSnapshot Owner::retainedStopSnapshot() const {
    if (impl_) return impl_->readRetainedStop();
    S540RetainedStopSnapshot value{}; value.format = 1; value.bytes = sizeof(value);
    value.snapshotStatus = NV_ERR_NOT_READY; return value;
}
Snapshot Owner::snapshot() const {''')
    out[BOOT] = boot
    header = once(out[HEADER], '#include "../prospective-runtime-coordinator/S540ExperimentalRuntime.h"',
        '#include "../prospective-runtime-coordinator/S540ExperimentalRuntime.h"\n'
        '#include "../prospective-retained-stop/S540NvidiaRetainedStop.h"')
    header = once(header, '    NV_STATUS initialize();',
        '    // Nonblocking diagnostic copy; lifecycle callers remain externally serialized.\n'
        '    S540RetainedStopSnapshot retainedStopSnapshot() const;\n'
        '    NV_STATUS initialize();')
    out[HEADER] = header
    services = out[SERVICES]
    first, last = function_span(services, 's540FirstTxnServicesSealAndDrain')
    # function_span starts at the name, preserving the pre-existing C linkage
    # and return type rather than declaring another independent wrapper.
    replacement = (HERE / 'services-seal.cpp.inc').read_text()
    prefix = 'extern "C" NV_STATUS '
    if not replacement.startswith(prefix): raise ValueError('Checked service body linkage changed')
    services = services[:first] + replacement[len(prefix):].rstrip() + services[last:]
    out[SERVICES] = services
    return out
