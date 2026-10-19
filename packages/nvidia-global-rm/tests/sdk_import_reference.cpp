// SPDX-License-Identifier: MIT
// Independent pinned-SDK operations used by the actual RM log formatter.
#include <IOKit/IOLib.h>
#include <libkern/OSDebug.h>
#include <IOKit/IORegistryEntry.h>
#include <IOKit/IOMemoryDescriptor.h>
#include <libkern/c++/OSData.h>

extern "C" int s540GlobalRmSdkDevicePrefix(char *buffer, size_t bytes,
    unsigned domain, unsigned bus, unsigned slot, unsigned function,
    const char *severity, unsigned xid)
{
    return snprintf(buffer, bytes, "S540 NVIDIA %04x:%02x:%02x.%x %s Xid %u: ",
                    domain, bus, slot, function, severity, xid);
}

extern "C" unsigned s540GlobalRmSdkStackTrace(void **frames, unsigned count)
{
    return OSBacktrace(frames, count);
}

// Independent public-SDK declarations used by the EFI table backend. This
// control is never linked into the runtime and makes no physical-read claim.
extern "C" IOReturn s540GlobalRmSdkFirmwareRead(const char *path,
    mach_vm_address_t address, void *bytes, IOByteCount count)
{
    IORegistryEntry *entry = IORegistryEntry::fromPath(path);
    if (!entry) return kIOReturnNotFound;
    OSObject *object = entry->copyProperty("table");
    OSData *data = OSDynamicCast(OSData, object);
    if (data) { (void)data->getLength(); (void)data->getBytesNoCopy(); }
    if (object) object->release();
    entry->release();
    IOMemoryDescriptor *memory = IOMemoryDescriptor::withAddressRange(
        address, count, kIODirectionIn | kIOMemoryMapperNone, nullptr);
    if (!memory) return kIOReturnNoMemory;
    IOReturn status = memory->prepare(kIODirectionIn);
    if (status == kIOReturnSuccess) {
        if (memory->readBytes(0, bytes, count) != count) status = kIOReturnUnderrun;
        IOReturn completed = memory->complete(kIODirectionIn);
        if (completed != kIOReturnSuccess) status = completed;
    }
    memory->release();
    return status;
}
