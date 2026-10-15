// SPDX-License-Identifier: MIT
#include "S540NvidiaPCIProbe.hpp"

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

MMIOOutcome attemptIdentificationRead(IOPCIDevice *device,
                                      IOMemoryDescriptor *bar0,
                                      bool metadataAvailable) {
    MMIOOutcome result = {"refused", "resource-metadata-unavailable", 0, 0};
    if (!metadataAvailable)
        return result;
    if (!bar0) {
        result.reason = "bar0-descriptor-missing";
        return result;
    }

    // Arbitration serializes compliant open/close/termination, without opening
    // the PCI provider (whose open path may change hardware resource state).
    // It does not freeze platform power management. D0 is rechecked below.
    ScopedArbitration arbitration(device);
    if (!arbitration.acquired()) {
        result.reason = "provider-arbitration-unavailable";
        return result;
    }
    if (device->isOpen()) {
        result.reason = "provider-already-open";
        return result;
    }
    const char *reason = checkReadPrerequisites(device, bar0);
    if (reason) {
        result.reason = reason;
        return result;
    }

    // Request only BOOT0. The VM mapping itself has page granularity; this
    // request does not make a four-byte physical aperture or a recoverable
    // hardware timeout. A single stalled MMIO load can still stall the kernel.
    ScopedRelease<IOMemoryMap> mapping(bar0->createMappingInTask(kernel_task, 0,
        kIOMapAnywhere | kIOMapReadOnly | kIOMapInhibitCache | kIOMapUnique, 0, 4));
    if (!mapping.get()) {
        result.reason = "mapping-unavailable";
        return result;
    }
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

    // Intel x86_64, exactly one aligned 32-bit volatile load. No retries,
    // registers beyond NV_PMC_BOOT_0, writes, polling, or arbitrary offsets.
    const volatile uint32_t *boot0 = reinterpret_cast<const volatile uint32_t *>(address);
    result.rawValue = *boot0;
    result.readCount = 1;
    mapping.reset();
    result.reason = S540NvidiaPCIProbePolicy::identifyBoot0(result.rawValue);
    result.status = S540NvidiaPCIProbePolicy::architecture(result.rawValue) == 0x16U
        && S540NvidiaPCIProbePolicy::implementation(result.rawValue) == 7U
        && result.rawValue != 0 && result.rawValue != UINT32_MAX
        ? "identified" : "failed";
    return result;
}

OSDictionary *copyMMIOResult(const MMIOOutcome &result) {
    OSDictionary *dictionary = OSDictionary::withCapacity(9);
    if (!dictionary)
        return nullptr;
    bool ok = setString(dictionary, "Status", result.status)
        && setString(dictionary, "Reason", result.reason)
        && setNumber(dictionary, "ReadCount", result.readCount, 32)
        && setNumber(dictionary, "BarIndex", 0, 32)
        && setNumber(dictionary, "Offset", 0, 32)
        && setNumber(dictionary, "Width", 32, 32);
    if (ok && result.readCount == 1) {
        ok = setNumber(dictionary, "RawValue", result.rawValue, 32)
            && setNumber(dictionary, "Architecture",
                         S540NvidiaPCIProbePolicy::architecture(result.rawValue), 32)
            && setNumber(dictionary, "Implementation",
                         S540NvidiaPCIProbePolicy::implementation(result.rawValue), 32);
    }
    if (!ok) {
        dictionary->release();
        return nullptr;
    }
    return dictionary;
}

OSDictionary *copySnapshot(IOPCIDevice *device,
                          const S540NvidiaPCIProbePolicy::Identity &identity) {
    OSDictionary *snapshot = OSDictionary::withCapacity(15);
    if (!snapshot)
        return nullptr;

    // One additional fixed config read captures command/status without changing
    // memory decoding, I/O decoding, bus mastering, or any status bits.
    const uint32_t commandStatus = device->configRead32(0x04);
    bool ok = setNumber(snapshot, "Format", 2, 32)
        && setString(snapshot, "ProbeVersion", "0.2.0")
        && setString(snapshot, "Stage", "attached")
        && setString(snapshot, "AccessPolicy", "single-read-only-bar0-identification")
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
    const MMIOOutcome outcome = attemptIdentificationRead(device, bar0, resources != nullptr);
    OSDictionary *mmio = copyMMIOResult(outcome);
    if (mmio) {
        ok = ok && snapshot->setObject("MMIOResult", mmio);
        mmio->release();
    } else {
        ok = false;
    }
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
