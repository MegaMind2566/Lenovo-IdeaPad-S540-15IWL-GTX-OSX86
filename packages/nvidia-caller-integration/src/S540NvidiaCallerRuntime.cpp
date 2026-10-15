// SPDX-License-Identifier: MIT
#include "S540NvidiaCallerRuntime.hpp"
#include "S540NvidiaReserve.hpp"
#include "../../nvidia-os-adapter/src/S540NvidiaMemory.hpp"
#include "../upstream/nvport_allocator_callers.h"
#include "../upstream/nvport_mutex_callers.h"

#if defined(KERNEL)
#include <machine/machine_routines.h>
#endif

namespace {

using S540NvidiaCallerRuntime::Result;

alignas(4) NvU32 gStartupLease;
static_assert(__atomic_always_lock_free(sizeof(gStartupLease), nullptr),
              "Startup serialization must never call a runtime lock.");

void check(Result &result, bool &component, bool condition)
{
    ++result.checks;
    if (!condition) {
        ++result.failures;
        component = false;
    }
}

bool ordinaryThreadContext()
{
#if defined(KERNEL)
    return !ml_at_interrupt_context() && ml_get_interrupts_enabled();
#else
    return true;
#endif
}

void allocationCallers(Result &result)
{
    using namespace S540NvidiaReserve;
    void *slots[kSlotCount];
    // Route this larger stack initialization through the reviewed memory
    // hook. An aggregate zero initializer can introduce an implicit bzero
    // import in the Darwin kernel build despite -fno-builtin.
    os_mem_set(slots, 0, static_cast<NvU32>(sizeof(slots)));
    bool full = true;
    bool uniqueAndAligned = true;
    bool contents = true;
    for (NvU32 index = 0; index < kSlotCount; ++index) {
        // Both unchanged NVIDIA allocation wrappers reach the reserve hook.
        slots[index] = (index & 1U) != 0
            ? _portMemAllocPagedUntracked(kSlotBytes)
            : _portMemAllocNonPagedUntracked(kSlotBytes);
        if (slots[index] == nullptr) {
            full = false;
            continue;
        }
        uniqueAndAligned = uniqueAndAligned &&
            reinterpret_cast<NvUPtr>(slots[index]) % kAlignment == 0;
        bool unique = true;
        for (NvU32 earlier = 0; earlier < index; ++earlier)
            unique = unique && slots[index] != slots[earlier];
        uniqueAndAligned = uniqueAndAligned && unique;
        if (!unique) {
            // Keep only one owner for cleanup if a broken hook aliases a slot.
            slots[index] = nullptr;
            full = false;
            continue;
        }
        auto *bytes = static_cast<NvU8 *>(slots[index]);
        bytes[0] = static_cast<NvU8>(index + 1);
        bytes[kSlotBytes - 1] = static_cast<NvU8>(index ^ 0xa5U);
    }
    check(result, result.allocationCallers, full);
    check(result, result.allocationCallers, uniqueAndAligned);
    check(result, result.reserve, liveSlots() == kSlotCount);

    if (full) {
        for (NvU32 index = 0; index < kSlotCount; ++index) {
            const auto *bytes = static_cast<const NvU8 *>(slots[index]);
            contents = contents && bytes[0] == static_cast<NvU8>(index + 1) &&
                bytes[kSlotBytes - 1] == static_cast<NvU8>(index ^ 0xa5U);
        }
        check(result, result.allocationCallers, contents);
        void *nonPaged = _portMemAllocNonPagedUntracked(1);
        void *paged = _portMemAllocPagedUntracked(1);
        check(result, result.allocationCallers,
              nonPaged == nullptr && paged == nullptr);
        // Unexpected successful allocations must still be returned.
        _portMemFreeUntracked(nonPaged);
        if (paged != nonPaged)
            _portMemFreeUntracked(paged);

        const bool refusedShutdown = !shutdown();
        check(result, result.reserve, refusedShutdown && ready() &&
              liveSlots() == kSlotCount);
        if (!refusedShutdown || !ready()) {
            // Do not read or free pointers after an unexpected destruction.
            os_mem_set(slots, 0, static_cast<NvU32>(sizeof(slots)));
            result.allocationCallers = false;
            return;
        }

        // Release alternating slots, then use both callers to recover them.
        for (NvU32 index = 1; index < kSlotCount; index += 2) {
            _portMemFreeUntracked(slots[index]);
            slots[index] = nullptr;
        }
        check(result, result.reserve, liveSlots() == kSlotCount / 2);
        bool reused = true;
        for (NvU32 index = 1; index < kSlotCount; index += 2) {
            slots[index] = (index & 2U) != 0
                ? _portMemAllocPagedUntracked(1)
                : _portMemAllocNonPagedUntracked(kSlotBytes - 1);
            reused = reused && slots[index] != nullptr;
        }
        check(result, result.allocationCallers, reused);
        check(result, result.reserve, liveSlots() == kSlotCount);
    }

    // The test owns every allocation and invokes the original free caller.
    for (void *slot : slots)
        _portMemFreeUntracked(slot);
    check(result, result.reserve, liveSlots() == 0);
    void *again = _portMemAllocNonPagedUntracked(256);
    check(result, result.allocationCallers, again != nullptr);
    _portMemFreeUntracked(again);
    _portMemFreeUntracked(nullptr);
    check(result, result.reserve, liveSlots() == 0);
}

void mutexCallers(Result &result)
{
    result.mutexCallers = true;
    check(result, result.mutexCallers,
          portSyncMutexInitialize(nullptr) == NV_ERR_INVALID_POINTER);
    PORT_MUTEX mutex;
    os_mem_set(&mutex, 0, static_cast<NvU32>(sizeof(mutex)));
    const NV_STATUS initialized = portSyncMutexInitialize(&mutex);
    check(result, result.mutexCallers,
          initialized == NV_OK && mutex.mutex != nullptr);
    if (initialized != NV_OK || mutex.mutex == nullptr) {
        if (mutex.mutex != nullptr)
            portSyncMutexDestroy(&mutex);
        return;
    }
    check(result, result.mutexCallers, mutex.pAllocator == nullptr);

    const NvBool acquired = portSyncMutexAcquireConditional(&mutex);
    check(result, result.mutexCallers, acquired == NV_TRUE);
    if (acquired != NV_TRUE) {
        // This newly created object has no external owner or waiter, and no
        // hook remains in flight. Abort-destroy the quiescent backing object;
        // do not enter an acquire that could block on an unexpected token.
        portSyncMutexDestroy(&mutex);
        return;
    }
    check(result, result.mutexCallers,
          portSyncMutexAcquireConditional(&mutex) == NV_FALSE);
    portSyncMutexRelease(&mutex);

    // This is an uncontended kernel acquire. The startup sequence does not
    // claim to exercise assert_wait/thread_block or cross-thread publication.
    portSyncMutexAcquire(&mutex);
    check(result, result.mutexCallers,
          portSyncMutexAcquireConditional(&mutex) == NV_FALSE);
    portSyncMutexRelease(&mutex);
    const NvBool reacquired = portSyncMutexAcquireConditional(&mutex);
    check(result, result.mutexCallers, reacquired == NV_TRUE);
    if (reacquired == NV_TRUE) {
        portSyncMutexRelease(&mutex);
    }
    // Every call has returned and no worker or waiter can outlive this frame.
    // On a failed reacquisition this is quiescent abort destruction, not reuse
    // or recovery of an unexpectedly unavailable token.
    portSyncMutexDestroy(&mutex);
}

} // namespace

S540NvidiaCallerRuntime::Result S540NvidiaCallerRuntime::run()
{
    Result result;
    os_mem_set(&result, 0, static_cast<NvU32>(sizeof(result)));
    result.reserve = true;
    check(result, result.reserve, ordinaryThreadContext());
    if (!result.reserve)
        return result;
    check(result, result.reserve,
          !S540NvidiaReserve::ready() && S540NvidiaReserve::liveSlots() == 0);
    if (!result.reserve)
        return result;

    result.allocationCallers = true;
    check(result, result.allocationCallers,
          _portMemAllocNonPagedUntracked(1) == nullptr &&
          _portMemAllocPagedUntracked(1) == nullptr);
    check(result, result.reserve, S540NvidiaReserve::initialize() &&
          S540NvidiaReserve::ready());
    if (!result.reserve) {
        result.allocationCallers = false;
        return result;
    }
    check(result, result.reserve, S540NvidiaReserve::initialize() &&
          S540NvidiaReserve::liveSlots() == 0);
    check(result, result.allocationCallers,
          _portMemAllocNonPagedUntracked(0) == nullptr &&
          _portMemAllocPagedUntracked(0) == nullptr);
    check(result, result.allocationCallers,
          _portMemAllocNonPagedUntracked(S540NvidiaReserve::kSlotBytes + 1) == nullptr);
    check(result, result.allocationCallers,
          _portMemAllocPagedUntracked(~NvLength{0}) == nullptr);

    allocationCallers(result);
    mutexCallers(result);

    check(result, result.reserve, S540NvidiaReserve::shutdown());
    check(result, result.reserve,
          !S540NvidiaReserve::ready() && S540NvidiaReserve::liveSlots() == 0);
    check(result, result.allocationCallers,
          _portMemAllocPagedUntracked(1) == nullptr);
    // Reinitialization after quiescent shutdown checks the complete lifecycle.
    check(result, result.reserve, S540NvidiaReserve::initialize());
    check(result, result.reserve, S540NvidiaReserve::shutdown() &&
          !S540NvidiaReserve::ready() && S540NvidiaReserve::liveSlots() == 0);
    return result;
}

S540NvidiaCallerRuntime::IntegratedResult S540NvidiaCallerRuntime::checkIntegrated()
{
    // Positive counts with failed components describe a refused precondition;
    // zero would be indistinguishable from absent or malformed evidence.
    IntegratedResult result;
    os_mem_set(&result, 0, static_cast<NvU32>(sizeof(result)));
    result.foundations.checks = 1;
    result.callers.checks = 1;
    result.callers.failures = 1;
    NvU32 expected = 0;
    if (!__atomic_compare_exchange_n(&gStartupLease, &expected, NvU32{1}, false,
                                      __ATOMIC_ACQUIRE, __ATOMIC_RELAXED))
        return result;
    result.acquired = true;

    result.callers = run();
    const bool cold = !S540NvidiaReserve::ready() &&
        S540NvidiaReserve::liveSlots() == 0;
    check(result.callers, result.callers.reserve, cold);
    if (cold) {
        const bool initialized = S540NvidiaReserve::initialize();
        check(result.callers, result.callers.reserve, initialized);
        if (initialized)
            result.foundations = S540NvidiaRuntime::check();
        const bool cleaned = S540NvidiaReserve::shutdown() &&
            !S540NvidiaReserve::ready() && S540NvidiaReserve::liveSlots() == 0;
        check(result.callers, result.callers.reserve, cleaned);
        if (!cleaned) {
            result.foundations.allocation = false;
            result.foundations.mutex = false;
        }
    }

    __atomic_store_n(&gStartupLease, NvU32{0}, __ATOMIC_RELEASE);
    return result;
}
