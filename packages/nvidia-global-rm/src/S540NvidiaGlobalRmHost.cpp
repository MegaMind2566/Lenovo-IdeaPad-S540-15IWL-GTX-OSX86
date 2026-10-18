// SPDX-License-Identifier: MIT
#include "S540NvidiaGlobalRm.h"
#include "../../nvidia-darwin-services/src/S540NvidiaDarwinServices.h"

#ifdef KERNEL
#include <IOKit/IOLib.h>
#else
#include <cstdlib>
#include <mutex>
#include <new>
#endif

namespace {
// The global manager's original GpuDb allocation alone is 24,604,904 bytes.
// These declared ceilings cover global construction and adapter-owned host
// buffers without recycling the small standalone RS reserve.
constexpr NvU32 kCapacity = 8192;
constexpr NvU64 kSingleLimit = 256ULL * 1024 * 1024;
constexpr NvU64 kTotalLimit = 512ULL * 1024 * 1024;
struct Allocation { void *pointer; NvU64 bytes; bool original; };
Allocation records[kCapacity] = {};
S540NvidiaGlobalRmPlatformFacts platformFacts = {};
S540NvidiaGlobalRmHostSnapshot counters = {};
NvU64 serviceMask = 0;
struct ServiceUse { const char *name; NvU64 calls; };
ServiceUse serviceUses[512] = {};
#if !defined(KERNEL)
NvU64 allocationOrdinal = 0;
NvU64 failureOrdinal = 0;
#endif
#ifdef KERNEL
IOLock *guard = nullptr;
void lock() { IOLockLock(guard); }
void unlock() { IOLockUnlock(guard); }
void *allocate(NvU64 n) { return IOMalloc(static_cast<vm_size_t>(n)); }
void release(void *p, NvU64 n) { IOFree(p, static_cast<vm_size_t>(n)); }
#else
std::mutex *guard = nullptr;
void lock() { guard->lock(); }
void unlock() { guard->unlock(); }
void *allocate(NvU64 n) { return std::malloc(static_cast<size_t>(n)); }
void release(void *p, NvU64) { std::free(p); }
#endif
}

extern "C" NV_STATUS s540GlobalRmHostInitialize(const S540NvidiaGlobalRmPlatformFacts *facts)
{
    if (!s540Darwin_os_semaphore_may_sleep()) return NV_ERR_INVALID_STATE;
    if (!facts || facts->format != 1 || facts->known != S540_GLOBAL_FACT_ALL ||
        !facts->cpuCount || !facts->cpuFrequencyHz || !facts->osMajor ||
        !facts->osVersion || !facts->osDate)
        return NV_ERR_NOT_SUPPORTED;
    if (guard || counters.initialized || counters.liveAllocations)
        return NV_ERR_STATE_IN_USE;
#ifdef KERNEL
    guard = IOLockAlloc();
#else
    guard = new (std::nothrow) std::mutex;
#endif
    if (!guard) return NV_ERR_NO_MEMORY;
    const NvU32 unavailable = counters.unavailableCalls;
    const NvU32 invalidFrees = counters.invalidFrees;
    counters = {};
    counters.unavailableCalls = unavailable;
    counters.invalidFrees = invalidFrees;
    serviceMask = 0;
#if !defined(KERNEL)
    allocationOrdinal = 0;
#endif
    platformFacts = *facts;
    counters.initialized = NV_TRUE;
    return NV_OK;
}

extern "C" NvBool s540GlobalRmHostShutdown(void)
{
    if (!s540Darwin_os_semaphore_may_sleep()) {
        s540GlobalRmRecordUnavailable(0);
        return NV_FALSE;
    }
    if (!guard) return counters.initialized ? NV_FALSE : NV_TRUE;
    lock();
    const bool cold = counters.liveAllocations == 0 && counters.liveBytes == 0;
    if (cold) counters.initialized = NV_FALSE;
    unlock();
    if (!cold) return NV_FALSE;
#ifdef KERNEL
    IOLockFree(guard);
#else
    delete guard;
#endif
    guard = nullptr;
    platformFacts = {};
    return NV_TRUE;
}

static void *allocateTracked(NvU64 bytes, bool original)
{
    if (!s540Darwin_os_semaphore_may_sleep()) {
        s540GlobalRmRecordUnavailable(0);
        return nullptr;
    }
    if (!guard || !bytes || bytes > kSingleLimit || bytes > static_cast<NvU64>(~static_cast<size_t>(0)))
        return nullptr;
    lock();
#if !defined(KERNEL)
    if (++allocationOrdinal == failureOrdinal) {
        failureOrdinal = 0;
        ++counters.allocationFailures;
        unlock();
        return nullptr;
    }
#endif
    NvU32 slot = 0;
    while (slot != kCapacity && records[slot].pointer) ++slot;
    if (!counters.initialized || slot == kCapacity || bytes > kTotalLimit - counters.liveBytes) {
        ++counters.allocationFailures;
        unlock();
        return nullptr;
    }
    // Reserve ownership before sleeping in IOMalloc. Other callers cannot use
    // this slot and the total byte ceiling includes in-progress allocations.
    records[slot] = {reinterpret_cast<void *>(static_cast<NvUPtr>(1)), bytes, original};
    counters.liveBytes += bytes;
    ++counters.liveAllocations;
    if (original) {
        counters.originalLiveBytes += bytes;
        ++counters.originalLiveAllocations;
    }
    unlock();
    void *pointer = allocate(bytes);
    lock();
    if (!pointer) {
        records[slot] = {};
        counters.liveBytes -= bytes;
        --counters.liveAllocations;
        if (original) {
            counters.originalLiveBytes -= bytes;
            --counters.originalLiveAllocations;
        }
        ++counters.allocationFailures;
    } else {
        records[slot].pointer = pointer;
        ++counters.allocations;
        if (counters.liveBytes > counters.peakBytes) counters.peakBytes = counters.liveBytes;
        if (counters.liveAllocations > counters.peakAllocations) counters.peakAllocations = counters.liveAllocations;
        if (bytes > counters.largestAllocation) counters.largestAllocation = bytes;
    }
    unlock();
    return pointer;
}

static void freeTracked(void *pointer, bool original)
{
    if (!pointer) return;
    if (!s540Darwin_os_semaphore_may_sleep()) {
        // Keep ownership recorded so ordinary-thread teardown can release it.
        s540GlobalRmRecordUnavailable(0);
        return;
    }
    if (!guard) { ++counters.invalidFrees; return; }
    lock();
    NvU32 slot = 0;
    while (slot != kCapacity && records[slot].pointer != pointer) ++slot;
    if (slot == kCapacity || pointer == reinterpret_cast<void *>(static_cast<NvUPtr>(1)) ||
        records[slot].original != original) {
        ++counters.invalidFrees;
        unlock();
        return;
    }
    const NvU64 bytes = records[slot].bytes;
    // Retain the reservation while IOFree runs, so host shutdown cannot race a
    // pending release. Duplicate free finds no matching published pointer.
    records[slot].pointer = reinterpret_cast<void *>(static_cast<NvUPtr>(1));
    unlock();
    release(pointer, bytes);
    lock();
    records[slot] = {};
    counters.liveBytes -= bytes;
    --counters.liveAllocations;
    if (original) {
        counters.originalLiveBytes -= bytes;
        --counters.originalLiveAllocations;
    }
    ++counters.frees;
    unlock();
}

extern "C" void *s540GlobalRmHostAllocate(NvU64 bytes) { return allocateTracked(bytes, false); }
extern "C" void s540GlobalRmHostFree(void *pointer) { freeTracked(pointer, false); }
extern "C" void *s540GlobalRmHostAllocateOriginal(NvU64 bytes) { return allocateTracked(bytes, true); }
extern "C" void s540GlobalRmHostFreeOriginal(void *pointer) { freeTracked(pointer, true); }

extern "C" void s540GlobalRmHostSnapshot(S540NvidiaGlobalRmHostSnapshot *out)
{
    if (!out) return;
    if (!s540Darwin_os_semaphore_may_sleep()) {
        s540GlobalRmRecordUnavailable(0);
        *out = {};
        out->unavailableCalls = __atomic_load_n(&counters.unavailableCalls, __ATOMIC_ACQUIRE);
        return;
    }
    if (guard) lock();
    out->liveBytes = counters.liveBytes;
    out->peakBytes = counters.peakBytes;
    out->largestAllocation = counters.largestAllocation;
    out->allocations = counters.allocations;
    out->frees = counters.frees;
    out->liveAllocations = counters.liveAllocations;
    out->peakAllocations = counters.peakAllocations;
    out->allocationFailures = counters.allocationFailures;
    out->invalidFrees = counters.invalidFrees;
    out->unavailableCalls = __atomic_load_n(&counters.unavailableCalls, __ATOMIC_ACQUIRE);
    out->initialized = counters.initialized;
    out->originalLiveBytes = counters.originalLiveBytes;
    out->originalLiveAllocations = counters.originalLiveAllocations;
    out->externalLiveBytes = counters.liveBytes - counters.originalLiveBytes;
    out->externalLiveAllocations = counters.liveAllocations - counters.originalLiveAllocations;
    if (guard) unlock();
}

extern "C" void s540GlobalRmRecordUnavailable(NvU32)
{
    NvU32 current = __atomic_load_n(&counters.unavailableCalls, __ATOMIC_RELAXED);
    while (current != ~0U &&
           !__atomic_compare_exchange_n(&counters.unavailableCalls, &current,
                                         current + 1U, false,
                                         __ATOMIC_RELAXED, __ATOMIC_RELAXED)) {}
}

extern "C" void s540GlobalRmRecordService(NvU32 service)
{
    if (service >= 64) { s540GlobalRmRecordUnavailable(service); return; }
    __atomic_fetch_or(&serviceMask, 1ULL << service, __ATOMIC_RELAXED);
}

extern "C" NvU64 s540GlobalRmServiceMask(void)
{
    return __atomic_load_n(&serviceMask, __ATOMIC_ACQUIRE);
}

extern "C" void s540GlobalRmRecordServiceName(const char *name)
{
    // Only static __func__ strings are accepted by this internal instrumentation
    // contract. All entries remain valid until the kext image unloads. The
    // observer is lock-free, allocation-free and safe while IRQs are disabled.
    if (!name) { s540GlobalRmRecordUnavailable(0); return; }
    NvU32 hash = 2166136261U;
    for (const char *s = name; *s; ++s) hash = (hash ^ static_cast<NvU8>(*s)) * 16777619U;
    for (NvU32 probe = 0; probe != 512; ++probe) {
        ServiceUse &entry = serviceUses[(hash + probe) & 511U];
        const char *current = __atomic_load_n(&entry.name, __ATOMIC_ACQUIRE);
        if (!current) {
            const char *empty = nullptr;
            if (__atomic_compare_exchange_n(&entry.name, &empty, name, false,
                                             __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE))
                current = name;
            else current = empty;
        }
        const char *a = current;
        const char *b = name;
        while (*a && *a == *b) { ++a; ++b; }
        if (!*a && !*b) {
            __atomic_fetch_add(&entry.calls, 1ULL, __ATOMIC_RELAXED);
            return;
        }
    }
    s540GlobalRmRecordUnavailable(0);
}

extern "C" NvU32 s540GlobalRmObservedServices(void)
{
    NvU32 count = 0;
    for (NvU32 slot = 0; slot != 512; ++slot)
        count += __atomic_load_n(&serviceUses[slot].name, __ATOMIC_ACQUIRE) != nullptr;
    return count;
}

extern "C" const char *s540GlobalRmServiceName(NvU32 slot)
{
    return slot < 512 ? __atomic_load_n(&serviceUses[slot].name, __ATOMIC_ACQUIRE) : nullptr;
}

extern "C" NvU64 s540GlobalRmServiceCalls(NvU32 slot)
{
    return slot < 512 ? __atomic_load_n(&serviceUses[slot].calls, __ATOMIC_ACQUIRE) : 0;
}

extern "C" const S540NvidiaGlobalRmPlatformFacts *s540GlobalRmPlatformFacts(void)
{
    return counters.initialized ? &platformFacts : nullptr;
}

#if !defined(KERNEL)
void S540NvidiaGlobalRmNative::failAllocationAt(NvU64 ordinal)
{
    failureOrdinal = ordinal;
}
#endif
