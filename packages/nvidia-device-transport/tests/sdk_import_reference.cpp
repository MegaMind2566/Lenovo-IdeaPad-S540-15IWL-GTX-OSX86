// SPDX-License-Identifier: MIT
// Independent compile-only SDK contract. Never linked into the runtime.
#include <IOKit/IOBufferMemoryDescriptor.h>
#include <IOKit/IODMACommand.h>
#include <IOKit/IOMapper.h>
#include <IOKit/IOLib.h>
#include <IOKit/pci/IOPCIDevice.h>
#include <kern/thread_call.h>
#include <machine/machine_routines.h>
#define REF(name) do { auto volatile pointer = &name; (void)pointer; } while (0)
extern "C" void s540DeviceTransportSdkCalls() {
    REF(IOMalloc); REF(IOFree); REF(bzero); REF(IOSleep);
    REF(ml_at_interrupt_context); REF(ml_get_interrupts_enabled);
    REF(IOSimpleLockAlloc); REF(IOSimpleLockFree);
    REF(IOSimpleLockLockDisableInterrupt); REF(IOSimpleLockUnlockEnableInterrupt);
    REF(thread_call_allocate_with_options); REF(thread_call_enter);
    REF(thread_call_cancel); REF(thread_call_isactive); REF(thread_call_free);
}
extern "C" IOBufferMemoryDescriptor *s540DeviceTransportSdkBuffer() {
    return IOBufferMemoryDescriptor::withOptions(kIODirectionInOut | kIOMemoryMapperNone |
        kIOMapCopybackCache, 4096, 4096);
}
extern "C" IODMACommand *s540DeviceTransportSdkDma(IOMapper *mapper, bool direct) {
    return IODMACommand::withSpecification(kIODMACommandOutputHost64, 32, 4096,
        direct ? IODMACommand::kUnmapped : IODMACommand::kMapped,
        4096, 4096, mapper, nullptr);
}
extern "C" IOMapper *s540DeviceTransportSdkMapper(OSObject *object) {
    return OSDynamicCast(IOMapper, object);
}
extern "C" IOMapper *s540DeviceTransportSdkSystemMapper() {
    return __atomic_load_n(&IOMapper::gSystem, __ATOMIC_ACQUIRE);
}
extern "C" bool s540DeviceTransportSdkProvider(IOPCIDevice *provider, IOService *owner) {
    const bool acquired = provider->lockForArbitration(false);
    if (!acquired) return false;
    OSObject *property = provider->copyProperty("iommu-parent");
    if (property) property->release();
    const bool opened = provider->open(owner);
    if (opened) provider->close(owner);
    provider->unlockForArbitration();
    return opened;
}
#undef REF
extern "C" UInt64 s540DeviceTransportSdkGeometry(IOMemoryMap *mapping,
    IOPCIDevice *provider, UInt32 offset, UInt32 value) {
    UInt64 result = mapping->getPhysicalAddress();
    result += provider->isInactive();
    result += provider->extendedConfigRead8(offset);
    result += provider->extendedConfigRead16(offset);
    result += provider->extendedConfigRead32(offset);
    provider->extendedConfigWrite8(offset, static_cast<UInt8>(value));
    provider->extendedConfigWrite16(offset, static_cast<UInt16>(value));
    provider->extendedConfigWrite32(offset, value);
    return result;
}
struct S540DeviceTransportSdkPod { void *slots[512]; };
extern "C" void s540DeviceTransportSdkAggregate(S540DeviceTransportSdkPod *zero,
    S540DeviceTransportSdkPod *destination, const S540DeviceTransportSdkPod *source) {
    *zero = S540DeviceTransportSdkPod{};
    *destination = *source;
}
