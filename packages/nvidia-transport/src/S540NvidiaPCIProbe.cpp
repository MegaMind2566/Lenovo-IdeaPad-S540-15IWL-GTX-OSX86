// SPDX-License-Identifier: MIT
#include "S540NvidiaPCIProbe.hpp"

#include <IOKit/IOMemoryDescriptor.h>
#include <libkern/c++/OSArray.h>
#include <libkern/c++/OSBoolean.h>
#include <libkern/c++/OSDictionary.h>
#include <libkern/c++/OSNumber.h>
#include <libkern/c++/OSString.h>

#define super IOService
OSDefineMetaClassAndStructors(S540NvidiaPCIProbe, IOService)

namespace {
const char * const kSnapshotKey = "S540NvidiaPCIProbeSnapshot";

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

OSArray *copyResourceMetadata(IOPCIDevice *device) {
    // Read the already-published resource array directly. PCI convenience
    // getters can change tunnel link power policy; this path avoids them.
    // The array and its descriptors are borrowed. Do not release or mutate them.
    OSArray *published = OSDynamicCast(OSArray, device->getProperty("IODeviceMemory"));
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
    return resources;
}

OSDictionary *copySnapshot(IOPCIDevice *device,
                          const S540NvidiaPCIProbePolicy::Identity &identity) {
    OSDictionary *snapshot = OSDictionary::withCapacity(14);
    if (!snapshot)
        return nullptr;

    // One additional fixed config read captures command/status without changing
    // memory decoding, I/O decoding, bus mastering, or any status bits.
    const uint32_t commandStatus = device->configRead32(0x04);
    bool ok = commandStatus != UINT32_MAX
        && setNumber(snapshot, "Format", 1, 32)
        && setString(snapshot, "ProbeVersion", "0.1.0")
        && setString(snapshot, "Stage", "attached")
        && setString(snapshot, "AccessPolicy", "config-read-and-resource-metadata-only")
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

    OSArray *resources = copyResourceMetadata(device);
    if (resources) {
        ok = snapshot->setObject("BARDescriptors", resources);
        resources->release();
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
