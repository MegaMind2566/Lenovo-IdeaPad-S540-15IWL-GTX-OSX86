// SPDX-License-Identifier: MIT
#include "S540NvidiaDeviceTransport.hpp"
#if defined(KERNEL)
#include "../../nvidia-hardware-transport/src/S540NvidiaPci.hpp"
#include <IOKit/IOBufferMemoryDescriptor.h>
#include <IOKit/IODMACommand.h>
#include <IOKit/IOMapper.h>
#include <IOKit/IOLib.h>
#include <IOKit/pci/IOPCIDevice.h>
#include <libkern/OSByteOrder.h>
#include <kern/thread_call.h>
#include <machine/machine_routines.h>
namespace S540NvidiaDeviceTransport { void destroyDarwinBackend(void *); }
namespace {
using namespace S540NvidiaDeviceTransport;
constexpr NvU64 kMaximumHostBytes = 128ULL * 1024 * 1024;
struct RegisterView { void *address; NvU64 bytes; };
struct Platform {
    IOPCIDevice *provider;
    IOService *owner;
    IOMemoryMap *registers;
    IOMapper *mapper;
    Mapper mapperMode;
    NvU64 hostBytes;
    RegisterView registerViews[32];
    bool retained;
    bool opened;
    NvU16 initialCommand;
    bool commandChanged;
    NvU16 initialHeaderControl;
    NvU32 initialRom;
    bool headerChanged;
    bool romChanged;
    bool irqRegistered;
    bool controllerAttached;
    bool irqEnabled;
    bool accepting;
    NvU32 callbacks;
    NvU32 pending;
    InterruptStatistics statistics;
    IOSimpleLock *isrLock;
    thread_call_t bottomHalf;
    InterruptContract interrupt;
};
struct Allocation {
    IOBufferMemoryDescriptor *buffer;
    IODMACommand *command;
    NvU64 *physical;
    NvU64 *device;
    NvU32 pages;
    bool contiguous;
    bool bufferPrepared;
    bool attached;
    bool commandAttempted;
    bool commandPrepared;
    bool quarantined;
};
bool ordinary(void *) { return !ml_at_interrupt_context() && ml_get_interrupts_enabled(); }
bool live(void *opaque) {
    auto *p = static_cast<Platform *>(opaque);
    return p->retained && p->opened && p->provider && !p->provider->isInactive();
}
NV_STATUS start(void *opaque, Snapshot &snapshot) {
    auto *p = static_cast<Platform *>(opaque);
    if (!p->provider || !p->owner || !ordinary(nullptr)) return NV_ERR_INVALID_ARGUMENT;
    if (!p->provider->lockForArbitration(false)) return NV_ERR_BUSY_RETRY;
    Snapshot value{};
    S540NvidiaPci::Context pci;
    bool ok = !p->provider->isInactive() && pci.bind(p->provider);
    S540NvidiaPci::Inventory inventory{};
    if (ok) inventory = pci.inventory();
    pci.unbind();
    value.identity = ok;
    value.bus = p->provider->getBusNumber();
    value.device = p->provider->getDeviceNumber();
    value.function = p->provider->getFunctionNumber();
    p->initialCommand = inventory.command;
    p->initialHeaderControl = p->provider->configRead16(static_cast<UInt8>(0x0c));
    p->initialRom = p->provider->configRead32(static_cast<UInt8>(0x30));
    value.memoryDecode = inventory.valid && (inventory.command & 2U);
    value.busMaster = inventory.valid && (inventory.command & 4U);
    int interruptType = 0;
    value.interruptTypeKnown = p->provider->getInterruptType(0,&interruptType) == kIOReturnSuccess;
    value.interruptType = static_cast<NvU32>(interruptType);
    value.messageSignaled = value.interruptTypeKnown && (interruptType & kIOInterruptTypePCIMessaged);
    value.msiEnabled = inventory.valid && inventory.msiEnabled;
    value.msixEnabled = inventory.valid && inventory.msixEnabled;
    value.powerD0 = inventory.valid && inventory.pmOffset != 0 && inventory.powerState == 0;
    if (value.identity && value.memoryDecode && value.powerD0) {
        p->provider->retain(); p->owner->retain(); p->retained = true;
        p->opened = p->provider->open(p->owner);
        value.providerOwned = p->opened;
        if (p->opened) {
            p->registers = p->provider->mapDeviceMemoryWithRegister(0x10, kIOMapInhibitCache);
            value.barMapped = p->registers && p->registers->getVirtualAddress() &&
                p->registers->getLength() >= 0x1804 && p->registers->getLength() <= 0x1000000;
            if (p->registers) value.barBytes = p->registers->getLength();
            // Do not call copyMapperForDevice(): an unresolved registry ID can
            // wait without deadline. Absence of iommu-parent and direct CPU
            // addresses never establish device-address translation readiness.
            OSObject *property = p->provider->copyProperty("iommu-parent");
            const bool propertyPresent = property != nullptr;
            if (property) {
                p->mapper = OSDynamicCast(IOMapper, property);
                if (p->mapper) p->mapper->retain();
                property->release();
            }
            const bool noSystemMapper = __atomic_load_n(&IOMapper::gSystem, __ATOMIC_ACQUIRE) == nullptr;
            value.mapper = selectMapperPolicy(propertyPresent, p->mapper != nullptr, noSystemMapper);
            p->mapperMode = value.mapper;
            value.dmaPolicySettled = value.mapper != Mapper::Unavailable;
            // Original Linux provider setup starts with a 32-bit DMA mask;
            // osinit RmInitDma later requests the GPU's verified address width.
            value.dmaAddressBits = 32;
        }
    }
    p->provider->unlockForArbitration();
    if (!value.identity || !value.providerOwned || !value.memoryDecode ||
        !value.powerD0 || !value.barMapped) {
        if (p->registers) { p->registers->release(); p->registers = nullptr; }
        if (p->mapper) { p->mapper->release(); p->mapper = nullptr; }
        if (p->opened) { p->provider->close(p->owner); p->opened = false; }
        if (p->retained) {
            p->owner->release(); p->provider->release(); p->retained = false;
        }
        return NV_ERR_NOT_SUPPORTED;
    }
    snapshot = value;
    return NV_OK;
}
NV_STATUS stop(void *opaque) {
    auto *p = static_cast<Platform *>(opaque);
    if (p->irqRegistered || p->callbacks || p->hostBytes) return NV_ERR_IN_USE;
    for (const auto &view : p->registerViews) if (view.address) return NV_ERR_IN_USE;
    if (p->headerChanged || p->romChanged || p->commandChanged) {
        if (!live(p) || !p->provider->lockForArbitration(false)) return NV_ERR_INVALID_STATE;
        if (p->headerChanged) p->provider->configWrite16(static_cast<UInt8>(0x0c), p->initialHeaderControl);
        if (p->romChanged) p->provider->configWrite32(static_cast<UInt8>(0x30), p->initialRom);
        bool restored = true;
        if (p->commandChanged) {
            NvU16 command = p->provider->configRead16(static_cast<UInt8>(4));
            command = static_cast<NvU16>((command & ~4U) | (p->initialCommand & 4U));
            p->provider->configWrite16(static_cast<UInt8>(4), command);
            restored = p->provider->configRead16(static_cast<UInt8>(4)) == command;
        }
        p->provider->unlockForArbitration();
        if (!restored) return NV_ERR_OPERATING_SYSTEM;
        p->headerChanged = p->romChanged = p->commandChanged = false;
    }
    if (p->registers) { p->registers->release(); p->registers = nullptr; }
    if (p->mapper) { p->mapper->release(); p->mapper = nullptr; }
    if (p->opened) { p->provider->close(p->owner); p->opened = false; }
    if (p->retained) {
        p->owner->release(); p->provider->release(); p->retained = false;
    }
    return NV_OK;
}
NV_STATUS readIdentification(void *opaque, NvU32 offset, NvU32 &value) {
    auto *p = static_cast<Platform *>(opaque);
    if (!live(p) || !p->registers || (offset != 0 && offset != 0x1800))
        return NV_ERR_INVALID_STATE;
    // The startup check never calls this method, preserving the existing
    // probe's exactly two identification-register loads.
    value = OSReadLittleInt32(reinterpret_cast<const volatile void *>(
              p->registers->getVirtualAddress()), offset);
    return NV_OK;
}
NV_STATUS registerGeometry(void *opaque, NvU64 &physical, NvU64 &bytes) {
    auto *p = static_cast<Platform *>(opaque);
    if (!live(p) || !p->registers) return NV_ERR_INVALID_STATE;
    physical = p->registers->getPhysicalAddress();
    bytes = p->registers->getLength();
    return NV_OK;
}
NV_STATUS mapRegisters(void *opaque, NvU64 physical, NvU64 bytes, void **address) {
    auto *p = static_cast<Platform *>(opaque);
    if (!live(p) || !p->registers || !address || !bytes) return NV_ERR_INVALID_ARGUMENT;
    const NvU64 start = p->registers->getPhysicalAddress();
    const NvU64 length = p->registers->getLength();
    if (physical < start || physical - start >= length || bytes > length - (physical - start))
        return NV_ERR_INVALID_ADDRESS;
    for (auto &view : p->registerViews) if (!view.address) {
        view.address = reinterpret_cast<void *>(static_cast<NvUPtr>(
            p->registers->getVirtualAddress() + physical - start));
        view.bytes = bytes;
        *address = view.address;
        return NV_OK;
    }
    return NV_ERR_INSUFFICIENT_RESOURCES;
}
NV_STATUS unmapRegisters(void *opaque, void *address, NvU64 bytes) {
    auto *p = static_cast<Platform *>(opaque);
    if (!address || !bytes) return NV_ERR_INVALID_ARGUMENT;
    for (auto &view : p->registerViews) if (view.address == address && view.bytes == bytes) {
        view = RegisterView{};
        return NV_OK;
    }
    return NV_ERR_OBJECT_NOT_FOUND;
}

NV_STATUS configRead(void *opaque, NvU32 offset, NvU32 width, NvU32 &value) {
    auto *p = static_cast<Platform *>(opaque);
    if (!live(p) || !p->provider->lockForArbitration(false)) return NV_ERR_INVALID_STATE;
    const bool identity = p->provider->configRead32(static_cast<UInt8>(0)) == 0x1f9110de &&
        (p->provider->configRead32(static_cast<UInt8>(8)) & 0xffU) == 0xa1 &&
        p->provider->configRead32(static_cast<UInt8>(0x2c)) == 0x380617aa;
    NvU32 captured = 0;
    if (identity) {
        if (width == 1) captured = p->provider->extendedConfigRead8(offset);
        else if (width == 2) captured = p->provider->extendedConfigRead16(offset);
        else captured = p->provider->extendedConfigRead32(offset);
    }
    p->provider->unlockForArbitration();
    if (!identity) return NV_ERR_INVALID_STATE;
    value = captured;
    return NV_OK;
}
NV_STATUS configWrite(void *opaque, NvU32 offset, NvU32 width, NvU32 value) {
    auto *p = static_cast<Platform *>(opaque);
    NvU32 previous = 0;
    NV_STATUS status = configRead(p,offset,width,previous);
    if (status != NV_OK) return status;
    const PciWriteKind kind = pciWriteKind(offset,width,previous,value);
    if (kind == PciWriteKind::Refused) return NV_ERR_NOT_SUPPORTED;
    if (!p->provider->lockForArbitration(false)) return NV_ERR_BUSY_RETRY;
    if (!live(p) || p->provider->configRead32(static_cast<UInt8>(0)) != 0x1f9110de) {
        p->provider->unlockForArbitration(); return NV_ERR_INVALID_STATE;
    }
    if (width == 1) p->provider->extendedConfigWrite8(offset, static_cast<NvU8>(value));
    else if (width == 2) p->provider->extendedConfigWrite16(offset, static_cast<NvU16>(value));
    else p->provider->extendedConfigWrite32(offset,value);
    p->provider->unlockForArbitration();
    if (kind == PciWriteKind::CommandBusMaster) p->commandChanged = true;
    if (kind == PciWriteKind::RomDisable) p->romChanged = true;
    if (kind == PciWriteKind::LatencySetup) p->headerChanged = true;
    // PCIe devices may hardwire legacy cache/latency fields to zero. The public
    // SDK write returns void; do not fabricate a readback error for those RO
    // fields after performing the exact original, validated request.
    return NV_OK;
}

NV_STATUS allocate(void *opaque, NvU32 pages, bool contiguous, NvU32 cache,
                   void **output, NvU8 **host) {
    auto *p = static_cast<Platform *>(opaque);
    const NvU64 bytes = NvU64(pages) * kPageBytes;
    if (!live(p) || !pages || pages > kMaximumPages || !output || !host || cache > 2)
        return NV_ERR_INVALID_ARGUMENT;
    if (p->hostBytes > kMaximumHostBytes || bytes > kMaximumHostBytes - p->hostBytes)
        return NV_ERR_INSUFFICIENT_RESOURCES;
    auto *a = static_cast<Allocation *>(IOMalloc(sizeof(Allocation)));
    if (!a) return NV_ERR_NO_MEMORY;
    *a = Allocation{};
    a->pages = pages; a->contiguous = contiguous;
    a->physical = static_cast<NvU64 *>(IOMalloc(pages * sizeof(NvU64)));
    a->device = static_cast<NvU64 *>(IOMalloc(pages * sizeof(NvU64)));
    IOOptionBits options = kIODirectionInOut | kIOMemoryMapperNone;
    options |= cache == 1 ? kIOMapInhibitCache :
               cache == 2 ? kIOMapWriteCombineCache : kIOMapCopybackCache;
    if (contiguous) options |= kIOMemoryPhysicallyContiguous;
    if (a->physical && a->device)
        a->buffer = IOBufferMemoryDescriptor::withOptions(options, bytes, kPageBytes);
    bool ok = a->buffer && a->buffer->getLength() == bytes && a->buffer->getBytesNoCopy();
    if (ok) {
        ok = a->buffer->prepare(kIODirectionInOut) == kIOReturnSuccess;
        a->bufferPrepared = ok;
    }
    for (NvU32 i = 0; ok && i < pages; ++i) {
        IOByteCount length = 0;
        a->physical[i] = a->buffer->getPhysicalSegment(NvU64(i) * kPageBytes,
                                                       &length, kIOMemoryMapperNone);
        ok = a->physical[i] && length >= kPageBytes &&
            !(a->physical[i] & (kPageBytes - 1));
    }
    if (!ok) {
        if (a->bufferPrepared) (void)a->buffer->complete(kIODirectionInOut);
        if (a->buffer) a->buffer->release();
        if (a->device) IOFree(a->device, pages * sizeof(NvU64));
        if (a->physical) IOFree(a->physical, pages * sizeof(NvU64));
        IOFree(a, sizeof(*a));
        return NV_ERR_NO_MEMORY;
    }
    // NVIDIA requests uninitialized or zeroed pages. This supported profile
    // always zeroes owned kernel buffers before exposing them to the caller.
    bzero(a->buffer->getBytesNoCopy(), bytes);
    p->hostBytes += bytes;
    *host = static_cast<NvU8 *>(a->buffer->getBytesNoCopy());
    *output = a;
    return NV_OK;
}
NV_STATUS pageAddress(void *, void *opaque, NvU32 page, bool device, NvU64 &address) {
    auto *a = static_cast<Allocation *>(opaque);
    if (!a || page >= a->pages || (device && !a->commandPrepared))
        return NV_ERR_INVALID_ARGUMENT;
    address = device ? a->device[page] : a->physical[page];
    return NV_OK;
}
NV_STATUS unmapDma(void *, void *opaque) {
    auto *a = static_cast<Allocation *>(opaque);
    NV_STATUS result = NV_OK;
    if (!a || !a->command || a->quarantined) return NV_ERR_INVALID_STATE;
    if (a->commandAttempted) {
        IOReturn status = a->command->complete(true, true);
        if (status != kIOReturnSuccess && !(status == kIOReturnNotReady && !a->commandPrepared))
            result = NV_ERR_OPERATING_SYSTEM;
    }
    a->commandAttempted = false;
    if (result != NV_OK) { a->quarantined = true; return result; }
    a->commandPrepared = false;
    if (a->attached && a->command->clearMemoryDescriptor(false) != kIOReturnSuccess)
        result = NV_ERR_OPERATING_SYSTEM;
    if (result != NV_OK) { a->quarantined = true; return result; }
    a->attached = false;
    a->command->release(); a->command = nullptr;
    return result;
}
bool mapperStillValid(Platform *p) {
    OSObject *property = p->provider->copyProperty("iommu-parent");
    bool valid = false;
    if (p->mapperMode == Mapper::Device)
        valid = property && OSDynamicCast(IOMapper, property) == p->mapper;
    else if (p->mapperMode == Mapper::Direct)
        valid = !property && __atomic_load_n(&IOMapper::gSystem, __ATOMIC_ACQUIRE) == nullptr;
    if (property) property->release();
    return valid;
}
NV_STATUS mapDma(void *opaque, void *allocation, NvU32 addressBits) {
    auto *p = static_cast<Platform *>(opaque);
    auto *a = static_cast<Allocation *>(allocation);
    if (!live(p) || !a || !a->bufferPrepared || a->quarantined ||
        !mapperStillValid(p) || addressBits < 32 || addressBits > 64) return NV_ERR_NOT_SUPPORTED;
    if (a->command) return NV_ERR_STATE_IN_USE;
    const NvU64 bytes = NvU64(a->pages) * kPageBytes;
    a->command = IODMACommand::withSpecification(kIODMACommandOutputHost64,
        addressBits, kPageBytes, p->mapperMode == Mapper::Direct ?
        IODMACommand::kUnmapped : IODMACommand::kMapped, bytes, kPageBytes, p->mapper, nullptr);
    if (!a->command) return NV_ERR_NO_MEMORY;
    a->attached = a->command->setMemoryDescriptor(a->buffer, false) == kIOReturnSuccess;
    bool ok = a->attached;
    if (ok) {
        a->commandAttempted = true;
        a->commandPrepared = a->command->prepare(0, bytes, true, true) == kIOReturnSuccess;
        ok = a->commandPrepared;
    }
    UInt64 offset = 0;
    for (NvU32 i = 0; ok && i < a->pages; ++i) {
        IODMACommand::Segment64 segment{};
        UInt32 count = 1;
        const NvU64 previous = offset;
        ok = a->command->gen64IOVMSegments(&offset, &segment, &count) == kIOReturnSuccess &&
            count == 1 && segment.fLength == kPageBytes && offset == previous + kPageBytes &&
            segment.fIOVMAddr && !(segment.fIOVMAddr & (kPageBytes - 1)) &&
            segment.fIOVMAddr <= ~NvU64(0) - (kPageBytes - 1);
        if (ok) {
            // GSP RPC queues share live CPU/GPU bytes. Refuse double-buffered
            // IODMACommand mappings: prepare/complete alone cannot synchronize
            // every subsequent producer/consumer access in the original RM.
            const NvU64 mappedPhysical = p->mapperMode == Mapper::Direct ?
                segment.fIOVMAddr : p->mapper->mapToPhysicalAddress(segment.fIOVMAddr);
            ok = dmaPageMatches(a->physical[i], segment.fIOVMAddr, mappedPhysical, addressBits);
            if (ok) a->device[i] = segment.fIOVMAddr;
        }
    }
    ok = ok && offset == bytes && mapperStillValid(p);
    if (!ok) { (void)unmapDma(p, a); return NV_ERR_OPERATING_SYSTEM; }
    return NV_OK;
}
NV_STATUS releaseAllocation(void *opaque, void *allocation) {
    auto *p = static_cast<Platform *>(opaque);
    auto *a = static_cast<Allocation *>(allocation);
    if (!a) return NV_ERR_INVALID_ARGUMENT;
    if (a->quarantined) return NV_ERR_INVALID_STATE;
    NV_STATUS result = NV_OK;
    if (a->command) {
        result = unmapDma(p, a);
        if (result != NV_OK) return result;
    }
    if (a->bufferPrepared && a->buffer->complete(kIODirectionInOut) != kIOReturnSuccess)
        result = NV_ERR_OPERATING_SYSTEM;
    if (result != NV_OK) { a->quarantined = true; return result; }
    if (a->buffer) a->buffer->release();
    IOFree(a->device, a->pages * sizeof(NvU64));
    IOFree(a->physical, a->pages * sizeof(NvU64));
    p->hostBytes -= NvU64(a->pages) * kPageBytes;
    IOFree(a, sizeof(*a));
    return result;
}
void bottomHalf(thread_call_param_t parameter, thread_call_param_t) {
    auto *p = static_cast<Platform *>(parameter);
    for (;;) {
        NvU32 work = __atomic_exchange_n(&p->pending, 0, __ATOMIC_ACQ_REL);
        if (!work) break;
        if (work & 1U) {
            p->interrupt.lockedBottomHalf(p->interrupt.context);
            __atomic_add_fetch(&p->statistics.lockedBottomHalves, 1, __ATOMIC_RELAXED);
        }
        if (work & 2U) {
            p->interrupt.unlockedBottomHalf(p->interrupt.context);
            __atomic_add_fetch(&p->statistics.unlockedBottomHalves, 1, __ATOMIC_RELAXED);
        }
    }
}
void interrupt(OSObject *, void *opaque, IOService *, int) {
    auto *p = static_cast<Platform *>(opaque);
    __atomic_add_fetch(&p->callbacks, 1, __ATOMIC_ACQ_REL);
    __atomic_add_fetch(&p->statistics.controllerCallbacks, 1, __ATOMIC_RELAXED);
    if (__atomic_load_n(&p->accepting, __ATOMIC_ACQUIRE)) {
        IOInterruptState state = IOSimpleLockLockDisableInterrupt(p->isrLock);
        bool locked = false, unlocked = false;
        if (p->interrupt.top(p->interrupt.context, locked, unlocked))
            __atomic_add_fetch(&p->statistics.rmHandledCallbacks, 1, __ATOMIC_RELAXED);
        const NvU32 bits = (locked ? 1U : 0U) | (unlocked ? 2U : 0U);
        if (bits) {
            __atomic_fetch_or(&p->pending, bits, __ATOMIC_RELEASE);
            thread_call_enter(p->bottomHalf);
        }
        IOSimpleLockUnlockEnableInterrupt(p->isrLock, state);
    }
    __atomic_sub_fetch(&p->callbacks, 1, __ATOMIC_ACQ_REL);
}
InterruptStatistics interruptStatistics(void *opaque) {
    auto *p = static_cast<Platform *>(opaque);
    return InterruptStatistics{
        __atomic_load_n(&p->statistics.controllerCallbacks,__ATOMIC_ACQUIRE),
        __atomic_load_n(&p->statistics.rmHandledCallbacks,__ATOMIC_ACQUIRE),
        __atomic_load_n(&p->statistics.lockedBottomHalves,__ATOMIC_ACQUIRE),
        __atomic_load_n(&p->statistics.unlockedBottomHalves,__ATOMIC_ACQUIRE)};
}

NV_STATUS installInterrupt(void *opaque, const InterruptContract &contract) {
    auto *p = static_cast<Platform *>(opaque);
    if (!live(p) || p->irqRegistered || !contract.context || !contract.top ||
        !contract.lockedBottomHalf || !contract.unlockedBottomHalf || !contract.maskHardware || !contract.readyToArm)
        return NV_ERR_NOT_SUPPORTED;
    int interruptType = 0;
    if (p->provider->getInterruptType(0,&interruptType) != kIOReturnSuccess) return NV_ERR_NOT_SUPPORTED;
    // XNU IOInterruptController and IOPCIMessagedInterruptController register
    // new vectors hard/soft disabled. Match Linux's register-before-init order;
    // a pre-pGpu hardware-mask operation would be fabricated. No enable occurs
    // until the original private RM dispatch state passes readyToArm below.
    p->isrLock = IOSimpleLockAlloc();
    p->bottomHalf = thread_call_allocate_with_options(bottomHalf, p,
        THREAD_CALL_PRIORITY_KERNEL, THREAD_CALL_OPTIONS_ONCE);
    if (!p->isrLock || !p->bottomHalf) {
        if (p->bottomHalf) thread_call_free(p->bottomHalf);
        if (p->isrLock) IOSimpleLockFree(p->isrLock);
        p->bottomHalf = nullptr; p->isrLock = nullptr;
        return NV_ERR_NO_MEMORY;
    }
    p->interrupt = contract;
    p->accepting = false;
    if (p->provider->registerInterrupt(0, p->owner, interrupt, p) != kIOReturnSuccess) {
        thread_call_free(p->bottomHalf); IOSimpleLockFree(p->isrLock);
        p->bottomHalf = nullptr; p->isrLock = nullptr;
        p->interrupt = InterruptContract{};
        return NV_ERR_OPERATING_SYSTEM;
    }
    p->irqRegistered = true;
    p->controllerAttached = true;
    return NV_OK;
}
NV_STATUS armInterrupt(void *opaque) {
    auto *p = static_cast<Platform *>(opaque);
    if (!live(p) || !p->irqRegistered || !p->interrupt.readyToArm ||
        !p->interrupt.readyToArm(p->interrupt.context)) return NV_ERR_INVALID_STATE;
    __atomic_store_n(&p->accepting, true, __ATOMIC_RELEASE);
    if (p->provider->enableInterrupt(0) != kIOReturnSuccess) {
        __atomic_store_n(&p->accepting, false, __ATOMIC_RELEASE);
        return NV_ERR_OPERATING_SYSTEM;
    }
    p->irqEnabled = true;
    return NV_OK;
}
NV_STATUS stopInterrupt(void *opaque) {
    auto *p = static_cast<Platform *>(opaque);
    if (!p->irqRegistered) return NV_OK;
    NV_STATUS status = p->interrupt.maskHardware(p->interrupt.context);
    if (status != NV_OK) return status;
    if (p->irqEnabled && p->provider->disableInterrupt(0) != kIOReturnSuccess)
        return NV_ERR_OPERATING_SYSTEM;
    p->irqEnabled = false;
    __atomic_store_n(&p->accepting, false, __ATOMIC_RELEASE);
    if (p->controllerAttached) {
        if (p->provider->unregisterInterrupt(0) != kIOReturnSuccess)
            return NV_ERR_OPERATING_SYSTEM;
        p->controllerAttached = false;
    }
    // No new controller callback may start after successful unregister. Drain
    // any accepted hard ISR before touching its thread-call/context resources.
    for (NvU32 i = 0; __atomic_load_n(&p->callbacks, __ATOMIC_ACQUIRE) && i < 100; ++i)
        IOSleep(1);
    if (__atomic_load_n(&p->callbacks, __ATOMIC_ACQUIRE)) return NV_ERR_BUSY_RETRY;
    (void)thread_call_cancel(p->bottomHalf);
    for (NvU32 i = 0; thread_call_isactive(p->bottomHalf) && i < 100; ++i) IOSleep(1);
    if (thread_call_isactive(p->bottomHalf)) return NV_ERR_BUSY_RETRY;
    // Cancellation may remove a queued bottom half. Finish pending original RM
    // work explicitly after hardware masking and hard-ISR quiescence.
    bottomHalf(p, nullptr);
    if (!thread_call_free(p->bottomHalf)) return NV_ERR_BUSY_RETRY;
    p->bottomHalf = nullptr;
    IOSimpleLockFree(p->isrLock); p->isrLock = nullptr;
    p->interrupt = InterruptContract{};
    p->irqRegistered = false;
    return NV_OK;
}
}
void S540NvidiaDeviceTransport::destroyDarwinBackend(void *opaque) {
    IOFree(opaque, sizeof(Platform));
}
NV_STATUS S540NvidiaDeviceTransport::Session::start(IOPCIDevice *provider, IOService *owner) {
    if (active() || platformOwned_) return NV_ERR_STATE_IN_USE;
    auto *platform = static_cast<Platform *>(IOMalloc(sizeof(Platform)));
    if (!platform) return NV_ERR_NO_MEMORY;
    *platform = Platform{}; platform->provider = provider; platform->owner = owner;
    Detail::Backend backend{platform, ::ordinary, ::start, ::stop, ::live,
        ::readIdentification, ::allocate, pageAddress, ::mapDma, ::unmapDma,
        releaseAllocation, ::installInterrupt, ::armInterrupt, ::stopInterrupt,
        ::registerGeometry, ::mapRegisters, ::unmapRegisters, ::configRead, ::configWrite, ::interruptStatistics};
    NV_STATUS status = start(backend);
    if (status == NV_OK) platformOwned_ = true;
    else if (!active()) IOFree(platform, sizeof(*platform));
    else platformOwned_ = true; // Failed cleanup quarantines the still-active owner.
    return status;
}
#endif
