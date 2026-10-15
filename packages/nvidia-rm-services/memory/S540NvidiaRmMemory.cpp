// SPDX-License-Identifier: MIT
#include "S540NvidiaRmMemory.hpp"

#if defined(KERNEL)
#include <IOKit/IOBufferMemoryDescriptor.h>
#include <IOKit/IOLib.h>
#include <IOKit/IOMemoryDescriptor.h>
#include <machine/machine_routines.h>
#else
#include <cstdlib>
#include <pthread.h>
#endif

// SDK: acidanthera/MacKernelSDK 3f750085caa17ec3a7880f11c11bf4f48cd6a164.
// IOBuffer/IOMemoryMap ownership checked against XNU
// f6217f891ac0bb64f3d375211650a4c1ff8ca1ea. No global mapper lookup, physical
// MMIO mapping, PCI write, device DMA or hardware command occurs here.
namespace {
using namespace S540NvidiaRmMemory;

#if defined(KERNEL)
using Buffer = IOBufferMemoryDescriptor;
using CpuMap = IOMemoryMap;
using Lock = IOLock;
#else
struct Buffer { NvU8 *bytes; NvU64 size; bool prepared; };
struct CpuMap { Buffer *buffer; NvU64 offset; NvU64 size; };
using Lock = pthread_mutex_t;
Fault nativeFault = Fault::None;
NvU32 liveResources = 0;
NvU32 illegalOperations = 0;
#endif

bool ordinaryContext()
{
#if defined(KERNEL)
    return !ml_at_interrupt_context() && ml_get_interrupts_enabled();
#else
    return nativeFault != Fault::Context;
#endif
}

Lock *lockCreate()
{
#if defined(KERNEL)
    return IOLockAlloc();
#else
    if (nativeFault == Fault::LockAllocation)
        return nullptr;
    auto *lock = static_cast<Lock *>(std::malloc(sizeof(Lock)));
    if (!lock)
        return nullptr;
    if (pthread_mutex_init(lock, nullptr) != 0) {
        std::free(lock);
        return nullptr;
    }
    ++liveResources;
    return lock;
#endif
}

void lockAcquire(Lock *lock)
{
#if defined(KERNEL)
    IOLockLock(lock);
#else
    if (pthread_mutex_lock(lock) != 0)
        ++illegalOperations;
#endif
}

void lockRelease(Lock *lock)
{
#if defined(KERNEL)
    IOLockUnlock(lock);
#else
    if (pthread_mutex_unlock(lock) != 0)
        ++illegalOperations;
#endif
}

void lockDestroy(Lock *lock)
{
#if defined(KERNEL)
    IOLockFree(lock);
#else
    if (pthread_mutex_destroy(lock) != 0)
        ++illegalOperations;
    std::free(lock);
    --liveResources;
#endif
}

Buffer *bufferAllocate(NvU64 size)
{
#if defined(KERNEL)
    return IOBufferMemoryDescriptor::withOptions(
        kIODirectionInOut | kIOMemoryMapperNone, size, kPageBytes);
#else
    if (nativeFault == Fault::BufferAllocation)
        return nullptr;
    auto *buffer = static_cast<Buffer *>(std::malloc(sizeof(Buffer)));
    if (!buffer)
        return nullptr;
    void *bytes = nullptr;
    if (posix_memalign(&bytes, kPageBytes, static_cast<size_t>(size)) != 0) {
        std::free(buffer);
        return nullptr;
    }
    buffer->bytes = static_cast<NvU8 *>(bytes);
    buffer->size = size;
    buffer->prepared = false;
    ++liveResources;
    return buffer;
#endif
}

NvU8 *bufferContents(Buffer *buffer, NvU64 size)
{
#if defined(KERNEL)
    return buffer->getLength() == size ?
        static_cast<NvU8 *>(buffer->getBytesNoCopy()) : nullptr;
#else
    return nativeFault == Fault::BufferContents || buffer->size != size ?
               nullptr : buffer->bytes;
#endif
}

bool bufferPrepare(Buffer *buffer)
{
#if defined(KERNEL)
    return buffer->prepare(kIODirectionInOut) == kIOReturnSuccess;
#else
    if (buffer->prepared) {
        ++illegalOperations;
        return false;
    }
    buffer->prepared = nativeFault != Fault::BufferPrepare;
    return buffer->prepared;
#endif
}

bool bufferComplete(Buffer *buffer)
{
#if defined(KERNEL)
    return buffer->complete(kIODirectionInOut) == kIOReturnSuccess;
#else
    if (!buffer->prepared) {
        ++illegalOperations;
        return false;
    }
    buffer->prepared = false;
    return nativeFault != Fault::BufferComplete;
#endif
}

void bufferRelease(Buffer *buffer)
{
#if defined(KERNEL)
    buffer->release();
#else
    if (buffer->prepared)
        ++illegalOperations;
    std::free(buffer->bytes);
    std::free(buffer);
    --liveResources;
#endif
}

bool bufferPhysical(Buffer *buffer, NvU32 page, NvU64 &address)
{
    const NvU64 offset = NvU64(page) * kPageBytes;
#if defined(KERNEL)
    IOByteCount length = 0;
    const NvU64 physical = buffer->getPhysicalSegment(offset, &length,
                                                     kIOMemoryMapperNone);
#else
    // Functional native stand-in only. These are process virtual addresses,
    // never presented as physical/DMA evidence in the reporter.
    NvU64 length = nativeFault == Fault::PhysicalShort ? 1 : kPageBytes;
    NvU64 physical = static_cast<NvU64>(reinterpret_cast<NvUPtr>(buffer->bytes)) + offset;
    if (nativeFault == Fault::PhysicalLookup)
        physical = 0;
    if (nativeFault == Fault::PhysicalAlignment)
        ++physical;
#endif
    if (physical == 0 || (physical & (kPageBytes - 1)) != 0 ||
        length < kPageBytes || physical > ~NvU64(0) - (kPageBytes - 1))
        return false;
    address = physical;
    return true;
}

CpuMap *mapCreate(Buffer *buffer, NvU64 offset, NvU64 size)
{
#if defined(KERNEL)
    return buffer->createMappingInTask(kernel_task, 0,
        kIOMapAnywhere | kIOMapCopybackCache, offset, size);
#else
    if (nativeFault == Fault::MappingAllocation)
        return nullptr;
    if (!buffer->prepared || size == 0 || offset > buffer->size ||
        size > buffer->size - offset) {
        ++illegalOperations;
        return nullptr;
    }
    auto *map = static_cast<CpuMap *>(std::malloc(sizeof(CpuMap)));
    if (!map)
        return nullptr;
    map->buffer = buffer;
    map->offset = offset;
    map->size = size;
    ++liveResources;
    return map;
#endif
}

void *mapAddress(CpuMap *map, NvU64 size)
{
#if defined(KERNEL)
    return map->getLength() == size ?
        reinterpret_cast<void *>(map->getVirtualAddress()) : nullptr;
#else
    return nativeFault == Fault::MappingAddress || map->size != size ?
               nullptr : map->buffer->bytes + map->offset;
#endif
}

void mapRelease(CpuMap *map)
{
#if defined(KERNEL)
    // IOMemoryMap owns a descriptor reference; its last release destroys its
    // mapping. No explicit unmap that could revoke another shared map.
    map->release();
#else
    if (!map->buffer->prepared)
        ++illegalOperations;
    std::free(map);
    --liveResources;
#endif
}

struct Allocation {
    NvUPtr token;
    Buffer *buffer;
    NvU8 *bytes;
    NvU32 pages;
    NvU32 mapCount;
    bool deferred;
};
struct Mapping {
    NvUPtr token;
    NvUPtr allocationToken;
    CpuMap *map;
    void *address;
};

Lock *registryLock = nullptr;
Allocation allocations[kMaxAllocations]{};
Mapping mappings[kMaxMappings]{};
// Tokens are opaque private ABI values, never pointers to dereference.
// They are unique across initialize/shutdown cycles and are not reused.
NvUPtr nextToken = 0x10000;
NvU32 rejected = 0;
NvU32 releaseErrors = 0;

class Guard {
    Lock *lock;
public:
    explicit Guard(Lock *value) : lock(value) { lockAcquire(lock); }
    ~Guard() { lockRelease(lock); }
    Guard(const Guard &) = delete;
    Guard &operator=(const Guard &) = delete;
};

void reject()
{
    __atomic_add_fetch(&rejected, 1U, __ATOMIC_RELAXED);
}

NvUPtr makeToken()
{
    // Restrict opaque integers to the positive canonical x86_64 range.
    if (nextToken >= (NvUPtr(1) << 47) - 1)
        return 0;
    return ++nextToken;
}

Allocation *findAllocation(void *handle)
{
    const NvUPtr token = reinterpret_cast<NvUPtr>(handle);
    if (!token)
        return nullptr;
    for (NvU32 i = 0; i < kMaxAllocations; ++i)
        if (allocations[i].token == token)
            return &allocations[i];
    return nullptr;
}

Mapping *findMapping(void *handle)
{
    const NvUPtr token = reinterpret_cast<NvUPtr>(handle);
    if (!token)
        return nullptr;
    for (NvU32 i = 0; i < kMaxMappings; ++i)
        if (mappings[i].token == token)
            return &mappings[i];
    return nullptr;
}

NV_STATUS destroyAllocation(Allocation &allocation)
{
    const bool complete = bufferComplete(allocation.buffer);
    bufferRelease(allocation.buffer);
    allocation = {};
    if (!complete) {
        __atomic_add_fetch(&releaseErrors, 1U, __ATOMIC_RELAXED);
        return NV_ERR_GENERIC;
    }
    return NV_OK;
}

void clearAllocationOutputs(NvU32 pages, NvBool contiguous,
                            NvU64 *ptes, void **privateData)
{
    if (privateData)
        *privateData = nullptr;
    // The upstream caller supplies one PTE for contiguous allocations, or
    // page_count PTEs otherwise. Never trust an unsupported count as a loop
    // bound; clear only the selected profile's bounded output prefix.
    const NvU32 count = contiguous ? (pages ? 1 : 0) :
                              (pages < kMaxPages ? pages : kMaxPages);
    if (ptes)
        for (NvU32 i = 0; i < count; ++i)
            ptes[i] = 0;
}

} // namespace

bool S540NvidiaRmMemory::initialize()
{
    if (!ordinaryContext())
        return false;
    if (registryLock)
        return true;
    registryLock = lockCreate();
    if (!registryLock)
        return false;
    __atomic_store_n(&rejected, 0U, __ATOMIC_RELAXED);
    __atomic_store_n(&releaseErrors, 0U, __ATOMIC_RELAXED);
    return true;
}

bool S540NvidiaRmMemory::shutdown()
{
    if (!ordinaryContext())
        return false;
    if (!registryLock)
        return true;
    {
        Guard guard(registryLock);
        for (NvU32 i = 0; i < kMaxAllocations; ++i)
            if (allocations[i].token)
                return false;
        for (NvU32 i = 0; i < kMaxMappings; ++i)
            if (mappings[i].token)
                return false;
    }
    Lock *lock = registryLock;
    registryLock = nullptr;
    lockDestroy(lock);
    return true;
}

bool S540NvidiaRmMemory::ready() { return registryLock != nullptr; }

S540NvidiaRmMemory::Statistics S540NvidiaRmMemory::statistics()
{
    Statistics result{};
    result.rejected = __atomic_load_n(&rejected, __ATOMIC_RELAXED);
    result.releaseErrors = __atomic_load_n(&releaseErrors, __ATOMIC_RELAXED);
    if (!ordinaryContext() || !registryLock)
        return result;
    Guard guard(registryLock);
    for (NvU32 i = 0; i < kMaxAllocations; ++i) {
        if (allocations[i].token) {
            ++result.allocations;
            result.bytes += NvU64(allocations[i].pages) * kPageBytes;
            if (allocations[i].deferred)
                ++result.deferred;
        }
    }
    for (NvU32 i = 0; i < kMaxMappings; ++i)
        if (mappings[i].token)
            ++result.mappings;
    return result;
}

extern "C" NV_STATUS NV_API_CALL nv_alloc_pages(
    nv_state_t *state, NvU32 pageCount, NvU64 pageSize, NvBool contiguous,
    NvU32 cacheType, NvBool zeroed, NvBool unencrypted, NvS32 node,
    NvU64 *ptes, void **privateData)
{
    clearAllocationOutputs(pageCount, contiguous, ptes, privateData);
    if (!ptes || !privateData || pageCount == 0 || pageSize == 0 ||
        contiguous > 1 || zeroed > 1 || unencrypted > 1)
        return NV_ERR_INVALID_ARGUMENT;
    if (!ordinaryContext())
        return NV_ERR_INVALID_REQUEST;
    if (state || pageCount > kMaxPages || pageSize != kPageBytes ||
        contiguous || cacheType != S540_NV_MEMORY_CACHED ||
        unencrypted || node != -1)
        return NV_ERR_NOT_SUPPORTED;
    if (!registryLock)
        return NV_ERR_INVALID_STATE;
    Guard guard(registryLock);
    Allocation *slot = nullptr;
    for (NvU32 i = 0; i < kMaxAllocations; ++i)
        if (!allocations[i].token) {
            slot = &allocations[i];
            break;
        }
    if (!slot)
        return NV_ERR_NO_MEMORY;
    const NvUPtr token = makeToken();
    if (!token)
        return NV_ERR_INVALID_LIMIT;
    const NvU64 size = NvU64(pageCount) * kPageBytes;
    Buffer *buffer = bufferAllocate(size);
    if (!buffer)
        return NV_ERR_NO_MEMORY;
    NvU8 *bytes = bufferContents(buffer, size);
    if (!bytes || !bufferPrepare(buffer)) {
        bufferRelease(buffer);
        return bytes ? NV_ERR_GENERIC : NV_ERR_NO_MEMORY;
    }
    NvU64 physical[kMaxPages]{};
    bool physicalValid = true;
    for (NvU32 i = 0; i < pageCount; ++i)
        if (!bufferPhysical(buffer, i, physical[i])) {
            physicalValid = false;
            break;
        }
    if (!physicalValid) {
        if (!bufferComplete(buffer))
            __atomic_add_fetch(&releaseErrors, 1U, __ATOMIC_RELAXED);
        bufferRelease(buffer);
        return NV_ERR_GENERIC;
    }
    if (zeroed)
        for (NvU64 i = 0; i < size; ++i)
            bytes[i] = 0;
    *slot = {token, buffer, bytes, pageCount, 0, false};
    for (NvU32 i = 0; i < pageCount; ++i)
        ptes[i] = physical[i];
    *privateData = reinterpret_cast<void *>(token);
    return NV_OK;
}

extern "C" NV_STATUS NV_API_CALL nv_free_pages(
    nv_state_t *state, NvU32 pageCount, NvBool contiguous,
    NvU32 cacheType, void *privateData)
{
    if (!ordinaryContext())
        return NV_ERR_INVALID_REQUEST;
    if (state || contiguous || cacheType != S540_NV_MEMORY_CACHED)
        return NV_ERR_NOT_SUPPORTED;
    if (!registryLock)
        return NV_ERR_INVALID_STATE;
    Guard guard(registryLock);
    Allocation *allocation = findAllocation(privateData);
    if (!allocation || allocation->pages != pageCount)
        return NV_ERR_INVALID_ARGUMENT;
    if (allocation->deferred)
        return NV_ERR_INVALID_STATE;
    if (allocation->mapCount) {
        allocation->deferred = true;
        return NV_OK;
    }
    return destroyAllocation(*allocation);
}

extern "C" void * NV_API_CALL nv_alloc_kernel_mapping(
    nv_state_t *state, void *privateData, NvU64 pageIndex,
    NvU32 pageOffset, NvU64 size, void **mapPrivate)
{
    if (mapPrivate)
        *mapPrivate = nullptr;
    if (!mapPrivate || state || !ordinaryContext() || !registryLock ||
        size == 0 || pageOffset >= kPageBytes)
        return nullptr;
    Guard guard(registryLock);
    Allocation *allocation = findAllocation(privateData);
    if (!allocation || allocation->deferred || pageIndex >= allocation->pages)
        return nullptr;
    const NvU64 offset = pageIndex * kPageBytes + pageOffset;
    const NvU64 bytes = NvU64(allocation->pages) * kPageBytes;
    if (size > bytes - offset)
        return nullptr;
    Mapping *slot = nullptr;
    for (NvU32 i = 0; i < kMaxMappings; ++i)
        if (!mappings[i].token) {
            slot = &mappings[i];
            break;
        }
    if (!slot)
        return nullptr;
    const NvUPtr token = makeToken();
    if (!token)
        return nullptr;
    CpuMap *map = mapCreate(allocation->buffer, offset, size);
    if (!map)
        return nullptr;
    void *address = mapAddress(map, size);
    if (!address) {
        mapRelease(map);
        return nullptr;
    }
    *slot = {token, allocation->token, map, address};
    ++allocation->mapCount;
    *mapPrivate = reinterpret_cast<void *>(token);
    return address;
}

extern "C" void NV_API_CALL nv_free_kernel_mapping(
    nv_state_t *state, void *privateData, void *address, void *mapPrivate)
{
    if (state || !ordinaryContext() || !registryLock) {
        reject();
        return;
    }
    Guard guard(registryLock);
    Allocation *allocation = findAllocation(privateData);
    Mapping *mapping = findMapping(mapPrivate);
    if (!allocation || !mapping || mapping->allocationToken != allocation->token ||
        mapping->address != address || allocation->mapCount == 0) {
        reject();
        return;
    }
    mapRelease(mapping->map);
    *mapping = {};
    --allocation->mapCount;
    if (allocation->deferred && allocation->mapCount == 0)
        destroyAllocation(*allocation);
}

extern "C" NV_STATUS NV_API_CALL nv_dma_map_alloc(
    nv_dma_device_t *, NvU64, NvU64 *, NvBool, NvBool, void **)
{
    return NV_ERR_NOT_SUPPORTED;
}

extern "C" NV_STATUS NV_API_CALL nv_dma_unmap_alloc(
    nv_dma_device_t *, NvU64, NvU64 *, void **)
{
    return NV_ERR_NOT_SUPPORTED;
}

namespace {
void recordCheck(S540NvidiaRmMemory::Result &result, bool &component,
                 bool condition)
{
    ++result.checks;
    if (!condition) {
        ++result.failures;
        component = false;
    }
}
}

S540NvidiaRmMemory::Result S540NvidiaRmMemory::check()
{
    Result result{0, 0, true, true, true, true, true};
    // This checkpoint owns its lifecycle. Never consume another RM owner's
    // registry or shut it down as a side effect of a failed startup test.
    recordCheck(result, result.cleanup, !ready());
    if (ready())
        return result;
    recordCheck(result, result.allocation, initialize());
    if (!ready())
        return result;
    recordCheck(result, result.allocation, initialize());
    NvU64 ptes[kMaxPages + 2]{};
    ptes[0] = 0x1234;
    ptes[kMaxPages + 1] = 0x5678;
    void *allocation = nullptr;
    const NV_STATUS allocated = nv_alloc_pages(nullptr, 4, kPageBytes,
        NV_FALSE, S540_NV_MEMORY_CACHED, NV_TRUE, NV_FALSE, -1,
        ptes + 1, &allocation);
    recordCheck(result, result.allocation, allocated == NV_OK && allocation);
    recordCheck(result, result.bounds,
                ptes[0] == 0x1234 && ptes[kMaxPages + 1] == 0x5678);
    if (allocated != NV_OK || !allocation) {
        recordCheck(result, result.cleanup, statistics().allocations == 0);
        recordCheck(result, result.cleanup, shutdown());
        return result;
    }
    bool physical = true;
    for (NvU32 i = 1; i <= 4; ++i)
        physical = physical && ptes[i] != 0 &&
                   (ptes[i] & (kPageBytes - 1)) == 0;
    recordCheck(result, result.allocation, physical);
    recordCheck(result, result.allocation,
                statistics().allocations == 1 && statistics().bytes == 4 * kPageBytes);
    recordCheck(result, result.cleanup, !shutdown() && ready());

    void *shortPrivate = nullptr;
    auto *shortMap = static_cast<NvU8 *>(nv_alloc_kernel_mapping(nullptr,
        allocation, 0, kPageBytes - 3, 16, &shortPrivate));
    recordCheck(result, result.mappings, shortMap && shortPrivate);
    if (shortMap) {
        bool zero = true;
        for (NvU32 i = 0; i < 16; ++i)
            zero = zero && shortMap[i] == 0;
        recordCheck(result, result.allocation, zero);
        for (NvU32 i = 0; i < 16; ++i)
            shortMap[i] = static_cast<NvU8>(0x80 + i);
    }
    void *fullPrivate = nullptr;
    auto *fullMap = static_cast<NvU8 *>(nv_alloc_kernel_mapping(nullptr,
        allocation, 0, 0, 4 * kPageBytes, &fullPrivate));
    recordCheck(result, result.mappings, fullMap && fullPrivate);
    if (fullMap && shortMap) {
        bool alias = true;
        for (NvU32 i = 0; i < 16; ++i)
            alias = alias && fullMap[kPageBytes - 3 + i] == NvU8(0x80 + i);
        recordCheck(result, result.mappings, alias);
    }
    void *invalidPrivate = reinterpret_cast<void *>(1);
    recordCheck(result, result.bounds,
        nv_alloc_kernel_mapping(nullptr, allocation, ~NvU64(0), 0, 1,
                                &invalidPrivate) == nullptr && !invalidPrivate);
    invalidPrivate = reinterpret_cast<void *>(1);
    recordCheck(result, result.bounds,
        nv_alloc_kernel_mapping(nullptr, allocation, 3, kPageBytes - 1, 2,
                                &invalidPrivate) == nullptr && !invalidPrivate);
    recordCheck(result, result.bounds,
        nv_free_pages(nullptr, 3, NV_FALSE, S540_NV_MEMORY_CACHED,
                      allocation) == NV_ERR_INVALID_ARGUMENT);
    if (shortMap && fullMap) {
        const NvU32 rejectedBefore = statistics().rejected;
        nv_free_kernel_mapping(nullptr, allocation, shortMap, fullPrivate);
        recordCheck(result, result.bounds,
                    statistics().rejected == rejectedBefore + 1 &&
                    statistics().mappings == 2);
    }

    // The selected DMA profile is deliberately unavailable. Error returns
    // preserve allocation ownership and physical PTE IN/OUT inputs.
    void *dmaPrivate = allocation;
    const NvU64 firstPhysical = ptes[1];
    recordCheck(result, result.bounds,
        nv_dma_map_alloc(nullptr, 4, ptes + 1, NV_FALSE, NV_FALSE,
                         &dmaPrivate) == NV_ERR_NOT_SUPPORTED &&
        dmaPrivate == allocation && ptes[1] == firstPhysical);

    recordCheck(result, result.deferredFree,
        nv_free_pages(nullptr, 4, NV_FALSE, S540_NV_MEMORY_CACHED,
                      allocation) == NV_OK);
    const Statistics deferred = statistics();
    const NvU32 expectedMaps = (shortMap ? 1U : 0U) + (fullMap ? 1U : 0U);
    recordCheck(result, result.deferredFree,
                deferred.mappings == expectedMaps &&
                deferred.deferred == (expectedMaps ? 1U : 0U));
    invalidPrivate = reinterpret_cast<void *>(1);
    recordCheck(result, result.bounds,
        nv_alloc_kernel_mapping(nullptr, allocation, 0, 0, 1,
                                &invalidPrivate) == nullptr && !invalidPrivate);
    recordCheck(result, result.bounds,
        nv_free_pages(nullptr, 4, NV_FALSE, S540_NV_MEMORY_CACHED, allocation) != NV_OK);
    if (shortMap)
        nv_free_kernel_mapping(nullptr, allocation, shortMap, shortPrivate);
    if (fullMap) {
        bool preserved = true;
        if (shortMap)
            for (NvU32 i = 0; i < 16; ++i)
                preserved = preserved && fullMap[kPageBytes - 3 + i] == NvU8(0x80 + i);
        recordCheck(result, result.deferredFree, preserved);
        nv_free_kernel_mapping(nullptr, allocation, fullMap, fullPrivate);
    }
    const Statistics final = statistics();
    recordCheck(result, result.cleanup, final.allocations == 0 &&
                final.mappings == 0 && final.deferred == 0 && final.bytes == 0 &&
                final.releaseErrors == 0);
    recordCheck(result, result.cleanup, shutdown() && !ready());
    return result;
}

#if !defined(KERNEL)
void S540NvidiaRmMemory::setNativeFault(Fault fault) { nativeFault = fault; }
NvU32 S540NvidiaRmMemory::nativeLiveResources() { return liveResources; }
NvU32 S540NvidiaRmMemory::nativeIllegalOperations() { return illegalOperations; }
#endif
