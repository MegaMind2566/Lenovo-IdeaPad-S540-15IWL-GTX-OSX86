// SPDX-License-Identifier: MIT
#include "S540NvidiaLifecycleRuntime.hpp"
#include "../../nvidia-caller-integration/src/S540NvidiaReserve.hpp"
#include "../../nvidia-caller-integration/src/S540NvidiaMutex.hpp"
#include "S540NvidiaSpinlock.hpp"
#include "../upstream/nvport_lifecycle.h"

namespace {

using S540NvidiaLifecycleRuntime::Result;

void check(Result &result, bool &component, bool condition)
{
    ++result.checks;
    if (!condition) {
        ++result.failures;
        component = false;
    }
}

bool activeCount(PORT_MEM_ALLOCATOR *allocator, NvU32 count)
{
    PORT_MEM_TRACK_ALLOCATOR_STATS stats{};
    return portMemExTrackingGetActiveStats(allocator, &stats) == NV_OK &&
        stats.numAllocations == count && stats.allocatedSize == 0 &&
        stats.usefulSize == 0 && stats.metaSize == 0;
}

void globalAllocations(Result &result)
{
    PORT_MEM_TRACK_ALLOCATOR_STATS before{};
    const bool baseline =
        portMemExTrackingGetActiveStats(nullptr, &before) == NV_OK;
    check(result, result.trackedAllocation, baseline);
    void *paged = portMemAllocPaged(32);
    void *nonPaged = portMemAllocNonPaged(96);
    check(result, result.trackedAllocation, paged != nullptr && nonPaged != nullptr);
    if (paged != nullptr && nonPaged != nullptr) {
        auto *left = static_cast<NvU8 *>(paged);
        auto *right = static_cast<NvU8 *>(nonPaged);
        left[0] = 0x3c;
        left[31] = 0xa5;
        right[0] = 0x71;
        right[95] = 0xb6;
        check(result, result.trackedAllocation, paged != nonPaged &&
              left[0] == 0x3c && left[31] == 0xa5 &&
              right[0] == 0x71 && right[95] == 0xb6);
        check(result, result.trackedAllocation,
              baseline && activeCount(nullptr, before.numAllocations + 2));
    }
    portMemFree(paged);
    if (nonPaged != paged)
        portMemFree(nonPaged);
    portMemFree(nullptr);
    check(result, result.cleanup,
          baseline && activeCount(nullptr, before.numAllocations));

    void *zeroPaged = portMemAllocPaged(0);
    void *zeroNonPaged = portMemAllocNonPaged(0);
    check(result, result.trackedAllocation,
          zeroPaged == nullptr && zeroNonPaged == nullptr);
    portMemFree(zeroPaged);
    if (zeroNonPaged != zeroPaged)
        portMemFree(zeroNonPaged);

    void *oversize = portMemAllocNonPaged(S540NvidiaReserve::kSlotBytes + 1);
    void *maximum = portMemAllocPaged(~NvLength{0});
    check(result, result.trackedAllocation,
          oversize == nullptr && maximum == nullptr);
    portMemFree(oversize);
    if (maximum != oversize)
        portMemFree(maximum);

    NvLength sum = 0;
    check(result, result.trackedAllocation,
          !portSafeAddLength(~NvLength{0}, 1, &sum));
    check(result, result.trackedAllocation,
          portSafeAddLength(~NvLength{0} - 1, 1, &sum) && sum == ~NvLength{0});
    check(result, result.cleanup,
          baseline && activeCount(nullptr, before.numAllocations));
}

void ownedMutex(Result &result, PORT_MEM_ALLOCATOR *allocator)
{
    PORT_MEM_TRACK_ALLOCATOR_STATS before{};
    const bool baseline =
        portMemExTrackingGetActiveStats(allocator, &before) == NV_OK;
    PORT_MUTEX *mutex = portSyncMutexCreate(allocator);
    check(result, result.ownedMutex, mutex != nullptr);
    if (mutex == nullptr)
        return;
    check(result, result.ownedMutex,
          mutex->pAllocator == allocator && mutex->mutex != nullptr);
    check(result, result.trackedAllocation,
          baseline && activeCount(allocator, before.numAllocations + 1));
    const NvBool acquired = portSyncMutexAcquireConditional(mutex);
    check(result, result.ownedMutex, acquired == NV_TRUE);
    if (acquired == NV_TRUE) {
        check(result, result.ownedMutex,
              portSyncMutexAcquireConditional(mutex) == NV_FALSE);
        portSyncMutexRelease(mutex);
        // The same thread released the only token. No worker exists here.
        portSyncMutexAcquire(mutex);
        check(result, result.ownedMutex,
              portSyncMutexAcquireConditional(mutex) == NV_FALSE);
        portSyncMutexRelease(mutex);
    }
    // On an unavailable newly created token, every hook has returned and the
    // object has no external owner or waiter: this is quiescent abort cleanup.
    portSyncMutexDestroy(mutex);
    check(result, result.cleanup,
          baseline && activeCount(allocator, before.numAllocations));
}

void ownedSpinlock(Result &result, PORT_MEM_ALLOCATOR *allocator)
{
    PORT_MEM_TRACK_ALLOCATOR_STATS before{};
    const bool baseline =
        portMemExTrackingGetActiveStats(allocator, &before) == NV_OK;
    PORT_SPINLOCK *spinlock = portSyncSpinlockCreate(allocator);
    check(result, result.spinlocks, spinlock != nullptr);
    if (spinlock == nullptr)
        return;
    check(result, result.spinlocks,
          spinlock->pAllocator == allocator && spinlock->lock != nullptr);
    check(result, result.trackedAllocation,
          baseline && activeCount(allocator, before.numAllocations + 1));
    portSyncSpinlockAcquire(spinlock);
    // The context hook only queries interrupt state. It never allocates,
    // sleeps or prints while the short uncontended lock is held.
    const bool interruptsMasked = s540NvportLifecycleContextAllowed() == NV_FALSE;
    portSyncSpinlockRelease(spinlock);
    check(result, result.spinlocks, interruptsMasked &&
          s540NvportLifecycleContextAllowed() == NV_TRUE);
    portSyncSpinlockDestroy(spinlock);
    check(result, result.cleanup,
          baseline && activeCount(allocator, before.numAllocations));
}

void customAllocations(Result &result, PORT_MEM_ALLOCATOR *allocator,
                       NvLength length)
{
    PORT_MEM_TRACK_ALLOCATOR_STATS before{};
    const bool totalBaseline =
        portMemExTrackingGetTotalStats(allocator, &before) == NV_OK;
    check(result, result.trackedAllocation,
          activeCount(allocator, 0) && totalBaseline);
    void *allocation = PORT_ALLOC(allocator, length);
    check(result, result.trackedAllocation, allocation != nullptr);
    if (allocation != nullptr) {
        auto *bytes = static_cast<NvU8 *>(allocation);
        bytes[0] = 0x19;
        bytes[length - 1] = 0xe7;
        check(result, result.trackedAllocation,
              bytes[0] == 0x19 && bytes[length - 1] == 0xe7 &&
              activeCount(allocator, 1));
        PORT_MEM_TRACK_ALLOCATOR_STATS total{};
        check(result, result.trackedAllocation,
              portMemExTrackingGetTotalStats(allocator, &total) == NV_OK &&
              totalBaseline && total.numAllocations == before.numAllocations + 1 &&
              total.usefulSize == before.usefulSize + length);
    }
    PORT_FREE(allocator, allocation);
    check(result, result.cleanup, activeCount(allocator, 0));
    ownedMutex(result, allocator);
    ownedSpinlock(result, allocator);
}

void boundedExhaustion(Result &result, PORT_MEM_ALLOCATOR *allocator)
{
    using namespace S540NvidiaReserve;
    const NvU32 before = liveSlots();
    void *allocations[kSlotCount] = {};
    NvU32 count = 0;
    for (; count < kSlotCount; ++count) {
        allocations[count] = PORT_ALLOC(allocator, 64 + count);
        if (allocations[count] == nullptr)
            break;
    }
    check(result, result.trackedAllocation,
          before < kSlotCount && count == kSlotCount - before &&
          liveSlots() == kSlotCount);
    check(result, result.trackedAllocation, activeCount(allocator, count));
    void *extra = PORT_ALLOC(allocator, 1);
    check(result, result.trackedAllocation, extra == nullptr);
    PORT_FREE(allocator, extra);
    for (void *allocation : allocations)
        PORT_FREE(allocator, allocation);
    check(result, result.cleanup,
          liveSlots() == before && activeCount(allocator, 0));
    void *reused = PORT_ALLOC(allocator, kSlotBytes);
    check(result, result.trackedAllocation, reused != nullptr);
    PORT_FREE(allocator, reused);
    check(result, result.cleanup,
          liveSlots() == before && activeCount(allocator, 0));
}

void runLifecycle(void *context)
{
    auto &result = *static_cast<Result *>(context);
    result = {0, 0, true, true, true, true, true};
    check(result, result.lifecycle,
          s540NvportLifecycleContextAllowed() == NV_TRUE);
    check(result, result.lifecycle, s540NvportMemoryIsCold() == NV_TRUE &&
          !S540NvidiaReserve::ready() && S540NvidiaReserve::liveSlots() == 0);
    if (!result.lifecycle)
        return;
    const NvU32 mutexBaseline = S540NvidiaMutex::liveObjects();
    const NvU32 spinlockBaseline = S540NvidiaSpinlock::liveObjects();
    check(result, result.lifecycle, S540NvidiaReserve::initialize());
    if (!S540NvidiaReserve::ready()) {
        result.cleanup = false;
        return;
    }
    const NV_STATUS initialized = s540NvportMemoryInitialize();
    check(result, result.lifecycle, initialized == NV_OK &&
          s540NvportMemoryIsInitialized() == NV_TRUE);
    if (initialized == NV_OK) {
        const NvU32 baselineSlots = S540NvidiaReserve::liveSlots();
        const NvU32 baselineAllocators = s540NvportMemoryAllocatorCount();
        check(result, result.trackedAllocation, activeCount(nullptr, 0));
        globalAllocations(result);
        PORT_MEM_ALLOCATOR *paged = portMemAllocatorCreatePaged();
        PORT_MEM_ALLOCATOR *nonPaged = portMemAllocatorCreateNonPaged();
        check(result, result.lifecycle, paged != nullptr && nonPaged != nullptr);
        if (paged != nullptr)
            customAllocations(result, paged, 256);
        if (nonPaged != nullptr) {
            customAllocations(result, nonPaged, 512);
            boundedExhaustion(result, nonPaged);
        }
        // Destroy owned objects before releasing the owning allocators.
        if (nonPaged != nullptr)
            portMemAllocatorRelease(nonPaged);
        if (paged != nullptr && paged != nonPaged)
            portMemAllocatorRelease(paged);
        ownedMutex(result, portMemAllocatorGetGlobalNonPaged());
        ownedSpinlock(result, portMemAllocatorGetGlobalNonPaged());
        check(result, result.cleanup,
              S540NvidiaReserve::liveSlots() == baselineSlots &&
              s540NvportMemoryAllocatorCount() == baselineAllocators &&
              activeCount(nullptr, 0));
        portMemShutdown(NV_TRUE);
    }
    check(result, result.cleanup, s540NvportMemoryIsCold() == NV_TRUE &&
          S540NvidiaReserve::liveSlots() == 0 &&
          S540NvidiaMutex::liveObjects() == mutexBaseline &&
          S540NvidiaSpinlock::liveObjects() == spinlockBaseline);
    check(result, result.cleanup, S540NvidiaReserve::shutdown());
    check(result, result.cleanup,
          !S540NvidiaReserve::ready() && S540NvidiaReserve::liveSlots() == 0);
}

} // namespace

S540NvidiaLifecycleRuntime::IntegratedResult
S540NvidiaLifecycleRuntime::checkIntegrated()
{
    IntegratedResult result{};
    // Positive failed evidence if the shared lease or prior cleanup refuses
    // the continuation. Absence must not look like a successful empty test.
    result.lifecycle = {1, 1, false, false, false, false, false};
    result.v5 = S540NvidiaCallerRuntime::checkIntegrated(
        runLifecycle, &result.lifecycle);
    result.acquired = result.v5.acquired;
    return result;
}
