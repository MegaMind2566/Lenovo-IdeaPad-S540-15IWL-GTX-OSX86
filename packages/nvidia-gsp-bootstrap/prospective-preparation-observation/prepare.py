#!/usr/bin/env python3
"""Preserve real preparation observations before the unchanged failure cleanup."""
from pathlib import Path
import hashlib
import importlib.util
import json
import sys
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DIRECTORY = 'packages/nvidia-gsp-bootstrap/prospective-preparation-observation'
BOOT = 'packages/nvidia-gsp-bootstrap/src/S540NvidiaGspBootstrap.cpp'
HEADER = BOOT[:-3] + 'hpp'
_spec = importlib.util.spec_from_file_location('s540_preparation_power_observation', HERE / 'power.py')
power = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = power
_spec.loader.exec_module(power)
INPUTS = (BOOT, HEADER, *power.INPUTS)
ORIGINAL_INPUTS = ()
COMPANIONS = {DIRECTORY + '/S540PreparationObservation.h': HERE / 'S540PreparationObservation.h'}
PROJECT_UNITS = ()
EXPORTS = {}
INCLUDE_DIRECTORIES = (DIRECTORY,)
COMPILE_DEFINITIONS = {}
SOURCE_FILES = ('BASE-SHA256.json', 'SOURCE-CONTRACT.json', 'check.py', 'power.py',
                'tests/check_owner.cpp.inc', 'check_power.py', 'tests/check_power.cpp')
BASE_SHA256 = json.loads((HERE / 'BASE-SHA256.json').read_text())
sys.path.insert(0, str(ROOT / 'packages/nvidia-gsp-bootstrap/cancellation'))
from prepare_wait_candidates import function_span


def once(text, before, after):
    if text.count(before) != 1:
        raise ValueError('Exact preparation observation anchor changed: ' + before[:120])
    return text.replace(before, after)


def observe_owner(boot, header):
    header = once(header, '#include "../../nvidia-device-transport/src/S540NvidiaDeviceTransport.hpp"',
        '#include "../../nvidia-device-transport/src/S540NvidiaDeviceTransport.hpp"\n'
        '#include "../prospective-preparation-observation/S540PreparationObservation.h"')
    header = once(header, '    NvU32 blockedGates;',
        '    NvU32 blockedGates;\n    S540PreparationObservation preparation;')
    boot = once(boot, 'struct Owner::Impl {', (HERE / 'owner-observation.cpp.inc').read_text() + '\nstruct Owner::Impl {')
    boot = once(boot, 'struct Owner::Impl {', 'struct Owner::Impl {\n'
        '    S540PreparationObservation preparationDispatchFallback{};\n'
        '    void observePreparationDispatchReturn(const S540PreparationObservation &setup, NV_STATUS status) {\n'
        '        if (status == NV_OK || s540Darwin_os_acquire_mutex(snapshotGuard) != NV_OK) return;\n'
        '        if (!(published.preparation.observedMask & S540_PREP_OBS_FIRST_FAILURE)) {\n'
        '            preparationDispatchFallback = setup;\n'
        '            (void)s540PreparationFailed(preparationDispatchFallback, status);\n'
        '        }\n'
        '        s540Darwin_os_release_mutex(snapshotGuard);\n'
        '    }')
    boot = once(boot, '        result = published; s540Darwin_os_release_mutex(snapshotGuard);',
        '        result = published;\n'
        '        if ((preparationDispatchFallback.observedMask & S540_PREP_OBS_FIRST_FAILURE) &&\n'
        '            !(result.preparation.observedMask & S540_PREP_OBS_FIRST_FAILURE))\n'
        '            result.preparation = preparationDispatchFallback;\n'
        '        s540Darwin_os_release_mutex(snapshotGuard);')
    boot = once(boot, '''    NV_STATUS failed(NV_STATUS failure) {
        state.preparationStatus = failure;''', '''    NV_STATUS failed(NV_STATUS failure) {
        // Preserve first failure and guarded PM metadata before unchanged cleanup.
        (void)s540PreparationFailed(state.preparation, failure);
        state.preparation.power = power.preparationObservation();
        if (state.preparation.power.format == 1)
            state.preparation.observedMask |= S540_PREP_OBS_POWER;
        state.preparationStatus = failure;''')
    first, last = function_span(boot, 'prepare')
    body = boot[first:last]
    body = once(body, '        state.ownsResources = true;',
        '        state.ownsResources = true;\n        s540PreparationStage(state.preparation, S540_PREP_POWER_START);')
    body = once(body, '''        if (status != NV_OK) return failed(status);
        status = platform.initialize(provider);''', '''        state.preparation.power = power.preparationObservation();
        if (state.preparation.power.format == 1)
            state.preparation.observedMask |= S540_PREP_OBS_POWER;
        if (status != NV_OK) return failed(status);
        s540PreparationCompleted(state.preparation);
        status = platform.initialize(provider);''')
    # Each completion is recorded only AFTER the original success/refusal test.
    # Call expressions, original tests, return values and cleanup stay literal.
    calls = (
        ('status = platform.initialize(provider);\n        if (status != NV_OK) return failed(status);', 'PLATFORM_INITIALIZE'),
        ('status = s540GlobalRmHostInitialize(&hostFacts); if (status != NV_OK) return failed(status);', 'HOST_INITIALIZE'),
        ('status = transport.setPciSegment(deviceFacts.segment); if (status != NV_OK) return failed(status);', 'PCI_SEGMENT'),
        ('status = s540GspContextCreate(&deviceFacts, &context); if (status != NV_OK) return failed(status);', 'CONTEXT_CREATE'),
        ('status = s540GspContextSetDetacher(context, &detacher); if (status != NV_OK) return failed(status);', 'CONTEXT_DETACHER'),
        ('status = s540GspCancellationBind(nv, &token); if (status != NV_OK) return failed(status);', 'CANCELLATION_BIND'),
        ('status = power.coupleCancellation(nv, token);\n        if (status != NV_OK) return failed(status);', 'POWER_CANCELLATION'),
        ('status = platform.bindState(nv); if (status != NV_OK) return failed(status);', 'PLATFORM_BIND'),
        ('status = S540NvidiaDeviceTransport::bindRmDevice(&transport, nv, dma); if (status != NV_OK) return failed(status);', 'RM_BIND'),
        ('gsp = s540GlobalRmHostAllocate(images.gspBytes); if (!gsp) return failed(NV_ERR_NO_MEMORY);', 'ALLOCATE_GSP'),
        ('ucodes = s540GlobalRmHostAllocate(images.ucodesBytes); if (!ucodes) return failed(NV_ERR_NO_MEMORY);', 'ALLOCATE_UCODES'),
        ('status = firmware.initialize(nv, thread, gsp, images.gspBytes, ucodes, images.ucodesBytes);\n        if (status != NV_OK) return failed(status);', 'FIRMWARE_STORE'),
        ('status = S540NvidiaGspFirmware::bind(&firmware); if (status != NV_OK) return failed(status);', 'FIRMWARE_BIND'),
        ('status = s540GspTimersBind(nv); if (status != NV_OK) return failed(status);', 'TIMERS_BIND'),
    )
    for original, stage in calls:
        body = once(body, '        ' + original,
            '        s540PreparationStage(state.preparation, S540_PREP_' + stage + ');\n        ' + original +
            '\n        s540PreparationCompleted(state.preparation);')
    host = '        status = platform.collect(&hostFacts); if (status != NV_OK) return failed(status);'
    body = once(body, host, '''        s540PreparationStage(state.preparation, S540_PREP_HOST_FACTS);
        status = platform.collect(&hostFacts);
        if (status == NV_OK || status == NV_ERR_NOT_READY) {
            state.preparation.hostKnown = hostFacts.known;
            state.preparation.hostMissing = S540_GLOBAL_FACT_ALL & ~hostFacts.known;
            state.preparation.observedMask |= S540_PREP_OBS_HOST_FACTS;
        }
        if (status != NV_OK) return failed(status);
        s540PreparationCompleted(state.preparation);''')
    body = once(body, '        status = platform.collectDeviceFacts(&deviceFacts); if (status != NV_OK) return failed(status);',
        '''        s540PreparationStage(state.preparation, S540_PREP_DEVICE_FACTS);
        status = platform.collectDeviceFacts(&deviceFacts);
        // These are the already computed final predicates, not new PCI reads.
        if (status == NV_OK || status == NV_ERR_NOT_READY) {
            state.preparation.deviceObserved = S540_PREP_DEVICE_ALL;
            state.preparation.devicePredicates =
                (deviceFacts.segmentKnown ? NvU32(S540_PREP_DEVICE_SEGMENT) : 0U) |
                (deviceFacts.pciConfigurationRead ? NvU32(S540_PREP_DEVICE_PCI) : 0U) |
                (deviceFacts.barsVerified ? NvU32(S540_PREP_DEVICE_BARS) : 0U) |
                (deviceFacts.poweredD0 ? NvU32(S540_PREP_DEVICE_D0) : 0U) |
                (deviceFacts.intelConsoleVerified ? NvU32(S540_PREP_DEVICE_INTEL_CONSOLE) : 0U) |
                (deviceFacts.nvidiaConsoleExcluded ? NvU32(S540_PREP_DEVICE_NVIDIA_EXCLUDED) : 0U) |
                (deviceFacts.noCoherentGpuMemoryProfile ? NvU32(S540_PREP_DEVICE_NO_COHERENT_GPU_MEMORY) : 0U);
            state.preparation.observedMask |= S540_PREP_OBS_DEVICE_FACTS;
        }
        if (status != NV_OK) return failed(status);
        s540PreparationCompleted(state.preparation);''')
    body = once(body, '        if (!copyText(osVersion, sizeof(osVersion), hostFacts.osVersion) ||',
        '        s540PreparationStage(state.preparation, S540_PREP_HOST_STRINGS);\n'
        '        if (!copyText(osVersion, sizeof(osVersion), hostFacts.osVersion) ||')
    body = once(body, '        hostFacts.osVersion = osVersion;',
        '        s540PreparationCompleted(state.preparation);\n        hostFacts.osVersion = osVersion;')
    body = once(body, '#if defined(KERNEL)\n        status = transport.start(provider, service);',
        '        s540PreparationStage(state.preparation, S540_PREP_TRANSPORT_START);\n'
        '#if defined(KERNEL)\n        status = transport.start(provider, service);')
    body = once(body, '#endif\n        if (status != NV_OK) return failed(status);\n        s540PreparationStage(state.preparation, S540_PREP_PCI_SEGMENT);',
        '#endif\n        if (status != NV_OK) return failed(status);\n'
        '        s540PreparationCompleted(state.preparation);\n'
        '        s540PreparationStage(state.preparation, S540_PREP_PCI_SEGMENT);')
    for expression, stage in (('transport.requiresDmaRemap(required)', 'DMA_REMAP'),
                              ('S540NvidiaDeviceTransport::queryRmDmaRemap(nv, required)', 'RM_DMA_REMAP')):
        original = '        status = ' + expression + ';\n        if (status != NV_OK || !required) return failed(status == NV_OK ? NV_STATUS(NV_ERR_NOT_SUPPORTED) : status);'
        body = once(body, original, '        s540PreparationStage(state.preparation, S540_PREP_' + stage + ');\n' + original +
            '\n        s540PreparationCompleted(state.preparation);')
    body = once(body, '        const auto powerState = power.snapshot();',
        '        s540PreparationStage(state.preparation, S540_PREP_POWER_REVOKE_CHECK);\n        const auto powerState = power.snapshot();')
    body = once(body, '        s540PreparationStage(state.preparation, S540_PREP_PLATFORM_BIND);',
        '        s540PreparationCompleted(state.preparation);\n        s540PreparationStage(state.preparation, S540_PREP_PLATFORM_BIND);')
    body = once(body, '        copyBytes(gsp, images.gsp, images.gspBytes);',
        '        s540PreparationStage(state.preparation, S540_PREP_COPY_FIRMWARE);\n        copyBytes(gsp, images.gsp, images.gspBytes);')
    body = once(body, '        state.firmwareCopied = true;',
        '        state.firmwareCopied = true;\n        s540PreparationCompleted(state.preparation);')
    body = once(body, '        if (power.status() != NV_OK) return failed(NV_ERR_NOT_READY);',
        '        s540PreparationStage(state.preparation, S540_PREP_FINAL_POWER);\n'
        '        if (power.status() != NV_OK) return failed(NV_ERR_NOT_READY);\n'
        '        state.preparation.power = power.preparationObservation();\n'
        '        if (state.preparation.power.format == 1) state.preparation.observedMask |= S540_PREP_OBS_POWER;\n'
        '        s540PreparationCompleted(state.preparation);')
    body = once(body, '        return NV_OK;',
        '        s540PreparationStage(state.preparation, S540_PREP_COMPLETE);\n'
        '        s540PreparationCompleted(state.preparation);\n        return NV_OK;')
    boot = boot[:first] + body + boot[last:]
    # Facade setup is externally serialized. Copy its real observations into
    # Impl before starting the worker, and back before any existing deletion.
    first, last = function_span(boot, 'Owner::prepareCommon')
    body = boot[first:last]
    body = once(body, '    NvU64 caller = 0;', '    s540PreparationReset(state_.preparation);\n'
        '    s540PreparationStage(state_.preparation, S540_PREP_VALIDATE);\n    NvU64 caller = 0;')
    for status in ('NV_ERR_INVALID_STATE', 'NV_ERR_STATE_IN_USE', 'NV_ERR_INVALID_ARGUMENT'):
        body = once(body, 'return ' + status + ';', 'return s540PreparationFailed(state_.preparation, ' + status + ');')
    body = once(body, '    if (!S540NvidiaFirmwareAssets::verifyPair',
        '    s540PreparationCompleted(state_.preparation);\n'
        '    s540PreparationStage(state_.preparation, S540_PREP_VERIFY_FIRMWARE);\n'
        '    if (!S540NvidiaFirmwareAssets::verifyPair')
    body = once(body, 'return NV_ERR_INVALID_DATA;', 'return s540PreparationFailed(state_.preparation, NV_ERR_INVALID_DATA);')
    body = once(body, '    void *memory = allocateOwner(sizeof(Impl)); if (!memory) return NV_ERR_NO_MEMORY;',
        '    s540PreparationCompleted(state_.preparation);\n'
        '    s540PreparationStage(state_.preparation, S540_PREP_ALLOCATE_OWNER);\n'
        '    void *memory = allocateOwner(sizeof(Impl)); if (!memory) return s540PreparationFailed(state_.preparation, NV_ERR_NO_MEMORY);')
    body = once(body, '    impl_ = new (S540BootstrapPlacement{memory}) Impl;',
        '    impl_ = new (S540BootstrapPlacement{memory}) Impl;\n'
        '    s540PreparationCompleted(state_.preparation);\n'
        '    impl_->state.preparation = state_.preparation;\n'
        '    s540PreparationStage(impl_->state.preparation, S540_PREP_SNAPSHOT_MUTEX);')
    body = once(body, '    if (status != NV_OK) { impl_->~Impl();',
        '    if (status != NV_OK) { (void)s540PreparationFailed(impl_->state.preparation, status);\n'
        '        state_.preparation = impl_->state.preparation; impl_->~Impl();')
    body = once(body, '    impl_->provider = provider;',
        '    s540PreparationCompleted(impl_->state.preparation);\n    impl_->provider = provider;')
    body = once(body, '    if (status == NV_OK) status = impl_->dispatcher.start(Impl::action, impl_);',
        '    s540PreparationStage(impl_->state.preparation, S540_PREP_DISPATCHER_START);\n'
        '    if (status == NV_OK) status = impl_->dispatcher.start(Impl::action, impl_);')
    body = once(body, '    if (status != NV_OK) {\n        s540Darwin_os_free_mutex',
        '    if (status != NV_OK) {\n        (void)s540PreparationFailed(impl_->state.preparation, status);\n'
        '        state_.preparation = impl_->state.preparation;\n        s540Darwin_os_free_mutex')
    body = once(body, '    status = impl_->dispatcher.invoke(Prepare);',
        '    s540PreparationCompleted(impl_->state.preparation);\n'
        '    s540PreparationStage(impl_->state.preparation, S540_PREP_DISPATCH_PREPARE);\n'
        '    state_.preparation = impl_->state.preparation;\n'
        '    status = impl_->dispatcher.invoke(Prepare);\n'
        '    impl_->observePreparationDispatchReturn(state_.preparation, status);')
    boot = boot[:first] + body + boot[last:]
    return boot, header


def transforms(values):
    if set(values) != set(INPUTS) or set(BASE_SHA256) != set(INPUTS):
        raise ValueError('Exact B3 post-retained-stop observation inputs required')
    for name, text in values.items():
        if hashlib.sha256(text.encode()).hexdigest() != BASE_SHA256[name]:
            raise ValueError('Preparation observation prerequisite changed: ' + name)
    out = dict(values)
    out[BOOT], out[HEADER] = observe_owner(out[BOOT], out[HEADER])
    changed = power.transforms({name: out[name] for name in power.INPUTS})
    out.update(changed)
    return out
