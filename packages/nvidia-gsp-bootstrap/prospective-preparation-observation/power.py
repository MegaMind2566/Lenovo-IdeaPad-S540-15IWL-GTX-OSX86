#!/usr/bin/env python3
"""Observation-only transforms of the exact B3 PM implementation.

Every PM/registry/provider call and every original return decision is preserved.
Only existing results and guarded Protocol fields enter the diagnostic record.
"""
from pathlib import Path
import hashlib

HERE = Path(__file__).resolve().parent
POWER = 'packages/nvidia-gsp-bootstrap/platform/S540NvidiaGspPower.cpp'
HEADER = POWER[:-3] + 'hpp'
INPUTS = (POWER, HEADER)
BASE_SHA256 = {
    POWER: '8d56d045d40048ef843db036e3539a2f008ca249aabe7052f9f87f4d62596a77',
    HEADER: '07daaace47e94ed9c7d5dbde4884ce4d4b58df8c59c2bdd95c98c7e486c2ca4b',
}

PROTOCOL = r'''
void Protocol::preparationProtocol(const Snapshot &value) {
    const NvU32 bits = S540_PREP_PM_FLAG_ON_REQUESTED | S540_PREP_PM_FLAG_ON_SET |
        S540_PREP_PM_FLAG_ON_COMPLETED | S540_PREP_PM_FLAG_REVOKED |
        S540_PREP_PM_FLAG_ACK_PENDING | S540_PREP_PM_FLAG_ACK_SENT | S540_PREP_PM_FLAG_STOPPED;
    preparation_.flags &= ~bits;
    if (value.onRequested) preparation_.flags |= S540_PREP_PM_FLAG_ON_REQUESTED;
    if (value.onSet) preparation_.flags |= S540_PREP_PM_FLAG_ON_SET;
    if (value.onCompleted) preparation_.flags |= S540_PREP_PM_FLAG_ON_COMPLETED;
    if (value.revoked) preparation_.flags |= S540_PREP_PM_FLAG_REVOKED;
    if (value.acknowledgementPending) preparation_.flags |= S540_PREP_PM_FLAG_ACK_PENDING;
    if (value.acknowledgementSent) preparation_.flags |= S540_PREP_PM_FLAG_ACK_SENT;
    if (value.stopped) preparation_.flags |= S540_PREP_PM_FLAG_STOPPED;
    preparation_.observedMask |= S540_PREP_PM_OBS_PROTOCOL;
}
void Protocol::preparationBegin(NvU32 stage) {
    preparation_.format = 1; preparation_.bytes = sizeof(preparation_);
    preparation_.stage = stage;
    preparation_.rawIOReturn = preparation_.rawIOReturnValid = 0;
    preparation_.observedMask &= ~NvU32(S540_PREP_PM_OBS_RAW_IOR);
    preparationProtocol(state_);
}
void Protocol::preparationResult(NvU32 stage, NV_STATUS status, NvU32 raw, NvBool rawValid) {
    preparationBegin(stage);
    preparation_.rawIOReturn = raw; preparation_.rawIOReturnValid = rawValid;
    if (rawValid) preparation_.observedMask |= S540_PREP_PM_OBS_RAW_IOR;
    if (status == NV_OK) preparation_.lastCompleted = stage;
    else if (!preparation_.firstFailureStage) {
        preparation_.firstFailureStage = stage; preparation_.firstFailureStatus = status;
        preparation_.firstFailureRawIOReturn = raw;
        preparation_.firstFailureRawIOReturnValid = rawValid;
    }
}
void Protocol::preparationPredicate(NvU32 stage, NvU32 bit, bool value) {
    preparationResult(stage, value ? NV_STATUS(NV_OK) : NV_STATUS(NV_ERR_NOT_READY), 0, NV_FALSE);
    preparation_.observedMask |= bit;
    preparation_.flags = (preparation_.flags & ~bit) | (value ? bit : 0U);
    if (value && stage == S540_PREP_POWER_WAIT_ACTIVE)
        preparationResult(S540_PREP_POWER_COMPLETE, NV_OK, 0, NV_FALSE);
}
void Protocol::preparationWaitResult(int value) {
    preparation_.waitResult = NvU32(value); preparation_.waitResultValid = 1;
    preparation_.observedMask |= S540_PREP_PM_OBS_WAIT_RESULT;
}
void Protocol::preparationFinalStatus(const Snapshot &value, bool accepted) {
    preparationResult(S540_PREP_POWER_FINAL_STATUS,
        accepted ? NV_STATUS(NV_OK) : NV_STATUS(NV_ERR_NOT_READY), 0, NV_FALSE);
    const NvU32 facts = S540_PREP_PM_OBS_READY | S540_PREP_PM_OBS_DOMAIN | S540_PREP_PM_OBS_ACTIVE;
    preparation_.observedMask &= ~facts; preparation_.flags &= ~facts;
    const bool ready = value.onRequested && value.onCompleted && !value.revoked && !value.stopped;
    preparation_.observedMask |= S540_PREP_PM_OBS_READY | S540_PREP_PM_OBS_DOMAIN;
    if (ready) preparation_.flags |= S540_PREP_PM_OBS_READY;
    if (value.domainJoined) preparation_.flags |= S540_PREP_PM_OBS_DOMAIN;
    // isInactive was evaluated by the ORIGINAL boolean only after this prefix.
    if (ready && value.domainJoined) {
        preparation_.observedMask |= S540_PREP_PM_OBS_ACTIVE;
        if (accepted) preparation_.flags |= S540_PREP_PM_OBS_ACTIVE;
    }
    preparationProtocol(value);
}
S540PreparationPowerObservation Protocol::preparationObservation() const { return preparation_; }
'''

KERNEL = r'''
// These helpers only copy CPU metadata under the existing PM service guard.
// No IOKit/PM/PCI observation is repeated by the diagnostic path.
static void preparationBegin(S540NvidiaGspPowerService *service, NvU32 stage) {
    IOLockLock(service->guard); service->protocol.preparationBegin(stage); IOLockUnlock(service->guard);
}
static void preparationResult(S540NvidiaGspPowerService *service, NvU32 stage,
    NV_STATUS status, NvU32 raw = 0, NvBool rawValid = NV_FALSE) {
    IOLockLock(service->guard);
    service->protocol.preparationResult(stage, status, raw, rawValid);
    IOLockUnlock(service->guard);
}
static bool preparationPredicate(S540NvidiaGspPowerService *service, NvU32 stage,
    NvU32 bit, bool value) {
    IOLockLock(service->guard); service->protocol.preparationPredicate(stage, bit, value); IOLockUnlock(service->guard);
    return value;
}
'''

LEASE = r'''
S540PreparationPowerObservation Lease::preparationObservation() const {
    // The ordinary owner captures this before cleanup. Live metadata is guarded;
    // after completed destruction only the already copied final record is read.
    if (!impl_) return preparationFinal_;
#if defined(KERNEL)
    auto *service = impl_->service;
    IOLockLock(service->guard);
    const auto result = service->protocol.preparationObservation();
    IOLockUnlock(service->guard); return result;
#else
    std::lock_guard<std::mutex> lock(impl_->guard);
    return impl_->protocol.preparationObservation();
#endif
}
'''


def once(text, before, after):
    if text.count(before) != 1:
        raise ValueError('Exact PM observation anchor changed: ' + before[:100])
    return text.replace(before, after)


def transforms(values):
    if set(values) != set(INPUTS): raise ValueError('Exact B3 Power sources required')
    for name, text in values.items():
        if hashlib.sha256(text.encode()).hexdigest() != BASE_SHA256[name]:
            raise ValueError('Frozen B3 PM source differs: ' + name)
    result = dict(values)
    header = once(result[HEADER], 'class IOPCIDevice;',
        '#include "../prospective-preparation-observation/S540PreparationObservation.h"\nclass IOPCIDevice;')
    header = once(header, '    void requested();',
        '    // Internal metadata methods require the existing Power guard.\n'
        '    void preparationBegin(NvU32);\n'
        '    void preparationResult(NvU32, NV_STATUS, NvU32, NvBool);\n'
        '    void preparationPredicate(NvU32, NvU32, bool);\n'
        '    void preparationWaitResult(int);\n'
        '    void preparationFinalStatus(const Snapshot &, bool);\n'
        '    S540PreparationPowerObservation preparationObservation() const;\n'
        '    void requested();')
    header = once(header, '    Snapshot state_;',
        '    Snapshot state_;\n    S540PreparationPowerObservation preparation_{};\n'
        '    void preparationProtocol(const Snapshot &);')
    header = once(header, '    NV_STATUS status() const;',
        '    NV_STATUS status() const;\n'
        '    // Ordinary lifecycle owner only; copies metadata and performs no query.\n'
        '    S540PreparationPowerObservation preparationObservation() const;')
    header = once(header, '    Snapshot final_;',
        '    Snapshot final_;\n    S540PreparationPowerObservation preparationFinal_{};')
    result[HEADER] = header
    power = once(result[POWER], 'void Protocol::requested() {', PROTOCOL + '\nvoid Protocol::requested() {')
    power = once(power, 'constexpr IOReturn kDropDeadlineUs = 30000000;',
        'constexpr IOReturn kDropDeadlineUs = 30000000;\n' + KERNEL)
    power = once(power, '        if (!attach(provider)) return false;',
        '        preparationBegin(this, S540_PREP_POWER_JOIN_ATTACH);\n'
        '        const bool didAttach = attach(provider);\n'
        '        preparationResult(this, S540_PREP_POWER_JOIN_ATTACH, didAttach ? NV_STATUS(NV_OK) : NV_STATUS(NV_ERR_NOT_READY));\n'
        '        if (!didAttach) return false;')
    power = once(power, '        if (!IOService::start(provider)) return false;',
        '        preparationBegin(this, S540_PREP_POWER_JOIN_SERVICE_START);\n'
        '        const bool didStart = IOService::start(provider);\n'
        '        preparationResult(this, S540_PREP_POWER_JOIN_SERVICE_START, didStart ? NV_STATUS(NV_OK) : NV_STATUS(NV_ERR_NOT_READY));\n'
        '        if (!didStart) return false;')
    power = once(power, '        PMinit(); pmInitialized = true;',
        '        preparationBegin(this, S540_PREP_POWER_JOIN_PM_INIT);\n'
        '        PMinit(); pmInitialized = true;\n'
        '        preparationResult(this, S540_PREP_POWER_JOIN_PM_INIT, NV_OK);')
    for stage, call, variable in (
        ('JOIN_REGISTER_DRIVER', 'registerPowerDriver(this, states, 2)', 'registered'),
        ('JOIN_REQUEST_OFF', 'changePowerStateTo(0)', 'offRequested'),
        ('JOIN_ADD_POWER_CHILD', 'provider->addPowerChild(this)', 'powerChild'),
        ('JOIN_REQUEST_ON_PRIV', 'changePowerStateToPriv(1)', 'onRequested')):
        power = once(power, '        if (' + call + ' != kIOReturnSuccess) return false;',
            '        preparationBegin(this, S540_PREP_POWER_' + stage + ');\n'
            '        const IOReturn ' + variable + ' = ' + call + ';\n'
            '        preparationResult(this, S540_PREP_POWER_' + stage + ', ' + variable + ' == kIOReturnSuccess ?\n'
            '            NV_STATUS(NV_OK) : NV_STATUS(NV_ERR_NOT_READY), NvU32(' + variable + '), NV_TRUE);\n'
            '        if (' + variable + ' != kIOReturnSuccess) return false;')
    power = once(power, '        IOLockLock(guard); protocol.requested(); IOLockUnlock(guard);',
        '        IOLockLock(guard); protocol.preparationBegin(S540_PREP_POWER_JOIN_MARK_REQUESTED);\n'
        '        protocol.requested(); protocol.preparationResult(S540_PREP_POWER_JOIN_MARK_REQUESTED, NV_OK, 0, NV_FALSE); IOLockUnlock(guard);')
    power = once(power, '        IOLockLock(guard);\n        while (!protocol.ready()',
        '        IOLockLock(guard); protocol.preparationBegin(S540_PREP_POWER_WAIT_READY);\n        while (!protocol.ready()')
    power = once(power, '            const int result = IOLockSleepDeadline(guard, this, deadline, THREAD_UNINT);',
        '            const int result = IOLockSleepDeadline(guard, this, deadline, THREAD_UNINT);\n'
        '            protocol.preparationWaitResult(result);')
    power = once(power,
        '        return ready && exactDomain() && !endpoint->isInactive() ? NV_STATUS(NV_OK) : NV_STATUS(NV_ERR_NOT_READY);',
        '        return preparationPredicate(this, S540_PREP_POWER_WAIT_READY, S540_PREP_PM_OBS_READY, ready) &&\n'
        '            preparationPredicate(this, S540_PREP_POWER_WAIT_DOMAIN, S540_PREP_PM_OBS_DOMAIN, exactDomain()) &&\n'
        '            preparationPredicate(this, S540_PREP_POWER_WAIT_ACTIVE, S540_PREP_PM_OBS_ACTIVE, !endpoint->isInactive()) ?\n'
        '            NV_STATUS(NV_OK) : NV_STATUS(NV_ERR_NOT_READY);')
    power = once(power,
        '    return state.onRequested && state.onCompleted && state.domainJoined &&\n'
        '        !state.revoked && !state.stopped && !impl_->service->endpoint->isInactive() ? NV_STATUS(NV_OK) : NV_STATUS(NV_ERR_NOT_READY);',
        '    const bool accepted = state.onRequested && state.onCompleted && state.domainJoined &&\n'
        '        !state.revoked && !state.stopped && !impl_->service->endpoint->isInactive();\n'
        '    IOLockLock(impl_->service->guard);\n'
        '    impl_->service->protocol.preparationFinalStatus(state, accepted);\n'
        '    IOLockUnlock(impl_->service->guard);\n'
        '    return accepted ? NV_STATUS(NV_OK) : NV_STATUS(NV_ERR_NOT_READY);')
    power = once(power, '    final_ = impl_->service->snapshot(); final_.retained = false;',
        '    final_ = impl_->service->snapshot(); final_.retained = false;\n'
        '    preparationFinal_ = preparationObservation();')
    power = once(power, '        final_.nativeFixture = true;',
        '        final_.nativeFixture = true;\n'
        '        preparationFinal_ = impl_->protocol.preparationObservation();')
    power = once(power, 'NvU64 Lease::revocationEventNs() const {', LEASE + '\nNvU64 Lease::revocationEventNs() const {')
    result[POWER] = power
    return result
