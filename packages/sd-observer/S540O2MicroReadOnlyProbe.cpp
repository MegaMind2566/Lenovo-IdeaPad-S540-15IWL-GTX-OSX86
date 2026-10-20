// SPDX-License-Identifier: MIT
// Bounded observer: this service attaches to IOResources, never to the PCI device.
#include <IOKit/IOService.h>
#include <IOKit/IOWorkLoop.h>
#include <IOKit/IOTimerEventSource.h>
#include <IOKit/IOMemoryDescriptor.h>
#include <IOKit/IODeviceMemory.h>
#include <IOKit/pci/IOPCIDevice.h>
#include <libkern/c++/OSArray.h>
#include <libkern/c++/OSBoolean.h>
#include <libkern/c++/OSData.h>
#include <libkern/c++/OSDictionary.h>
#include <libkern/c++/OSNumber.h>
#include <libkern/c++/OSString.h>
#include <libkern/libkern.h>
#include <libkern/version.h>

namespace {
const char * const kVersion = "0.1.0";
const UInt32 kDeviceID = 0x86211217;
const UInt32 kSubsystemID = 0x380317aa;
const unsigned kMaxDevices = 256;
const unsigned kMaxSnapshots = 4;
const UInt32 kScheduledSeconds[kMaxSnapshots] = {0, 2, 10, 20};

void number(OSDictionary *dict, const char *key, UInt64 value, unsigned bits = 32) {
    OSNumber *n = OSNumber::withNumber(value, bits);
    if (n) { dict->setObject(key, n); n->release(); }
}
void string(OSDictionary *dict, const char *key, const char *value) {
    OSString *s = OSString::withCString(value);
    if (s) { dict->setObject(key, s); s->release(); }
}
bool registryID(IOPCIDevice *pci, const char *key, UInt32 expected) {
    OSObject *object = pci->copyProperty(key);
    OSData *data = OSDynamicCast(OSData, object);
    UInt32 value = 0;
    bool valid = data && data->getLength() == sizeof(value);
    if (valid) memcpy(&value, data->getBytesNoCopy(), sizeof(value));
    if (object) object->release();
    return valid && value == expected;
}
bool expectedPath(IOPCIDevice *pci) {
    // Context only: exact hardware/subsystem IDs and uniqueness are the gate.
    char path[512];
    int length = sizeof(path);
    const char *suffix = "/RP04@1C/PXSX@0";
    if (!pci->getPath(path, &length, gIOServicePlane)) return false;
    size_t n = strlen(path), s = strlen(suffix);
    return n >= s && strcmp(path + n - s, suffix) == 0;
}
bool exactHardware(IOPCIDevice *pci) {
    return !pci->isInactive() &&
        pci->extendedConfigRead32(0x00) == kDeviceID &&
        pci->extendedConfigRead32(0x2c) == kSubsystemID &&
        (pci->extendedConfigRead32(0x08) >> 8) == 0x080501;
}
// Capability headers only; finite walk, no reads of MSI payload or SD data.
UInt8 pmCapability(IOPCIDevice *pci) {
    if (!(pci->extendedConfigRead16(0x06) & 0x10)) return 0;
    UInt8 pointer = pci->extendedConfigRead8(0x34);
    UInt64 visited = 0;
    for (unsigned hops = 0; hops < 48 && pointer; ++hops) {
        if (pointer < 0x40 || pointer > 0xf8 || (pointer & 3)) return 0;
        UInt64 bit = 1ULL << (pointer >> 2);
        if (visited & bit) return 0;
        visited |= bit;
        UInt16 header = pci->extendedConfigRead16(pointer);
        if ((header & 0xff) == 0x01) return pointer;
        pointer = static_cast<UInt8>(header >> 8);
    }
    return 0;
}
bool readableMMIO(IOPCIDevice *pci, UInt8 pm) {
    return pm && exactHardware(pci) &&
        (pci->extendedConfigRead16(0x04) & 0x0002) &&
        (pci->extendedConfigRead16(pm + 4) & 3) == 0;
}
void copyScalar(IORegistryEntry *entry, OSDictionary *dict, const char *key) {
    OSObject *object = entry->copyProperty(key);
    // Never forward arbitrary strings, dictionaries, card identities or media data.
    if (object && (OSDynamicCast(OSNumber, object) || OSDynamicCast(OSBoolean, object)))
        dict->setObject(key, object);
    else if (OSString *s = OSDynamicCast(OSString, object)) {
        if (s->isEqualTo("Yes")) dict->setObject(key, kOSBooleanTrue);
        else if (s->isEqualTo("No")) dict->setObject(key, kOSBooleanFalse);
    }
    if (object) object->release();
}
void driverState(IORegistryEntry *parent, OSArray *out, unsigned depth) {
    if (depth >= 5 || out->getCount() >= 16) return;
    OSIterator *children = parent->getChildIterator(gIOServicePlane);
    if (!children) return;
    unsigned scanned = 0;
    while (OSObject *object = children->getNextObject()) {
        if (++scanned > 32 || out->getCount() >= 16) break;
        IOService *child = OSDynamicCast(IOService, object);
        if (!child) continue;
        OSDictionary *state = OSDictionary::withCapacity(10);
        if (!state) break;
        string(state, "Class", child->getMetaClass()->getClassName());
        number(state, "Depth", depth);
        state->setObject("Inactive", child->isInactive() ? kOSBooleanTrue : kOSBooleanFalse);
        const char *keys[] = {"Card Present", "Card Configured", "IOUnit", "Bus Voltage",
                              "Base Frequency", "Clock Divisor"};
        for (unsigned i = 0; i < sizeof(keys) / sizeof(keys[0]); ++i)
            copyScalar(child, state, keys[i]);
        out->setObject(state);
        state->release();
        driverState(child, out, depth + 1);
    }
    children->release();
}
void readMMIO(IOPCIDevice *pci, UInt8 pm, OSDictionary *snapshot) {
    if (!readableMMIO(pci, pm)) {
        string(snapshot, "MMIOStatus", "skipped-not-D0-or-memory-disabled");
        return;
    }
    UInt32 bar = pci->extendedConfigRead32(0x10);
    UInt32 high = ((bar & 6) == 4) ? pci->extendedConfigRead32(0x14) : 0;
    if (bar == 0xffffffff || high == 0xffffffff || (bar & 1) || ((bar & 6) != 0 && (bar & 6) != 4) ||
        (!(bar & ~0xfU) && !high)) {
        string(snapshot, "MMIOStatus", "skipped-invalid-BAR0");
        return;
    }
    // copyProperty avoids IOPCIDevice memory accessors that may alter PCI state.
    OSObject *memoryObject = pci->copyProperty("IODeviceMemory");
    OSArray *memories = OSDynamicCast(OSArray, memoryObject);
    IOMemoryDescriptor *memory = nullptr;
    if (memories && memories->getCount() <= 16) {
        for (unsigned i = 0; i < memories->getCount(); ++i) {
            // IODeviceMemory factories may return IOGeneral/IOSubMemoryDescriptor.
            IOMemoryDescriptor *candidate = OSDynamicCast(IOMemoryDescriptor, memories->getObject(i));
            if (candidate && (candidate->getTag() & 0xff) == 0x10 &&
                candidate->getLength() >= 0x1d0) { memory = candidate; break; }
        }
    }
    if (!memory) {
        string(snapshot, "MMIOStatus", "skipped-no-existing-BAR0-descriptor");
        if (memoryObject) memoryObject->release();
        return;
    }
    IOByteCount segmentLength = 0;
    UInt64 address = (static_cast<UInt64>(high) << 32) | (bar & ~0xfU);
    addr64_t descriptorAddress = memory->getPhysicalSegment(0, &segmentLength, kIOMemoryMapperNone);
    if (descriptorAddress != address || segmentLength < 0x1d0) {
        string(snapshot, "MMIOStatus", "skipped-BAR0-descriptor-mismatch");
        memoryObject->release();
        return;
    }
    IOMemoryMap *map = nullptr;
    if (readableMMIO(pci, pm)) map = memory->map(kIOMapReadOnly | kIOMapUnique);
    if (!map || !(map->getMapOptions() & kIOMapReadOnly) ||
        map->getLength() < 0x1d0 || !map->getVirtualAddress()) {
        string(snapshot, "MMIOStatus", "skipped-read-only-map-unavailable");
    } else if (!readableMMIO(pci, pm)) {
        string(snapshot, "MMIOStatus", "skipped-state-changed-before-read");
    } else {
        OSDictionary *registers = OSDictionary::withCapacity(12);
        if (registers) {
            volatile const UInt8 *base = reinterpret_cast<volatile const UInt8 *>(map->getVirtualAddress());
            // Explicit whitelist: NO command/argument, FIFO 0x20, response or CID.
            const UInt16 offsets32[] = {0x24, 0x28, 0x2c, 0x30, 0x34, 0x38, 0x40, 0x44, 0x1cc};
            for (unsigned i = 0; i < sizeof(offsets32) / sizeof(offsets32[0]); ++i) {
                char key[12];
                snprintf(key, sizeof(key), "0x%03x", offsets32[i]);
                UInt32 value = *reinterpret_cast<volatile const UInt32 *>(base + offsets32[i]);
                number(registers, key, value);
            }
            number(registers, "0x0fe", *reinterpret_cast<volatile const UInt16 *>(base + 0xfe), 16);
            bool stable = readableMMIO(pci, pm);
            // A native driver can change hardware concurrently; this is not atomic.
            registers->setObject("GuardStillValidAfterRead", stable ? kOSBooleanTrue : kOSBooleanFalse);
            snapshot->setObject("MMIO", registers);
            registers->release();
            string(snapshot, "MMIOStatus", stable ? "read-whitelist-nonatomic" : "state-changed-during-read");
        } else string(snapshot, "MMIOStatus", "allocation-failed");
    }
    if (map) map->release();
    memoryObject->release();
}
void readPCI(IOPCIDevice *pci, OSDictionary *snapshot) {
    if (!exactHardware(pci)) { string(snapshot, "Status", "hardware-gate-failed"); return; }
    OSDictionary *config = OSDictionary::withCapacity(24);
    if (!config) { string(snapshot, "Status", "allocation-failed"); return; }
    number(config, "VendorDevice", kDeviceID);
    number(config, "SubsystemVendorDevice", kSubsystemID);
    number(config, "Bus", pci->getBusNumber(), 8);
    number(config, "Device", pci->getDeviceNumber(), 8);
    number(config, "Function", pci->getFunctionNumber(), 8);
    number(config, "CommandStatus", pci->extendedConfigRead32(0x04));
    number(config, "ClassRevision", pci->extendedConfigRead32(0x08));
    number(config, "HeaderType", pci->extendedConfigRead8(0x0e), 8);
    for (unsigned i = 0; i < 6; ++i) {
        char key[8]; snprintf(key, sizeof(key), "BAR%u", i);
        number(config, key, pci->extendedConfigRead32(0x10 + 4 * i));
    }
    const UInt16 offsets8[] = {0xd3, 0xd4};
    for (unsigned i = 0; i < sizeof(offsets8) / sizeof(offsets8[0]); ++i) {
        char key[12]; snprintf(key, sizeof(key), "0x%03x", offsets8[i]);
        number(config, key, pci->extendedConfigRead8(offsets8[i]), 8);
    }
    const UInt16 offsets32[] = {0xdc, 0xf0, 0x300, 0x304, 0x324, 0x3e4};
    for (unsigned i = 0; i < sizeof(offsets32) / sizeof(offsets32[0]); ++i) {
        char key[12]; snprintf(key, sizeof(key), "0x%03x", offsets32[i]);
        number(config, key, pci->extendedConfigRead32(offsets32[i]));
    }
    UInt8 pm = pmCapability(pci);
    number(config, "PMCapabilityOffset", pm, 8);
    if (pm) {
        number(config, "PMCapabilities", pci->extendedConfigRead16(pm + 2), 16);
        number(config, "PMCSR", pci->extendedConfigRead16(pm + 4), 16);
    }
    snapshot->setObject("PCI", config);
    config->release();
    snapshot->setObject("ExpectedPortPath", expectedPath(pci) ? kOSBooleanTrue : kOSBooleanFalse);
    OSArray *drivers = OSArray::withCapacity(8);
    if (drivers) { driverState(pci, drivers, 0); snapshot->setObject("DriverState", drivers); drivers->release(); }
    readMMIO(pci, pm, snapshot);
    string(snapshot, "Status", "observed");
}
} // namespace

class S540O2MicroReadOnlyProbe : public IOService {
    OSDeclareDefaultStructors(S540O2MicroReadOnlyProbe)
    IOWorkLoop *loop_ = nullptr;
    IOTimerEventSource *timer_ = nullptr;
    OSArray *snapshots_ = nullptr;
    unsigned next_ = 0;
    bool stopping_ = false;
    bool allocationFailed_ = false;
    void takeSnapshot();
    void releaseResources();
    static void timeout(OSObject *owner, IOTimerEventSource *sender);
public:
    bool start(IOService *provider) override;
    void stop(IOService *provider) override;
    void free() override;
};
OSDefineMetaClassAndStructors(S540O2MicroReadOnlyProbe, IOService)

bool S540O2MicroReadOnlyProbe::start(IOService *provider) {
#if !defined(__x86_64__)
    return false;
#else
    if (version_major != 25 || !IOService::start(provider)) return false;
    snapshots_ = OSArray::withCapacity(kMaxSnapshots);
    loop_ = IOWorkLoop::workLoop();
    timer_ = IOTimerEventSource::timerEventSource(this, timeout);
    if (!snapshots_ || !loop_ || !timer_ || loop_->addEventSource(timer_) != kIOReturnSuccess) {
        releaseResources();
        IOService::stop(provider);
        return false;
    }
    takeSnapshot();
    if (timer_->setTimeoutMS(2000) != kIOReturnSuccess) {
        setProperty("S540SDObserverTimerStatus", "schedule-failed");
    }
    registerService();
    IOLog("S540O2MicroReadOnlyProbe 0.1.0: bounded observer started\n");
    return true;
#endif
}
void S540O2MicroReadOnlyProbe::takeSnapshot() {
    if (stopping_ || next_ >= kMaxSnapshots) return;
    OSDictionary *snapshot = OSDictionary::withCapacity(10);
    if (!snapshot) {
        allocationFailed_ = true;
        ++next_;
        setProperty("S540SDObserverAllocationStatus", "snapshot-allocation-failed");
        return;
    }
    number(snapshot, "Index", next_);
    number(snapshot, "ScheduledSeconds", kScheduledSeconds[next_]);
    IOPCIDevice *target = nullptr;
    unsigned matches = 0, scanned = 0;
    OSDictionary *matching = IOService::serviceMatching("IOPCIDevice");
    OSIterator *iterator = matching ? IOService::getMatchingServices(matching) : nullptr;
    if (matching) matching->release();
    if (iterator) {
        while (OSObject *object = iterator->getNextObject()) {
            if (++scanned > kMaxDevices) break;
            IOPCIDevice *pci = OSDynamicCast(IOPCIDevice, object);
            // Only properties are examined on unrelated PCI devices.
            if (!pci || !registryID(pci, "vendor-id", 0x1217) ||
                !registryID(pci, "device-id", 0x8621)) continue;
            ++matches;
            if (!target) { pci->retain(); target = pci; }
        }
        iterator->release();
    }
    number(snapshot, "Matches", matches);
    if (!iterator) string(snapshot, "Status", "enumeration-unavailable");
    else if (scanned > kMaxDevices) string(snapshot, "Status", "enumeration-limit");
    else if (matches != 1) string(snapshot, "Status", matches ? "ambiguous-target" : "target-not-published");
    else readPCI(target, snapshot);
    if (target) target->release();
    OSArray *next = OSArray::withArray(snapshots_, kMaxSnapshots);
    if (next) {
        next->setObject(snapshot);
        snapshots_->release(); snapshots_ = next;
    } else allocationFailed_ = true;
    snapshot->release();
    ++next_;
    OSDictionary *diagnostics = OSDictionary::withCapacity(4);
    if (diagnostics) {
        string(diagnostics, "Version", kVersion);
        string(diagnostics, "Status", allocationFailed_ ? "allocation-failed" :
               (next_ == kMaxSnapshots ? "complete" : "collecting"));
        number(diagnostics, "SnapshotLimit", kMaxSnapshots);
        diagnostics->setObject("Snapshots", snapshots_);
        setProperty("S540SDDiagnostics", diagnostics);
        diagnostics->release();
    }
}
void S540O2MicroReadOnlyProbe::timeout(OSObject *owner, IOTimerEventSource *sender) {
    S540O2MicroReadOnlyProbe *self = OSDynamicCast(S540O2MicroReadOnlyProbe, owner);
    if (!self || self->stopping_ || self->next_ >= kMaxSnapshots) return;
    self->takeSnapshot();
    if (self->next_ < kMaxSnapshots) {
        UInt32 delay = (kScheduledSeconds[self->next_] - kScheduledSeconds[self->next_ - 1]) * 1000;
        if (sender->setTimeoutMS(delay) != kIOReturnSuccess)
            self->setProperty("S540SDObserverTimerStatus", "schedule-failed");
    }
}
void S540O2MicroReadOnlyProbe::releaseResources() {
    // Serialize the stop flag with a running timer action. Cancel outside the
    // gate: active timer implementations may wait for a pending callout.
    if (loop_) loop_->closeGate();
    stopping_ = true;
    if (loop_) loop_->openGate();
    if (timer_) {
        timer_->cancelTimeout();
        timer_->disable();
        if (loop_ && timer_->getWorkLoop() == loop_) loop_->removeEventSource(timer_);
        timer_->release(); timer_ = nullptr;
    }
    if (loop_) { loop_->release(); loop_ = nullptr; }
    if (snapshots_) { snapshots_->release(); snapshots_ = nullptr; }
}
void S540O2MicroReadOnlyProbe::stop(IOService *provider) {
    releaseResources();
    IOService::stop(provider);
}
void S540O2MicroReadOnlyProbe::free() {
    releaseResources();
    IOService::free();
}
