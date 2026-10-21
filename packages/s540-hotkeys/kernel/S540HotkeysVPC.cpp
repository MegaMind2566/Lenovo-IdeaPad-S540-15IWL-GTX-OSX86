// SPDX-License-Identifier: GPL-2.0-only
#include "S540HotkeysVPC.hpp"
#include <IOKit/IOLib.h>
#include <IOKit/IOMessage.h>
#include <IOKit/acpi/IOACPITypes.h>
#include <IOKit/pwr_mgt/IOPM.h>
#include <kern/clock.h>
#include <libkern/libkern.h>

OSDefineMetaClassAndStructors(S540HotkeysVPC, IOService)

struct S540VPCTransport {
    S540HotkeysVPC *owner;
    bool operational() { return owner->operational(); }
    UInt64 nowNs() { return S540HotkeysVPC::nowNs(); }
    bool readRegister(UInt32 index, UInt32 &value) { return owner->readRegister(index, value); }
    bool writeRegister(UInt32 index, UInt32 value) { return owner->writeRegister(index, value); }
    void pause() { owner->pause(); }
};

static bool dictionaryNumber(OSDictionary *dictionary, const char *key, UInt64 value, unsigned bits = 64) {
    OSNumber *number = OSNumber::withNumber(value, bits);
    if (!number) return false;
    bool good = dictionary->setObject(key, number);
    number->release();
    return good;
}
static bool dictionaryString(OSDictionary *dictionary, const char *key, const char *value) {
    OSString *string = OSString::withCString(value);
    if (!string) return false;
    bool good = dictionary->setObject(key, string);
    string->release();
    return good;
}

bool S540HotkeysVPC::init(OSDictionary *dictionary) {
    if (!IOService::init(dictionary)) return false;
    _lock = IOLockAlloc();
    return _lock != nullptr;
}

UInt64 S540HotkeysVPC::nowNs() {
    AbsoluteTime absolute;
    UInt64 result = 0;
    clock_get_uptime(&absolute);
    absolutetime_to_nanoseconds(absolute, &result);
    return result;
}

bool S540HotkeysVPC::operational() {
    IOLockLock(_lock);
    // A requested power-off/unload stops new events immediately, but the current
    // serialized command may complete before the workloop acknowledges quiescence.
    bool allowed = !_fault && _transportAwake;
    IOLockUnlock(_lock);
    return allowed;
}

bool S540HotkeysVPC::competingClient() {
    if (_acpi->isOpen()) return true;
    OSIterator *iterator = _acpi->getClientIterator();
    if (!iterator) return true; // Failure to inspect ownership is a refusal.
    bool conflict = false;
    while (OSObject *object = iterator->getNextObject()) {
        IOService *client = OSDynamicCast(IOService, object);
        if (!client || client == this) continue;
        const char *name = client->getMetaClass()->getClassName();
        OSString *bundle = OSDynamicCast(OSString, client->getProperty("CFBundleIdentifier"));
        const char *identifier = bundle ? bundle->getCStringNoCopy() : "";
        if (!strcmp(name, "IdeaVPC") || !strcmp(name, "YogaVPC") || !strcmp(name, "S540HotkeysVPC") ||
            strstr(identifier, "YogaSMC") || strstr(identifier, "HotkeysVPC")) {
            conflict = true;
            break;
        }
    }
    iterator->release();
    return conflict;
}

bool S540HotkeysVPC::start(IOService *provider) {
    if (!IOService::start(provider)) return false;
    _acpi = OSDynamicCast(IOACPIPlatformDevice, provider);
    if (!_acpi) return false;
    _acpi->retain();
    if (strcmp(_acpi->getName(), "VPC0") ||
        _acpi->validateObject("_CFG") != kIOReturnSuccess ||
        _acpi->validateObject("VPCR") != kIOReturnSuccess ||
        _acpi->validateObject("VPCW") != kIOReturnSuccess ||
        competingClient()) {
        IOLog("S540HotkeysVPC: target identity or exclusive ownership refused\n");
        releaseRuntime();
        return false;
    }
    UInt32 cfg = 0;
    if (_acpi->evaluateInteger("_CFG", &cfg) != kIOReturnSuccess || cfg != S540Protocol::ExpectedCFG) {
        IOLog("S540HotkeysVPC: target firmware configuration refused\n");
        releaseRuntime();
        return false;
    }
    _cfg = cfg;
    if (!_acpi->open(this)) {
        releaseRuntime();
        return false;
    }
    _opened = true;
    _workLoop = IOWorkLoop::workLoop();
    _gate = IOCommandGate::commandGate(this);
    _events = IOInterruptEventSource::interruptEventSource(this, &S540HotkeysVPC::eventAction);
    if (!_workLoop || !_gate || !_events) {
        releaseRuntime();
        return false;
    }
    if (_workLoop->addEventSource(_gate) != kIOReturnSuccess) {
        releaseRuntime();
        return false;
    }
    _gateAdded = true;
    if (_workLoop->addEventSource(_events) != kIOReturnSuccess) {
        releaseRuntime();
        return false;
    }
    _eventsAdded = true;
    if (!setProperty("CFBundleIdentifier", "org.s540.HotkeysVPC")) {
        releaseRuntime();
        return false;
    }
    if (_gate->runAction(&S540HotkeysVPC::readyAction) != kIOReturnSuccess) {
        releaseRuntime();
        return false;
    }
    IOPMPowerState states[2];
    bzero(states, sizeof(states));
    states[0].version = 1;
    states[1].version = 1;
    states[1].capabilityFlags = kIOPMDeviceUsable;
    states[1].outputPowerCharacter = kIOPMPowerOn;
    states[1].inputPowerRequirement = kIOPMPowerOn;
    PMinit();
    _pmStarted = true;
    provider->joinPMtree(this);
    if (registerPowerDriver(this, states, 2) != kIOReturnSuccess ||
        changePowerStateTo(1) != kIOReturnSuccess) {
        releaseRuntime();
        return false;
    }
    registerService();
    return true;
}

IOReturn S540HotkeysVPC::readyAction(OSObject *owner, void *, void *, void *, void *) {
    S540HotkeysVPC *self = OSDynamicCast(S540HotkeysVPC, owner);
    if (!self || !self->establishBaseline()) return kIOReturnNotReady;
    if (!self->publishSnapshot("Ready")) {
        return kIOReturnNoMemory;
    }
    return kIOReturnSuccess;
}

IOReturn S540HotkeysVPC::setProperties(OSObject *) {
    // No user-triggered EC transport, arbitrary command, reactivation, or mapping API.
    return kIOReturnUnsupported;
}

IOReturn S540HotkeysVPC::setPowerState(unsigned long state, IOService *) {
    if (state > 1) return kIOPMAckImplied;
    IOLockLock(_lock);
    bool awake = state != 0;
    bool deferred = !_stopping && _events && (!_pmSawState || awake != _awake);
    if (deferred) {
        _pmSawState = true;
        _awake = awake;
        if (awake) _transportAwake = true;
        _accepting = false;
        _powerPending = true;
        _pmAckPending = true;
        _events->interruptOccurred(nullptr, nullptr, 0);
    }
    IOLockUnlock(_lock);
    // One in-flight event plus four bounded baseline passes fit this allowance.
    // Each pass has at most three 200ms command waits. A synchronous
    // AML implementation can exceed it; the driver never claims to abort AML.
    return deferred ? 4000000 : kIOPMAckImplied;
}

void S540HotkeysVPC::acknowledgePowerTransition() {
    IOLockLock(_lock);
    bool acknowledge = _pmAckPending;
    _pmAckPending = false;
    IOLockUnlock(_lock);
    if (acknowledge) acknowledgeSetPowerState();
}

IOReturn S540HotkeysVPC::message(UInt32 type, IOService *provider, void *argument) {
    // IOACPIFamily passes a pointer to the UInt32 notification value, matching
    // IdeaVPC::message in the pinned upstream. It is not a pointer-sized integer.
    if (type != kIOACPIMessageDeviceNotification || provider != _acpi)
        return IOService::message(type, provider, argument);
    uintptr_t notificationAddress = reinterpret_cast<uintptr_t>(argument);
    if (notificationAddress < 4096 || (notificationAddress & (alignof(UInt32) - 1)) != 0)
        return kIOReturnBadArgument;
    if (*static_cast<const UInt32 *>(argument) != 0x80U) return kIOReturnSuccess;
    IOLockLock(_lock);
    if (!_stopping && !_fault && _events) {
        // Count even while actions are disabled: a notification during drain/R1D
        // invalidates that baseline instead of resurfacing as a stale F8 later.
        if (_notificationGeneration != UINT64_MAX) _notificationGeneration++;
        else _pendingOverflow = true;
        if (_accepting && _awake) {
            if (_pending < PendingLimit) _pending++;
            else _pendingOverflow = true;
            // Signalling only queues private work; no AML evaluation or gate wait.
            _events->interruptOccurred(nullptr, nullptr, 0);
        }
    }
    IOLockUnlock(_lock);
    return kIOReturnSuccess;
}

void S540HotkeysVPC::eventAction(OSObject *owner, IOInterruptEventSource *, int) {
    S540HotkeysVPC *self = OSDynamicCast(S540HotkeysVPC, owner);
    if (self) self->handleEvents();
}

bool S540HotkeysVPC::readRegister(UInt32 index, UInt32 &value) {
    if (index > 1 || !operational()) return false;
    OSNumber *argument = OSNumber::withNumber(index, 32);
    if (!argument) { _lastIOReturn = kIOReturnNoMemory; return false; }
    OSObject *arguments[1] = {argument};
    _lastIOReturn = _acpi->evaluateInteger("VPCR", &value, arguments, 1);
    argument->release();
    return _lastIOReturn == kIOReturnSuccess;
}

bool S540HotkeysVPC::writeRegister(UInt32 index, UInt32 value) {
    // Only ProtocolCore can call this transport. Index/value allowlists are further
    // enforced at each command API, and no external interface exposes these calls.
    if (index > 1 || !operational()) return false;
    OSNumber *slot = OSNumber::withNumber(index, 32);
    OSNumber *data = OSNumber::withNumber(value, 32);
    if (!slot || !data) {
        if (slot) slot->release();
        if (data) data->release();
        _lastIOReturn = kIOReturnNoMemory;
        return false;
    }
    OSObject *arguments[2] = {slot, data};
    UInt32 result = 0;
    _lastIOReturn = _acpi->evaluateInteger("VPCW", &result, arguments, 2);
    slot->release(); data->release();
    return _lastIOReturn == kIOReturnSuccess;
}

void S540HotkeysVPC::pause() { IOSleep(1); }

S540Protocol::Result S540HotkeysVPC::readCommand(UInt32 command) {
    S540VPCTransport transport {this};
    _queryCount++;
    return S540Protocol::read(transport, command);
}
S540Protocol::Result S540HotkeysVPC::writeCameraCommand(UInt32 value) {
    S540VPCTransport transport {this};
    _queryCount++;
    return S540Protocol::write(transport, S540Protocol::WriteCamera, value, true);
}

bool S540HotkeysVPC::readMask(UInt32 &mask) {
    S540Protocol::Result low = readCommand(S540Protocol::ReadEventsLow);
    if (!low.good()) { if (low.error != S540Protocol::Stopped) failProtocol(low.error); return false; }
    S540Protocol::Result high = readCommand(S540Protocol::ReadEventsHigh);
    if (!high.good()) { if (high.error != S540Protocol::Stopped) failProtocol(high.error); return false; }
    mask = low.value | (high.value << 8);
    return true;
}

void S540HotkeysVPC::failProtocol(S540Protocol::Error error) {
    IOLockLock(_lock);
    _fault = true;
    _accepting = false;
    IOLockUnlock(_lock);
    _error = error;
    _queryFailureCount++;
    setProperty("Ready", kOSBooleanFalse);
    removeProperty("Snapshot"); // Never leave a previous Ready snapshot after a fault.
}

void S540HotkeysVPC::cameraFailure(S540Protocol::Error error) {
    _cameraBaselineValid = false;
    _cameraEnabled = false;
    _cameraState = S540Protocol::UnknownCamera;
    _cameraResult = S540Protocol::CameraProtocolFailure;
    _cameraError = error;
    // A payload error after a completed command leaves VCMD idle. Only the
    // camera feature is disabled. A stopped power transition is rebaselined on
    // wake. Failed command/status transport is poisoned until unload/reload.
    if (error == S540Protocol::PayloadReadFailed || error == S540Protocol::PayloadOutOfRange)
        _queryFailureCount++;
    else if (error != S540Protocol::Stopped) failProtocol(error);
}

bool S540HotkeysVPC::baselineCamera() {
    _cameraBaselineValid = false;
    _cameraSeen = false;
    _cameraError = 0;
    _cameraState = S540Protocol::UnknownCamera;
    _cameraEnabled = S540Protocol::cameraAdvertised(_cfg);
    if (!_cameraEnabled) {
        _cameraResult = S540Protocol::CameraUnsupported;
        return true;
    }
    S540Protocol::Result current = readCommand(S540Protocol::ReadCamera);
    if (!current.good()) {
        cameraFailure(current.error);
        return current.error != S540Protocol::Stopped && operational();
    }
    if (current.value > 1) {
        _cameraEnabled = false;
        _cameraResult = S540Protocol::CameraInvalidState;
        return true;
    }
    _cameraState = current.value;
    _cameraBaselineValid = true;
    _cameraResult = S540Protocol::CameraNeverRequested;
    return true;
}

bool S540HotkeysVPC::establishBaseline() {
    // All callers hold the private workloop gate. Notify generation is sampled
    // under the same lock that atomically enables event acceptance. No stale bit
    // from between the drain and R1D can authorize a later camera toggle.
    for (unsigned pass = 0; pass < 4; pass++) {
        IOLockLock(_lock);
        _accepting = false;
        UInt64 generation = _notificationGeneration;
        bool allowed = _awake && !_stopping && !_fault && !_powerPending;
        IOLockUnlock(_lock);
        if (!allowed) return false;
        if (generation == UINT64_MAX) {
            failProtocol(S540Protocol::NotificationOverflow);
            return false;
        }
        if (!readMask(_baselineMask) || !baselineCamera()) return false;
        IOLockLock(_lock);
        bool quiet = generation == _notificationGeneration && !_pendingOverflow &&
            _awake && !_stopping && !_fault && !_powerPending;
        if (quiet) { _pending = 0; _accepting = true; }
        IOLockUnlock(_lock);
        if (quiet) return true;
    }
    _cameraBaselineValid = false;
    _cameraEnabled = false;
    failProtocol(S540Protocol::BaselineNotQuiet);
    return false;
}

void S540HotkeysVPC::handleCamera(UInt64 timestamp, bool singleNotification) {
    IOLockLock(_lock);
    bool actionAllowed = _awake && !_stopping && !_fault;
    IOLockUnlock(_lock);
    if (!actionAllowed) return;
    bool trigger = S540Protocol::quietTrigger(timestamp, _lastCameraSeenNs, _cameraSeen);
    _cameraSeen = true;
    _lastCameraSeenNs = timestamp; // Every repeat extends the quiet-period debounce.
    if (!_cameraEnabled || !_cameraBaselineValid) return;
    S540Protocol::Result current = readCommand(S540Protocol::ReadCamera);
    if (!current.good()) {
        cameraFailure(current.error);
        return;
    }
    if (current.value > 1) {
        _cameraState = S540Protocol::UnknownCamera;
        _cameraEnabled = false;
        _cameraBaselineValid = false;
        _cameraResult = S540Protocol::CameraInvalidState;
        return;
    }
    if (!trigger || !singleNotification) {
        // Firmware may itself toggle on a rapid/repeated notification. Observe
        // its actual state even when a second host write is forbidden.
        _cameraState = current.value;
        _cameraResult = S540Protocol::CameraDebounced;
        return;
    }
    // A firmware change since the last baseline already satisfies this hotkey;
    // issuing a second toggle would undo it. This is a guarded integration
    // policy, not a claim that CFG's camera/OSD bits establish toggle ownership.
    if (S540Protocol::cameraDecision(current.value, _cameraState, _cameraBaselineValid) ==
        S540Protocol::CameraObserveFirmware) {
        _cameraState = current.value;
        _cameraResult = S540Protocol::CameraFirmwareChanged;
        return;
    }
    UInt32 requested = current.value ^ 1U;
    S540Protocol::Result written = writeCameraCommand(requested);
    if (!written.good()) {
        cameraFailure(written.error);
        return;
    }
    S540Protocol::Result actual = readCommand(S540Protocol::ReadCamera);
    if (!actual.good()) {
        cameraFailure(actual.error);
        return;
    }
    if (actual.value > 1) {
        _cameraState = S540Protocol::UnknownCamera;
        _cameraEnabled = false;
        _cameraBaselineValid = false;
        _cameraResult = S540Protocol::CameraInvalidState;
        return;
    }
    _cameraState = actual.value;
    if (actual.value != requested) {
        _cameraEnabled = false;
        _cameraBaselineValid = false;
        _cameraResult = S540Protocol::CameraReadbackMismatch;
        return;
    }
    _cameraResult = S540Protocol::CameraChanged;
}

void S540HotkeysVPC::handleEvents() {
    IOLockLock(_lock);
    UInt32 count = _pending;
    bool overflow = _pendingOverflow;
    bool power = _powerPending;
    bool awake = _awake;
    bool stopping = _stopping;
    _powerPending = false;
    _pending = 0; _pendingOverflow = false;
    bool accept = _accepting && !_stopping && !_fault;
    IOLockUnlock(_lock);
    if (power) {
        _cameraBaselineValid = false;
        _cameraEnabled = false;
        _cameraState = S540Protocol::UnknownCamera;
        if (!awake || stopping || !operational()) {
            IOLockLock(_lock);
            if (!awake || stopping) _transportAwake = false;
            IOLockUnlock(_lock);
            publishSnapshot(_fault ? "Fault" : "Ready");
            acknowledgePowerTransition();
            return;
        }
        // Power transitions drain all pending VPC bits while actions are disabled.
        // Establish the camera baseline AFTER that drain, then accept fresh events.
        if (!establishBaseline()) {
            publishSnapshot(_fault ? "Fault" : "Ready");
            acknowledgePowerTransition();
            return;
        }
        publishSnapshot(_fault ? "Fault" : "Ready");
        acknowledgePowerTransition();
        return;
    }
    if (!accept || !count) return;
    if (UINT64_MAX - _notifyCount < count || overflow) {
        failProtocol(S540Protocol::NotificationOverflow);
        publishSnapshot("Fault");
        return;
    }
    _notifyCount += count;
    UInt32 mask = 0;
    if (!readMask(mask)) { publishSnapshot(_fault ? "Fault" : "Ready"); return; }
    _lastMask = mask;
    if (mask) {
        if (_sequence == UINT64_MAX) {
            failProtocol(S540Protocol::SequenceOverflow);
            publishSnapshot("Fault");
            return;
        }
        UInt64 timestamp = nowNs();
        if (mask & (1U << 7)) handleCamera(timestamp, count == 1);
        _sequence++;
        UInt32 slot = (_ringStart + _ringCount) % RingCapacity;
        if (_ringCount == RingCapacity) {
            slot = _ringStart;
            _ringStart = (_ringStart + 1) % RingCapacity;
        } else _ringCount++;
        _ring[slot] = Record {_sequence, mask, timestamp};
    }
    if (!publishSnapshot(_fault ? "Fault" : "Ready")) {
        setProperty("SnapshotPublishFailure", kOSBooleanTrue);
    }
}

bool S540HotkeysVPC::publishSnapshot(const char *state) {
    OSDictionary *snapshot = OSDictionary::withCapacity(20);
    OSArray *ring = OSArray::withCapacity(RingCapacity);
    if (!snapshot || !ring) {
        if (snapshot) snapshot->release();
        if (ring) ring->release();
        failProtocol(S540Protocol::ResourceFailure);
        return false;
    }
    bool good = true;
    for (UInt32 i = 0; i < _ringCount && good; i++) {
        const Record &record = _ring[(_ringStart + i) % RingCapacity];
        OSDictionary *entry = OSDictionary::withCapacity(3);
        if (!entry) { good = false; break; }
        good = dictionaryNumber(entry, "seq", record.sequence) &&
            dictionaryNumber(entry, "mask", record.mask, 32) &&
            dictionaryNumber(entry, "time_ns", record.timeNs) && ring->setObject(entry);
        entry->release();
    }
    IOLockLock(_lock);
    bool ready = !strcmp(state, "Ready") && _accepting && _awake && !_fault && !_stopping;
    bool awake = _awake;
    IOLockUnlock(_lock);
    good = good && dictionaryNumber(snapshot, "Schema", 1, 32) &&
        dictionaryString(snapshot, "Version", "0.1.0") && dictionaryString(snapshot, "State", state) &&
        snapshot->setObject("Ready", ready ? kOSBooleanTrue : kOSBooleanFalse) &&
        snapshot->setObject("Awake", awake ? kOSBooleanTrue : kOSBooleanFalse) &&
        dictionaryNumber(snapshot, "CFG", _cfg, 32) &&
        dictionaryNumber(snapshot, "EventSequence", _sequence) && snapshot->setObject("EventRing", ring) &&
        dictionaryNumber(snapshot, "NotifyCount", _notifyCount) &&
        dictionaryNumber(snapshot, "QueryCount", _queryCount) &&
        dictionaryNumber(snapshot, "QueryFailureCount", _queryFailureCount) &&
        dictionaryNumber(snapshot, "ErrorCode", _error, 32) &&
        dictionaryNumber(snapshot, "LastIOReturn", _lastIOReturn, 32) &&
        dictionaryNumber(snapshot, "LastMask", _lastMask, 32) &&
        dictionaryNumber(snapshot, "CameraState", _cameraState, 32) &&
        dictionaryNumber(snapshot, "LastCameraResult", _cameraResult, 32) &&
        dictionaryNumber(snapshot, "CameraErrorCode", _cameraError, 32) &&
        snapshot->setObject("CameraBaselineValid", _cameraBaselineValid ? kOSBooleanTrue : kOSBooleanFalse) &&
        snapshot->setObject("CameraEnabled", _cameraEnabled ? kOSBooleanTrue : kOSBooleanFalse) &&
        dictionaryNumber(snapshot, "BaselineMask", _baselineMask, 32);
    if (good) good = setProperty("Snapshot", snapshot);
    if (good) {
        // Immutable aliases support an installer's simple readiness query. Consumers
        // requiring a coherent multi-field read must use the Snapshot dictionary.
        setProperty("Ready", ready ? kOSBooleanTrue : kOSBooleanFalse);
        setProperty("Version", "0.1.0"); setProperty("State", state);
        setProperty("EventSequence", _sequence, 64); setProperty("EventRing", ring);
        setProperty("CFG", _cfg, 32); setProperty("QueryFailureCount", _queryFailureCount, 64);
        setProperty("LastCameraResult", _cameraResult, 32); setProperty("CameraState", _cameraState, 32);
    }
    ring->release(); snapshot->release();
    if (!good) failProtocol(S540Protocol::ResourceFailure);
    return good;
}

IOReturn S540HotkeysVPC::stopAction(OSObject *owner, void *, void *, void *, void *) {
    S540HotkeysVPC *self = OSDynamicCast(S540HotkeysVPC, owner);
    if (!self) return kIOReturnBadArgument;
    IOLockLock(self->_lock);
    self->_transportAwake = false;
    IOLockUnlock(self->_lock);
    self->publishSnapshot("Stopping");
    self->acknowledgePowerTransition();
    return kIOReturnSuccess;
}

void S540HotkeysVPC::releaseRuntime() {
    if (_lock) {
        IOLockLock(_lock);
        _stopping = true;
        _accepting = false;
        IOLockUnlock(_lock);
    }
    if (_gate && _gateAdded) _gate->runAction(&S540HotkeysVPC::stopAction);
    if (_pmStarted) { PMstop(); _pmStarted = false; }
    if (_events) {
        _events->disable();
        if (_eventsAdded && _workLoop) _workLoop->removeEventSource(_events);
        _eventsAdded = false;
        _events->release(); _events = nullptr;
    }
    if (_gate) {
        if (_gateAdded && _workLoop) _workLoop->removeEventSource(_gate);
        _gateAdded = false;
        _gate->release(); _gate = nullptr;
    }
    if (_workLoop) { _workLoop->release(); _workLoop = nullptr; }
    if (_acpi) {
        if (_opened) _acpi->close(this);
        _opened = false;
        _acpi->release(); _acpi = nullptr;
    }
}

void S540HotkeysVPC::stop(IOService *provider) {
    releaseRuntime();
    IOService::stop(provider);
}
void S540HotkeysVPC::free() {
    releaseRuntime();
    if (_lock) { IOLockFree(_lock); _lock = nullptr; }
    IOService::free();
}
