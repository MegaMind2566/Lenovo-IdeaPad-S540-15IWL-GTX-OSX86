// SPDX-License-Identifier: MIT
#include "S540NvidiaPCIProbe.hpp"
#include "../../nvidia-hardware-transport/src/S540NvidiaHardwareRuntime.hpp"

#include <IOKit/IOMemoryDescriptor.h>
#include <kern/task.h>
#include <libkern/c++/OSArray.h>
#include <libkern/c++/OSBoolean.h>
#include <libkern/c++/OSDictionary.h>
#include <libkern/c++/OSNumber.h>
#include <libkern/c++/OSString.h>

#define super IOService
OSDefineMetaClassAndStructors(S540NvidiaPCIProbe, IOService)

namespace {
const char * const kSnapshotKey = "S540NvidiaPCIProbeSnapshot";

template <typename T> class ScopedRelease {
    T *object;
public:
    explicit ScopedRelease(T *value = nullptr) : object(value) {}
    ~ScopedRelease() { if (object) object->release(); }
    T *get() const { return object; }
    void reset() { if (object) object->release(); object = nullptr; }
private:
    ScopedRelease(const ScopedRelease &) = delete;
    ScopedRelease &operator=(const ScopedRelease &) = delete;
};

class ScopedArbitration {
    IOService *provider;
    bool locked;
public:
    explicit ScopedArbitration(IOService *value) : provider(value),
        locked(value->lockForArbitration(false)) {}
    ~ScopedArbitration() { if (locked) provider->unlockForArbitration(); }
    bool acquired() const { return locked; }
private:
    ScopedArbitration(const ScopedArbitration &) = delete;
    ScopedArbitration &operator=(const ScopedArbitration &) = delete;
};

class ConfigReader {
    IOPCIDevice *device;
public:
    explicit ConfigReader(IOPCIDevice *value) : device(value) {}
    bool operator()(uint32_t offset, uint32_t &value) const {
        // Standard PCI configuration only, never extended space or unaligned
        // reads. The capability walker has a separate strict 48-link bound.
        if (offset > 0xfc || (offset & 3U) != 0)
            return false;
        value = device->configRead32(static_cast<UInt8>(offset));
        return value != UINT32_MAX;
    }
};

S540NvidiaPCIProbePolicy::Identity readIdentity(IOPCIDevice *device) {
    // Exactly three fixed configuration-space dwords; never write config space.
    S540NvidiaPCIProbePolicy::Identity identity = {
        device->configRead32(0x00),
        device->configRead32(0x08),
        device->configRead32(0x2c)
    };
    return identity;
}

bool setNumber(OSDictionary *dictionary, const char *key,
               uint64_t value, unsigned int bits) {
    OSNumber *number = OSNumber::withNumber(value, bits);
    if (!number)
        return false;
    const bool result = dictionary->setObject(key, number);
    number->release();
    return result;
}

bool setString(OSDictionary *dictionary, const char *key, const char *value) {
    OSString *string = OSString::withCString(value);
    if (!string)
        return false;
    const bool result = dictionary->setObject(key, string);
    string->release();
    return result;
}

OSArray *copyResourceMetadata(IOPCIDevice *device, IOMemoryDescriptor **bar0) {
    // Read the already-published resource array directly. PCI convenience
    // getters can change tunnel link power policy; this path avoids them.
    // copyProperty retains the published array while it is examined. Retain
    // BAR0 independently for the bounded mapping, without provider helpers.
    ScopedRelease<OSObject> property(device->copyProperty("IODeviceMemory"));
    OSArray *published = OSDynamicCast(OSArray, property.get());
    if (!published)
        return nullptr;
    const unsigned int count = published->getCount();
    if (count == 0 || count > 16)
        return nullptr;

    IOMemoryDescriptor *bars[6] = {nullptr, nullptr, nullptr, nullptr, nullptr, nullptr};
    for (unsigned int index = 0; index < count; ++index) {
        IOMemoryDescriptor *memory = OSDynamicCast(IOMemoryDescriptor, published->getObject(index));
        if (!memory)
            return nullptr;
        const unsigned int reg = static_cast<unsigned int>(memory->getTag() & 0xffU);
        // Other published resources, such as the expansion ROM, are outside
        // this snapshot. A duplicate descriptor for a BAR is ambiguous.
        if (reg < 0x10 || reg > 0x24 || ((reg - 0x10) & 3U) != 0)
            continue;
        const unsigned int barIndex = (reg - 0x10) / 4;
        if (bars[barIndex])
            return nullptr;
        bars[barIndex] = memory;
    }

    OSArray *resources = OSArray::withCapacity(6);
    if (!resources)
        return nullptr;

    for (unsigned int index = 0; index < 6; ++index) {
        const UInt8 reg = static_cast<UInt8>(0x10 + 4 * index);
        OSDictionary *resource = OSDictionary::withCapacity(4);
        if (!resource) {
            resources->release();
            return nullptr;
        }

        // Querying the assigned address/length is metadata only: no mapping,
        // aperture access, BAR sizing writes, DMA, or hardware initialization.
        IOMemoryDescriptor *memory = bars[index];
        bool ok = setNumber(resource, "Register", reg, 8)
            && resource->setObject("Present", memory ? kOSBooleanTrue : kOSBooleanFalse);
        if (ok && memory) {
            const uint64_t address = memory->getPhysicalAddress();
            const uint64_t length = memory->getLength();
            // Reject unusable or wrapping published descriptors. Do not attempt
            // to repair provider resources or probe the device for a size.
            ok = length != 0 && address <= UINT64_MAX - (length - 1)
                && setNumber(resource, "Address", address, 64)
                && setNumber(resource, "Length", length, 64);
        }
        if (ok)
            ok = resources->setObject(resource);
        resource->release();
        if (!ok) {
            resources->release();
            return nullptr;
        }
    }
    if (bars[0]) {
        bars[0]->retain();
        *bar0 = bars[0];
    }
    return resources;
}

struct MMIOOutcome {
    const char *status;
    const char *reason;
    uint32_t readCount;
    uint32_t rawValue;
};

const char *checkReadPrerequisites(IOPCIDevice *device,
                                   IOMemoryDescriptor *bar0) {
    if (!S540NvidiaPCIProbePolicy::matches(readIdentity(device)))
        return "pci-identity-changed";
    ConfigReader read(device);
    uint32_t commandStatus = 0, rawBar0 = 0;
    if (!read(0x04, commandStatus) || !read(0x10, rawBar0))
        return "pci-config-unavailable";
    if ((commandStatus & 2U) == 0)
        return "memory-decoding-disabled";
    const char *reason = S540NvidiaPCIProbePolicy::validateBar0(rawBar0,
        bar0->getTag(), bar0->getPhysicalAddress(), bar0->getLength());
    if (reason)
        return reason;
    return S540NvidiaPCIProbePolicy::requireD0(read);
}

struct IdentificationOutcome {
    MMIOOutcome boot0;
    MMIOOutcome boot42;
};

template <uint32_t Offset>
MMIOOutcome attemptRegisterRead(IOPCIDevice *device,
                               IOMemoryDescriptor *bar0) {
    // A compile-time whitelist, not an arbitrary-offset runtime interface.
    static_assert(Offset == 0 || Offset == 0xa00, "Only BOOT0 and BOOT42 are allowed.");
    MMIOOutcome result = {"refused", "mapping-unavailable", 0, 0};
    const char *reason = checkReadPrerequisites(device, bar0);
    if (reason) {
        result.reason = reason;
        return result;
    }

    // Each request covers one register. Physical VM mappings still have page
    // granularity. No timeout makes a stalled hardware load recoverable.
    ScopedRelease<IOMemoryMap> mapping(bar0->createMappingInTask(kernel_task, 0,
        kIOMapAnywhere | kIOMapReadOnly | kIOMapInhibitCache | kIOMapUnique, Offset, 4));
    if (!mapping.get())
        return result;
    // The returned address already includes Offset; do not add it again.
    const mach_vm_address_t address = mapping.get()->getVirtualAddress();
    if (address == 0 || (address & 3U) != 0 || mapping.get()->getLength() != 4) {
        result.reason = "mapping-invalid";
        return result;
    }
    reason = checkReadPrerequisites(device, bar0);
    if (reason) {
        result.reason = reason;
        return result;
    }

    // Intel x86_64: one aligned 32-bit volatile load per fixed instantiation.
    // No writes, retries, polling, or access beyond the two allowed registers.
    const volatile uint32_t *registerWord = reinterpret_cast<const volatile uint32_t *>(address);
    result.rawValue = *registerWord;
    result.readCount = 1;
    mapping.reset();
    const bool identified = Offset == 0
        ? S540NvidiaPCIProbePolicy::boot0IsTU117(result.rawValue)
        : S540NvidiaPCIProbePolicy::boot42IsTU117(result.rawValue);
    result.reason = Offset == 0
        ? S540NvidiaPCIProbePolicy::identifyBoot0(result.rawValue)
        : S540NvidiaPCIProbePolicy::identifyBoot42(result.rawValue);
    result.status = identified ? "identified" : "failed";
    return result;
}

IdentificationOutcome attemptIdentificationReads(IOPCIDevice *device,
                                                 IOMemoryDescriptor *bar0,
                                                 bool metadataAvailable) {
    IdentificationOutcome result = {
        {"refused", "resource-metadata-unavailable", 0, 0},
        {"not_attempted", "boot0-not-identified", 0, 0}
    };
    if (!metadataAvailable)
        return result;
    if (!bar0) {
        result.boot0.reason = "bar0-descriptor-missing";
        return result;
    }

    // One arbitration scope covers both reads and both mapping lifetimes.
    // It serializes compliant open/close/termination without opening the PCI
    // provider. It does not freeze platform PM or guarantee bounded latency.
    ScopedArbitration arbitration(device);
    if (!arbitration.acquired()) {
        result.boot0.reason = "provider-arbitration-unavailable";
        return result;
    }
    if (device->isOpen()) {
        result.boot0.reason = "provider-already-open";
        return result;
    }
    result.boot0 = attemptRegisterRead<0>(device, bar0);
    if (result.boot0.readCount == 1
        && S540NvidiaPCIProbePolicy::boot0IsTU117(result.boot0.rawValue))
        result.boot42 = attemptRegisterRead<0xa00>(device, bar0);
    return result;
}

OSDictionary *copyMMIOResult(const MMIOOutcome &result, bool boot42) {
    OSDictionary *dictionary = OSDictionary::withCapacity(10);
    if (!dictionary)
        return nullptr;
    bool ok = setString(dictionary, "Status", result.status)
        && setString(dictionary, "Reason", result.reason)
        && setNumber(dictionary, "ReadCount", result.readCount, 32)
        && setNumber(dictionary, "BarIndex", 0, 32)
        && setNumber(dictionary, "Offset", boot42 ? 0xa00 : 0, 32)
        && setNumber(dictionary, "Width", 32, 32);
    if (ok && result.readCount == 1) {
        ok = setNumber(dictionary, "RawValue", result.rawValue, 32)
            && setNumber(dictionary, "Architecture", boot42
                         ? S540NvidiaPCIProbePolicy::boot42Architecture(result.rawValue)
                         : S540NvidiaPCIProbePolicy::architecture(result.rawValue), 32)
            && setNumber(dictionary, "Implementation", boot42
                         ? S540NvidiaPCIProbePolicy::boot42Implementation(result.rawValue)
                         : S540NvidiaPCIProbePolicy::implementation(result.rawValue), 32);
        if (ok && boot42)
            ok = setNumber(dictionary, "ChipID",
                           S540NvidiaPCIProbePolicy::boot42ChipID(result.rawValue), 32);
    }
    if (!ok) {
        dictionary->release();
        return nullptr;
    }
    return dictionary;
}

OSDictionary *copyHALSelection(const IdentificationOutcome &result) {
    OSDictionary *dictionary = OSDictionary::withCapacity(5);
    if (!dictionary)
        return nullptr;
    const bool matched = result.boot0.readCount == 1 && result.boot42.readCount == 1
        && S540NvidiaPCIProbePolicy::selectHALVariant(result.boot0.rawValue,
                                                     result.boot42.rawValue) == 41;
    bool ok = setString(dictionary, "Status", matched ? "matched" : "not_selected")
        && setNumber(dictionary, "TotalReadCount",
                     result.boot0.readCount + result.boot42.readCount, 32)
        && setString(dictionary, "SourceCommit", "1a82fbfda8f321b056eb3568850f9316c5e465c5");
    if (ok && matched)
        ok = setString(dictionary, "Chip", "TU117")
            && setNumber(dictionary, "VariantIndex", 41, 32);
    if (!ok) {
        dictionary->release();
        return nullptr;
    }
    return dictionary;
}

OSDictionary *copySnapshot(IOPCIDevice *device,
                          const S540NvidiaPCIProbePolicy::Identity &identity) {
    OSDictionary *snapshot = OSDictionary::withCapacity(21);
    if (!snapshot)
        return nullptr;

    // One additional fixed config read captures command/status without changing
    // memory decoding, I/O decoding, bus mastering, or any status bits.
    const uint32_t commandStatus = device->configRead32(0x04);
    bool ok = setNumber(snapshot, "Format", 8, 32)
        && setString(snapshot, "ProbeVersion", "0.8.0")
        && setString(snapshot, "Stage", "attached")
        && setString(snapshot, "AccessPolicy", "two-read-only-bar0-hal-identification")
        && setNumber(snapshot, "VendorID", identity.vendorDevice & 0xffffU, 16)
        && setNumber(snapshot, "DeviceID", identity.vendorDevice >> 16, 16)
        && setNumber(snapshot, "SubsystemVendorID", identity.subsystem & 0xffffU, 16)
        && setNumber(snapshot, "SubsystemID", identity.subsystem >> 16, 16)
        && setNumber(snapshot, "RevisionID", identity.revisionClass & 0xffU, 8)
        && setNumber(snapshot, "ClassCode", identity.revisionClass >> 8, 32)
        && setNumber(snapshot, "Command", commandStatus & 0xffffU, 16)
        && setNumber(snapshot, "Status", commandStatus >> 16, 16);
    if (!ok) {
        snapshot->release();
        return nullptr;
    }

    // IOService::start is a sleepable thread context. The same finite combined
    // CPU entry point runs in native CI. Its nonblocking singleton lease
    // protects the reserve lifecycle. The preparation layer separately guards
    // provider access and releases owned resources before the two MMIO reads.
    const S540NvidiaHardwareRuntime::IntegratedResult integrated =
        S540NvidiaHardwareRuntime::checkIntegrated(device);
    if (!integrated.acquired) {
        snapshot->release();
        return nullptr;
    }
    const S540NvidiaRuntime::Result &foundations = integrated.v7.v6.v5.foundations;
    ScopedRelease<OSDictionary> foundationSnapshot(OSDictionary::withCapacity(8));
    OSDictionary *foundation = foundationSnapshot.get();
    ok = foundation
        && setNumber(foundation, "Version", 1, 32)
        && setString(foundation, "Status", foundations.passed() ? "passed" : "failed")
        && setNumber(foundation, "Checks", foundations.checks, 32)
        && foundation->setObject("Timer", foundations.timer ? kOSBooleanTrue : kOSBooleanFalse)
        && foundation->setObject("Memory", foundations.memory ? kOSBooleanTrue : kOSBooleanFalse)
        && foundation->setObject("Atomics", foundations.atomics ? kOSBooleanTrue : kOSBooleanFalse)
        && foundation->setObject("Allocation", foundations.allocation ? kOSBooleanTrue : kOSBooleanFalse)
        && foundation->setObject("Mutex", foundations.mutex ? kOSBooleanTrue : kOSBooleanFalse)
        && snapshot->setObject("OSFoundations", foundation);
    const S540NvidiaCallerRuntime::Result &callers = integrated.v7.v6.v5.callers;
    ScopedRelease<OSDictionary> callerSnapshot(OSDictionary::withCapacity(6));
    OSDictionary *caller = callerSnapshot.get();
    ok = ok && caller
        && setNumber(caller, "Version", S540NvidiaCallerRuntime::kFormatVersion, 32)
        && setString(caller, "Status", callers.passed() ? "passed" : "failed")
        && setNumber(caller, "Checks", callers.checks, 32)
        && caller->setObject("AllocationCallers", callers.allocationCallers ? kOSBooleanTrue : kOSBooleanFalse)
        && caller->setObject("MutexCallers", callers.mutexCallers ? kOSBooleanTrue : kOSBooleanFalse)
        && caller->setObject("Reserve", callers.reserve ? kOSBooleanTrue : kOSBooleanFalse)
        && snapshot->setObject("CallerIntegration", caller);
    const S540NvidiaLifecycleRuntime::Result &lifecycle = integrated.v7.v6.lifecycle;
    ScopedRelease<OSDictionary> lifecycleSnapshot(OSDictionary::withCapacity(8));
    OSDictionary *nvport = lifecycleSnapshot.get();
    ok = ok && nvport
        && setNumber(nvport, "Version", S540NvidiaLifecycleRuntime::kFormatVersion, 32)
        && setString(nvport, "Status", lifecycle.passed() ? "passed" : "failed")
        && setNumber(nvport, "Checks", lifecycle.checks, 32)
        && nvport->setObject("Lifecycle", lifecycle.lifecycle ? kOSBooleanTrue : kOSBooleanFalse)
        && nvport->setObject("TrackedAllocation", lifecycle.trackedAllocation ? kOSBooleanTrue : kOSBooleanFalse)
        && nvport->setObject("OwnedMutex", lifecycle.ownedMutex ? kOSBooleanTrue : kOSBooleanFalse)
        && nvport->setObject("Spinlocks", lifecycle.spinlocks ? kOSBooleanTrue : kOSBooleanFalse)
        && nvport->setObject("Cleanup", lifecycle.cleanup ? kOSBooleanTrue : kOSBooleanFalse)
        && snapshot->setObject("NvPortLifecycle", nvport);
    const S540NvidiaSupportRuntime::Result &support = integrated.v7.support;
    ScopedRelease<OSDictionary> supportSnapshot(OSDictionary::withCapacity(7));
    OSDictionary *runtime = supportSnapshot.get();
    ok = ok && runtime
        && setNumber(runtime, "Version", S540NvidiaSupportRuntime::kFormatVersion, 32)
        && setString(runtime, "Status", support.passed() ? "passed" : "failed")
        && setNumber(runtime, "Checks", support.checks, 32)
        && runtime->setObject("Core", support.core ? kOSBooleanTrue : kOSBooleanFalse)
        && runtime->setObject("Utilities", support.utilities ? kOSBooleanTrue : kOSBooleanFalse)
        && runtime->setObject("Consumer", support.consumer ? kOSBooleanTrue : kOSBooleanFalse)
        && runtime->setObject("Cleanup", support.cleanup ? kOSBooleanTrue : kOSBooleanFalse)
        && snapshot->setObject("NvPortSupport", runtime);
    const S540NvidiaHardwareRuntime::Result &preparation = integrated.preparation;
    ScopedRelease<OSDictionary> preparationSnapshot(OSDictionary::withCapacity(25));
    OSDictionary *hardware = preparationSnapshot.get();
    ok = ok && hardware
        && setNumber(hardware, "Version", S540NvidiaHardwareRuntime::kFormatVersion, 32)
        && setString(hardware, "Status", preparation.passed() ? "passed" : "failed")
        && setNumber(hardware, "Checks", preparation.checks, 32)
        && hardware->setObject("HostDma", preparation.hostDma ? kOSBooleanTrue : kOSBooleanFalse)
        && hardware->setObject("PciReadAdapter", preparation.pciReadAdapter ? kOSBooleanTrue : kOSBooleanFalse)
        && hardware->setObject("InterruptInventory", preparation.interruptInventory ? kOSBooleanTrue : kOSBooleanFalse)
        && hardware->setObject("FirmwareParser", preparation.firmwareParser ? kOSBooleanTrue : kOSBooleanFalse)
        && hardware->setObject("FirmwareRpc", preparation.firmwareRpc ? kOSBooleanTrue : kOSBooleanFalse)
        && hardware->setObject("Cleanup", preparation.cleanup ? kOSBooleanTrue : kOSBooleanFalse)
        && setString(hardware, "DmaMode", preparation.dmaMode)
        && setNumber(hardware, "DmaBytes", preparation.dmaBytes, 64)
        && setNumber(hardware, "DmaSegments", preparation.dmaSegments, 32)
        && setString(hardware, "DmaReason", preparation.dmaReason)
        && setString(hardware, "PciReason", preparation.pciReason)
        && setNumber(hardware, "PciCapabilities", preparation.pciCapabilities, 32)
        && setNumber(hardware, "MsiVectors", preparation.msiVectors, 32)
        && setNumber(hardware, "MsixVectors", preparation.msixVectors, 32)
        && hardware->setObject("MsiObservedEnabled", preparation.msiObservedEnabled ? kOSBooleanTrue : kOSBooleanFalse)
        && hardware->setObject("MsixObservedEnabled", preparation.msixObservedEnabled ? kOSBooleanTrue : kOSBooleanFalse)
        && hardware->setObject("FirmwareLoaded", kOSBooleanFalse)
        && hardware->setObject("FirmwareImageVerified", kOSBooleanFalse)
        && hardware->setObject("InterruptsEnabled", kOSBooleanFalse)
        && hardware->setObject("GpuInitialized", kOSBooleanFalse)
        && hardware->setObject("RmInitialized", kOSBooleanFalse)
        && hardware->setObject("DeviceDmaVerified", kOSBooleanFalse)
        && snapshot->setObject("HardwarePreparation", hardware);
    if (!ok) {
        snapshot->release();
        return nullptr;
    }

    IOMemoryDescriptor *bar0 = nullptr;
    OSArray *resources = copyResourceMetadata(device, &bar0);
    ScopedRelease<IOMemoryDescriptor> bar0Owner(bar0);
    if (resources) {
        ok = snapshot->setObject("BARDescriptors", resources);
        resources->release();
    }
    if (!ok) {
        snapshot->release();
        return nullptr;
    }
    // The service remains attached on MMIO refusal. Missing resource metadata
    // is explicit and is not fabricated as a list of absent BARs.
    const IdentificationOutcome outcome = attemptIdentificationReads(device, bar0, resources != nullptr);
    OSDictionary *mmio = copyMMIOResult(outcome.boot0, false);
    OSDictionary *boot42 = copyMMIOResult(outcome.boot42, true);
    OSDictionary *selection = copyHALSelection(outcome);
    ok = mmio && boot42 && selection;
    if (ok)
        ok = snapshot->setObject("MMIOResult", mmio)
            && snapshot->setObject("BOOT42Result", boot42)
            && snapshot->setObject("HALSelection", selection);
    if (mmio) mmio->release();
    if (boot42) boot42->release();
    if (selection) selection->release();
    if (!ok) {
        snapshot->release();
        return nullptr;
    }
    return snapshot;
}
}

IOService *S540NvidiaPCIProbe::probe(IOService *provider, SInt32 *score) {
    if (!super::probe(provider, score))
        return nullptr;
    IOPCIDevice *device = OSDynamicCast(IOPCIDevice, provider);
    if (!device || !S540NvidiaPCIProbePolicy::matches(readIdentity(device)))
        return nullptr;
    return this;
}

bool S540NvidiaPCIProbe::start(IOService *provider) {
    if (!super::start(provider))
        return false;

    IOPCIDevice *device = OSDynamicCast(IOPCIDevice, provider);
    if (!device) {
        super::stop(provider);
        return false;
    }
    // Recheck actual PCI config after matching: stale/forged registry properties
    // and inaccessible hardware (including vendor 0xffff) must not attach.
    const S540NvidiaPCIProbePolicy::Identity identity = readIdentity(device);
    if (!S540NvidiaPCIProbePolicy::matches(identity)) {
        super::stop(provider);
        return false;
    }

    OSDictionary *snapshot = copySnapshot(device, identity);
    if (!snapshot) {
        super::stop(provider);
        return false;
    }
    const bool published = setProperty(kSnapshotKey, snapshot);
    snapshot->release();
    if (!published) {
        removeProperty(kSnapshotKey);
        super::stop(provider);
        return false;
    }

    // Publish our own service/property only. Do not open or modify the provider.
    // No callbacks, periodic polling, power policy, firmware, or user client.
    registerService();
    return true;
}

void S540NvidiaPCIProbe::stop(IOService *provider) {
    removeProperty(kSnapshotKey);
    super::stop(provider);
}
