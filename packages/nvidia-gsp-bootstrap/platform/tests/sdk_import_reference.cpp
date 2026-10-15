// SPDX-License-Identifier: MIT
// Independent pinned-SDK API reference. Never linked into the driver.
#include <IOKit/IOLib.h>
#include <IOKit/IOService.h>
#include <IOKit/IORegistryEntry.h>
#include <IOKit/IODeviceTreeSupport.h>
#include <IOKit/pci/IOPCIDevice.h>
#include <IOKit/acpi/IOACPIPlatformDevice.h>
#include <IOKit/graphics/IOFramebuffer.h>
#include <libkern/c++/OSArray.h>
#include <libkern/c++/OSData.h>
#include <libkern/c++/OSNumber.h>
#include <libkern/c++/OSSerialize.h>
#include <libkern/c++/OSString.h>
#include <libkern/c++/OSUnserialize.h>
#include <libkern/version.h>
#include <machine/machine_routines.h>
#include <pexpert/pexpert.h>

extern "C" unsigned int real_ncpus;
extern "C" void *gPEEFISystemTable;

extern "C" unsigned long long s540GspPlatformSdkGlobals() {
    return real_ncpus + gPEClockFrequencyInfo.cpu_frequency_hz +
        (gPEEFISystemTable != nullptr) + version_major + version_minor +
        version_revision + unsigned(osrelease[0]) + unsigned(version[0]) +
        ml_at_interrupt_context() + ml_get_interrupts_enabled();
}

extern "C" void s540GspPlatformSdkBulk(void *destination, const void *source,
                                      unsigned long length) {
    bzero(destination, length);
    bcopy(source, destination, length);
    (void)memcpy(destination, source, length);
    (void)memmove(destination, source, length);
}

struct S540PlatformSdkZeroState { unsigned long long values[48]; };
extern "C" void s540GspPlatformSdkZero(S540PlatformSdkZeroState *state) {
    // Let the actual kernel compiler select its zero-initialization helper.
    // No handwritten prototype for an otherwise undeclared compiler helper.
    *state = S540PlatformSdkZeroState{};
}

extern "C" void s540GspPlatformSdkQueries(IOPCIDevice *pci,
    IOACPIPlatformDevice *acpi, IOFramebuffer *fb, IORegistryEntry *entry,
    OSObject *object, char *destination) {
    const IORegistryPlane *plane = IORegistryEntry::getPlane("IOACPIPlane");
    IORegistryEntry *path = IORegistryEntry::fromPath("IOACPIPlane:/");
    IORegistryIterator *walk = path ? IORegistryIterator::iterateOver(path, plane, kIORegistryIterateRecursively) : nullptr;
    OSDictionary *match = IOService::serviceMatching("IOPCIDevice");
    OSIterator *iterator = match ? IOService::getMatchingServices(match) : nullptr;
    IOService *found = match ? IOService::copyMatchingService(match) : nullptr;
    IORegistryEntry *parent = entry->copyParentEntry(gIOServicePlane);
    OSObject *property = entry->copyProperty("acpi-path");
    OSString *string = OSDynamicCast(OSString, property);
    if (string) { (void)string->getLength(); (void)string->getCStringNoCopy(); (void)string->isEqualTo("PNP0A08"); }
    OSData *data = OSDynamicCast(OSData, object);
    if (data) { (void)data->getLength(); (void)data->getBytesNoCopy(); }
    OSNumber *number = OSNumber::withNumber(UInt64(1), 32);
    OSNumber *numberCast = OSDynamicCast(OSNumber, object);
    if (numberCast) { (void)numberCast->unsigned32BitValue(); (void)numberCast->unsigned64BitValue(); }
    OSArray *array = OSDynamicCast(OSArray, object);
    if (array) { (void)array->getCount(); (void)array->getObject(0); }
    (void)OSDynamicCast(OSSerializer, object);
    (void)OSDynamicCast(IOACPIPlatformDevice, entry);
    (void)OSDynamicCast(IOPCIDevice, entry);
    (void)OSDynamicCast(IOFramebuffer, fb);
    OSSerialize *serializer = OSSerialize::withCapacity(4096);
    OSObject *decoded = nullptr;
    if (serializer) {
        (void)object->serialize(serializer);
        decoded = OSUnserializeXML(serializer->text(), serializer->getLength());
    }
    UInt64 integer = 0;
    OSObject *result = nullptr;
    OSObject *arguments[2] = {number, number};
    (void)acpi->validateObject("_SEG");
    (void)acpi->evaluateObject("_ROM", &result, arguments, 2);
    (void)acpi->evaluateInteger("_SEG", &integer);
    (void)acpi->getACPITableData("FACP");
    (void)fb->isConsoleDevice();
    (void)pci->isInactive();
    if (pci->lockForArbitration(false)) {
        (void)pci->getBusNumber(); (void)pci->getDeviceNumber(); (void)pci->getFunctionNumber();
        (void)pci->configRead8(UInt8(0)); (void)pci->configRead16(UInt8(0)); (void)pci->configRead32(UInt8(0));
        IODeviceMemory *memory = pci->getDeviceMemoryWithRegister(0x10);
        if (memory) {
            IOByteCount length = 0;
            (void)memory->getPhysicalSegment(0, &length, kIOMemoryMapperNone);
            (void)memory->getLength();
        }
        pci->unlockForArbitration();
    }
    void *allocation = IOMalloc(64);
    if (allocation) { bzero(allocation, 64); bcopy(allocation, destination, 1); IOFree(allocation, 64); }
    if (iterator) { (void)iterator->getNextObject(); (void)iterator->isValid(); iterator->release(); }
    if (walk) { (void)walk->getNextObject(); (void)walk->isValid(); walk->release(); }
    if (found) found->release();
    if (match) match->release();
    if (parent) parent->release();
    if (property) property->release();
    if (number) number->release();
    if (result) result->release();
    if (decoded) decoded->release();
    if (serializer) serializer->release();
    if (path) path->release();
}
