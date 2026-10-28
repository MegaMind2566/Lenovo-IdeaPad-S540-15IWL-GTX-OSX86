/* SPDX-License-Identifier: MIT; independent public SDK declaration probe. */
#include <IOKit/pci/IOPCIBridge.h>
#include <IOKit/pci/IOPCIDevice.h>
extern "C" UInt32 s540PciTopologySdkImportReference(IORegistryEntry *entry,
    IOPCIAddressSpace space, UInt8 offset) {
    IOPCIBridge *bridge = OSDynamicCast(IOPCIBridge, entry);
    IOPCIDevice *device = OSDynamicCast(IOPCIDevice, entry);
    IORegistryEntry *parent = entry ? entry->copyParentEntry(gIOServicePlane) : nullptr;
    UInt32 result = 0U;
    if (bridge && !bridge->isInactive()) {
        result = bridge->configRead32(space, offset);
        result ^= bridge->configRead16(space, offset);
        result ^= bridge->configRead8(space, offset);
        result ^= bridge->firstBusNum(); result ^= bridge->lastBusNum();
    }
    if (device && !device->isInactive()) {
        result ^= device->extendedConfigRead32(0x100U);
        result ^= device->extendedConfigRead16(0x100U);
        result ^= device->extendedConfigRead8(0x100U);
    }
    if (parent) parent->release();
    return result;
}
