#!/usr/bin/env python3
"""Isolated permanent operational-owner/session lifetime and PM-producer successor.

This selects source; it neither admits original RM entry nor acknowledges PM.
The optional loader transform must accompany any image using this profile.
"""
from pathlib import Path
import argparse
import hashlib
import json

HERE = Path(__file__).resolve().parent
BOOT = 'packages/nvidia-gsp-bootstrap/src/S540NvidiaGspBootstrap.cpp'
HEADER = BOOT[:-3]+'hpp'
POWER = 'packages/nvidia-gsp-bootstrap/platform/S540NvidiaGspPower.cpp'
POWER_HEADER = POWER[:-3]+'hpp'
LOADER = 'packages/nvidia-gsp-bootstrap/prospective-loader/S540ProspectiveLoaderKernel.cpp'
INPUTS = (BOOT, HEADER, POWER, POWER_HEADER)
TX = 'src/nvidia/src/kernel/gpu/gsp/message_queue_cpu.c'
ORIGINAL_INPUTS = (TX,)
TX_INPUT_SHA256 = '426b45f7cd754a80068d0093e67f7308dcd0dd828056dc4c5abf8d872af69f57'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('Exact session lifetime anchor missing or ambiguous: '+old[:100])
    return text.replace(old, new)


def transforms(values):
    if set(values) != set(INPUTS):
        raise ValueError('Exact session lifetime source set required')
    out = dict(values)
    boot = out[BOOT]
    boot = once(boot, 'namespace S540NvidiaGspBootstrap {',
        (HERE/'module-pin.cpp.inc').read_text()+'\nnamespace S540NvidiaGspBootstrap {')
    boot = once(boot, 'Inspect, NativeActionCommand, NativeAckFailure',
        'Inspect, RetainDiagnosticLifetime, NativeActionCommand, NativeAckFailure')
    boot = once(boot, 'bool host, deviceBound, firmwareBound, timersBound, platformBound, nativeFixture;',
        'bool host, deviceBound, firmwareBound, timersBound, platformBound, nativeFixture;\n'
        '    bool diagnosticLifetimeHeld;')
    boot = once(boot, 'timersBound(false), platformBound(false), nativeFixture(false), state{}, published{},',
        'timersBound(false), platformBound(false), nativeFixture(false), diagnosticLifetimeHeld(false), state{}, published{},')
    boot = once(boot, '        const auto token = __atomic_load_n(&self->cancellationToken, __ATOMIC_ACQUIRE);',
        '        const NvU64 event = self->power.revocationEventNs();\n'
        '        const auto token = __atomic_load_n(&self->cancellationToken, __ATOMIC_ACQUIRE);')
    boot = once(boot, '            self->power.snapshot().revokedAtNs) : NV_STATUS(NV_OK);',
        '            event) : NV_STATUS(NV_OK);')
    boot = once(boot, '        case Initialize: status = self->initialize(); break;',
        '        case Initialize: status = self->initialize(); break;\n'
        '        case RetainDiagnosticLifetime: status = self->retainDiagnosticLifetime(); break;')
    boot = once(boot, '        result.blockedGates = kBlockedGates;',
        '        result.diagnosticLifetimeRetained = diagnosticLifetimeHeld;\n'
        '        result.hardwareDmaLifetimeHeld = transport.hardwareDmaLifetimeHeld();\n'
        '        result.hardwareDmaGeneration = transport.hardwareDmaGeneration();\n'
        '        result.blockedGates = kBlockedGates;')
    boot = once(boot, '        if (self->timersBound) {',
        '        // The retained profile has no final-release path, including an\n'
        '        // unexpected direct ContextDestroy call through this detacher.\n'
        '        if (self->diagnosticLifetimeHeld || self->transport.hardwareDmaLifetimeHeld())\n'
        '            return NV_ERR_IN_USE;\n'
        '        if (self->timersBound) {')
    boot = once(boot, '    NV_STATUS initialize() {',
        (HERE/'owner-lifetime.cpp.inc').read_text()+'\n    NV_STATUS initialize() {')
    boot = once(boot, '        NV_STATUS status = NV_OK;\n        const auto cancellation =',
        '        NV_STATUS status = NV_OK;\n'
        '        // No disable, queue/timer stop, unbind, backing release, PM ack\n'
        '        // or member destructor is authorized after this lifetime starts.\n'
        '        if (diagnosticLifetimeHeld || transport.hardwareDmaLifetimeHeld()) {\n'
        '            state.quarantined = true; state.cleanupStatus = NV_ERR_IN_USE;\n'
        '            return NV_ERR_IN_USE;\n'
        '        }\n'
        '        const auto cancellation =')
    boot = once(boot, 'NV_STATUS Owner::initialize() {',
        'NV_STATUS Owner::retainDiagnosticLifetime() {\n'
        '    return impl_ ? impl_->dispatcher.invoke(RetainDiagnosticLifetime) : NV_STATUS(NV_ERR_INVALID_STATE);\n'
        '}\n'
        'const void *Owner::retainedDiagnosticOwner() const {\n'
        '    return impl_ && impl_->read().diagnosticLifetimeRetained ? impl_ : nullptr;\n'
        '}\n'
        'NV_STATUS Owner::initialize() {')
    out[BOOT] = boot
    header = out[HEADER]
    header = once(header, 'class IOPCIDevice;',
        '/* Actual permanent module-lifetime pin count. There is no reset API. */\n'
        'extern "C" NvU32 s540GspDiagnosticLifetimePinCount(void);\n\nclass IOPCIDevice;')
    header = once(header, '    NvU64 workerThread;',
        '    NvU64 workerThread;\n'
        '    bool diagnosticLifetimeRetained, hardwareDmaLifetimeHeld;\n'
        '    NvU64 hardwareDmaGeneration;')
    header = once(header, '    NV_STATUS initialize();',
        '    // Must precede every prospective original entry. Successful acquisition\n'
        '    // permanently retains the actual operational Impl/session until reboot.\n'
        '    // It does not begin the first-record epoch or admit original execution.\n'
        '    NV_STATUS retainDiagnosticLifetime();\n'
        '    // Exact stable Impl identity; null until a real Session hold exists.\n'
        '    const void *retainedDiagnosticOwner() const;\n'
        '    NV_STATUS initialize();')
    out[HEADER] = header
    out[POWER_HEADER] = once(out[POWER_HEADER], '    Snapshot snapshot() const;\n#if',
        '    Snapshot snapshot() const;\n'
        '    // Callback-safe pull of the original guarded monotonic PM event only.\n'
        '    // No registry/provider query, RM lock, allocation or worker dispatch.\n'
        '    NvU64 revocationEventNs() const;\n#if')
    out[POWER_HEADER] = once(out[POWER_HEADER], '    void revocationObserved(NvU64 eventNs);',
        '    void revocationObserved(NvU64 eventNs);\n'
        '    NvU64 revocationEventNs() const;')
    out[POWER] = once(out[POWER],
        '    if (state_.revoked && !state_.revokedAtNs) state_.revokedAtNs = eventNs;',
        '    if (state_.revoked && !__atomic_load_n(&state_.revokedAtNs, __ATOMIC_ACQUIRE))\n'
        '        __atomic_store_n(&state_.revokedAtNs, eventNs, __ATOMIC_RELEASE);')
    out[POWER] = once(out[POWER], 'void Protocol::completed() {',
        'NvU64 Protocol::revocationEventNs() const {\n'
        '    return __atomic_load_n(&state_.revokedAtNs, __ATOMIC_ACQUIRE);\n'
        '}\nvoid Protocol::completed() {')
    out[POWER] = once(out[POWER], 'Snapshot Lease::snapshot() const {',
        (HERE/'power-event.cpp.inc').read_text()+'\nSnapshot Lease::snapshot() const {')
    return out


def loader_transform(text):
    text = once(text, '#include <kern/task.h>',
        '#include <kern/task.h>\n'
        'extern "C" NvU32 s540GspDiagnosticLifetimePinCount(void);')
    text = once(text, 'extern "C" kern_return_t s540ProspectiveModuleStopBackend(void) {',
        'extern "C" kern_return_t s540ProspectiveModuleStopBackend(void) {\n'
        '    // Permanent actual Owner/Session holds also pin this image text.\n'
        '    if (s540GspDiagnosticLifetimePinCount()) return KERN_FAILURE;')
    text = once(text, 'void S540ProspectiveLoaderControl::stop(IOService *provider) {',
        'void S540ProspectiveLoaderControl::stop(IOService *provider) {\n'
        '    // IOKit stop has no status result. Preserve our service state and\n'
        '    // refuse module stop while its actual operational session is retained.\n'
        '    if (s540GspDiagnosticLifetimePinCount()) return;')
    return text


def original_transforms(values):
    if set(values) != set(ORIGINAL_INPUTS):
        raise ValueError('Exact original GSP TX source set required')
    text = values[TX]
    if hashlib.sha256(text.encode()).hexdigest() != TX_INPUT_SHA256:
        raise ValueError('Composed original GSP TX source changed')
    text = once(text,
        '        while (NV_TRUE)\n        {\n            // Must get the buffers one at a time, since they could wrap.',
        '        while (NV_TRUE)\n        {\n'
        '            nvStatus = s540GspCancellationCheckGpu(pGpu);\n'
        '            if (nvStatus != NV_OK) goto done;\n'
        '            // Must get the buffers one at a time, since they could wrap.')
    text = once(text, '    nRet = msgqTxSubmitBuffers(pMQI->hQueue, nElements);',
        '    // GetWriteBuffer has not advanced TX_HEAD: partially filled free\n'
        '    // slots remain unpublished. Retain them and return the real status\n'
        '    // rather than publishing a new command after an observed revocation.\n'
        '    nvStatus = s540GspCancellationCheckGpu(pGpu);\n'
        '    if (nvStatus != NV_OK) goto done;\n'
        '    nRet = msgqTxSubmitBuffers(pMQI->hQueue, nElements);')
    return {TX: text}


def prepare(composition, output):
    composition = composition.resolve(strict=True)
    manifest = json.loads(composition.read_text())
    if manifest.get('status') != 'materialized-source-only':
        raise ValueError('Complete source-only composition required')
    profiles = manifest.get('fixed_source_profiles', {})
    if not all(profiles.get(name) for name in ('retained_diagnostic', 'retained_backends', 'global_epoch')):
        raise ValueError('Retained diagnostic/backends and permanent global epoch composition required')
    project = (composition.parent/manifest['project']).resolve(strict=True)
    output = output.resolve()
    if output.exists() or output.is_relative_to(project) or project.is_relative_to(output):
        raise ValueError('Fresh output outside input project required')
    values, inputs = {}, {}
    for name in INPUTS:
        path = project/name
        expected = manifest['project_files'][name]['sha256']
        if path.is_symlink() or sha(path) != expected:
            raise ValueError('Composed session input changed: '+name)
        inputs[name] = expected
        values[name] = path.read_text()
    changed = transforms(values)
    original_values, original_inputs = {}, {}
    for name in ORIGINAL_INPUTS:
        path = composition.parent/'source'/name
        expected = manifest['original_files'][name]['sha256']
        if path.is_symlink() or sha(path) != expected:
            raise ValueError('Composed original TX input changed: '+name)
        original_values[name] = path.read_text()
        original_inputs[name] = expected
    changed_original = original_transforms(original_values)
    output.mkdir(parents=True)
    rows = {}
    for name, value in changed.items():
        path = output/'project'/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value)
        rows[name] = {'source': path.relative_to(output).as_posix(),
                      'input_sha256': inputs[name], 'output_sha256': sha(path)}
    if any(sha(project/name) != digest for name, digest in inputs.items()):
        raise ValueError('Input changed during session preparation')
    original_rows = {}
    for name, value in changed_original.items():
        path = output/'source'/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value)
        original_rows[name] = {'source':path.relative_to(output).as_posix(),
            'input_sha256':original_inputs[name], 'output_sha256':sha(path)}
    if any(sha(composition.parent/'source'/name) != digest for name,digest in original_inputs.items()):
        raise ValueError('Original TX input changed during session preparation')
    report = {'format': 1, 'component': 'permanent-operational-owner-session-lifetime',
        'sources': rows, 'composition_sha256': sha(composition),
        'original_sources': original_rows,
        'transform_source_sha256': {path.relative_to(HERE).as_posix(): sha(path)
            for path in sorted(HERE.rglob('*')) if path.is_file() and '__pycache__' not in path.parts},
        'loader_transform_required': True, 'module_pin_has_final_release': False,
        'stop_receipt_issued': False, 'pm_deadline_extended': False,
        'physical_reclamation_authorized': False, 'hardware_admission': False,
        'original_entry_admission': False, 'kernel_gate_preserved': True}
    (output/'project-successor.json').write_text(json.dumps(report, indent=2, sort_keys=True)+'\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--composition', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    prepare(args.composition, args.output)
