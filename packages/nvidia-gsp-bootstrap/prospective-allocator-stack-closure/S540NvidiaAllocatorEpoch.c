/* SPDX-License-Identifier: MIT */
/* Opt-in retained global epoch. These guards do not grant original entry. */
#include "S540NvidiaAllocatorEpoch.h"
#include "S540NvidiaGspFirstTransaction.h"
#include "S540NvidiaDarwinServices.h"

static struct {
    NvU32 portableBusy, memoryBusy, portableReady, memoryReady;
    NvU64 refusedInitializations, refusedShutdowns, invalidCompletions;
    NvU64 initializerThread;
} state;

static void refused(NvU64 *counter)
{
    NvU64 value = __atomic_load_n(counter, __ATOMIC_RELAXED);
    while (value != ~(NvU64)0 && !__atomic_compare_exchange_n(counter, &value,
            value + 1, NV_FALSE, __ATOMIC_RELAXED, __ATOMIC_RELAXED)) { }
}

static NV_STATUS authorize(NvU64 *thread)
{
    S540FirstTxnGlobalSnapshot epoch = {0};
    NV_STATUS status = s540FirstTxnGlobalReadMaster(&epoch);
    if (status != NV_OK) return status;
    if (!epoch.owner || !epoch.generation || !epoch.masterThread || epoch.nv ||
        epoch.state != S540_FIRST_GLOBAL_IN_CORE || epoch.originalReturned)
        return NV_ERR_INVALID_STATE;
    *thread = epoch.masterThread;
    return NV_OK;
}

static NV_STATUS initializationRefused(NV_STATUS status)
{
    refused(&state.refusedInitializations);
    return status;
}

static NvBool completingOwner(void)
{
    NvU64 thread = 0;
    return s540Darwin_os_get_current_thread(&thread) == NV_OK && thread &&
        thread == __atomic_load_n(&state.initializerThread, __ATOMIC_ACQUIRE);
}

NV_STATUS s540AllocatorPortableBegin(void)
{
    NvU64 thread = 0;
    NvU32 expected = 0;
    NV_STATUS status = authorize(&thread);
    if (status != NV_OK) return initializationRefused(status);
    if (!__atomic_compare_exchange_n(&state.portableBusy, &expected, 1,
            NV_FALSE, __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE))
        return initializationRefused(NV_ERR_IN_USE);
    __atomic_store_n(&state.initializerThread, thread, __ATOMIC_RELEASE);
    return NV_OK;
}

NV_STATUS s540AllocatorPortableEnd(NV_STATUS originalStatus)
{
    if (!completingOwner() || !__atomic_load_n(&state.portableBusy, __ATOMIC_ACQUIRE) ||
        __atomic_load_n(&state.memoryBusy, __ATOMIC_ACQUIRE)) {
        refused(&state.invalidCompletions);
        return originalStatus != NV_OK ? originalStatus : NV_ERR_INVALID_STATE;
    }
    __atomic_store_n(&state.portableReady, originalStatus == NV_OK, __ATOMIC_RELEASE);
    __atomic_store_n(&state.portableBusy, 0, __ATOMIC_RELEASE);
    return originalStatus;
}

NV_STATUS s540AllocatorMemoryBegin(void)
{
    NvU64 thread = 0;
    NvU32 expected = 0;
    NV_STATUS status = authorize(&thread);
    if (status != NV_OK) return initializationRefused(status);
    if (!__atomic_load_n(&state.portableBusy, __ATOMIC_ACQUIRE) ||
        thread != __atomic_load_n(&state.initializerThread, __ATOMIC_ACQUIRE))
        return initializationRefused(NV_ERR_INVALID_STATE);
    if (!__atomic_compare_exchange_n(&state.memoryBusy, &expected, 1,
            NV_FALSE, __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE))
        return initializationRefused(NV_ERR_IN_USE);
    return NV_OK;
}

NV_STATUS s540AllocatorMemoryEnd(NV_STATUS originalStatus)
{
    if (!completingOwner() || !__atomic_load_n(&state.memoryBusy, __ATOMIC_ACQUIRE)) {
        refused(&state.invalidCompletions);
        return originalStatus != NV_OK ? originalStatus : NV_ERR_INVALID_STATE;
    }
    __atomic_store_n(&state.memoryReady, originalStatus == NV_OK, __ATOMIC_RELEASE);
    __atomic_store_n(&state.memoryBusy, 0, __ATOMIC_RELEASE);
    return originalStatus;
}

NV_STATUS s540AllocatorPortableRelease(NvU32 actualReferenceCount)
{
    NvU64 thread = 0;
    NV_STATUS status = authorize(&thread);
    /* The retained outer portable reference is never relinquished. Nested
     * TLS/NVLOG references may balance after a completed initializer. */
    if (status != NV_OK || actualReferenceCount <= 1 ||
        __atomic_load_n(&state.portableBusy, __ATOMIC_ACQUIRE) ||
        thread != __atomic_load_n(&state.initializerThread, __ATOMIC_ACQUIRE)) {
        refused(&state.refusedShutdowns);
        return status != NV_OK ? status : NV_ERR_INVALID_STATE;
    }
    return NV_OK;
}

NV_STATUS s540AllocatorMemoryShutdown(void)
{
    /* Selected global owner retains its base runtime until reboot. No raw
     * caller can erase allocator tracking or callbacks behind that owner. */
    refused(&state.refusedShutdowns);
    return NV_ERR_NOT_SUPPORTED;
}

NV_STATUS s540AllocatorGlobalUse(void)
{
    /* Other original portable modules may allocate after memory initialization
     * and before the outer portable initializer returns. Publication of the
     * actual memory initializer, rather than outer completion, is required. */
    if (__atomic_load_n(&state.memoryReady, __ATOMIC_ACQUIRE) &&
        !__atomic_load_n(&state.memoryBusy, __ATOMIC_ACQUIRE)) return NV_OK;
    return initializationRefused(NV_ERR_NOT_READY);
}

void s540AllocatorTrackingRefused(void)
{
    refused(&state.refusedInitializations);
}

NvBool s540AllocatorPortableVisible(void)
{
    return !__atomic_load_n(&state.portableBusy, __ATOMIC_ACQUIRE) &&
        __atomic_load_n(&state.portableReady, __ATOMIC_ACQUIRE) &&
        __atomic_load_n(&state.memoryReady, __ATOMIC_ACQUIRE);
}

void s540AllocatorEpochSnapshot(S540AllocatorEpochSnapshot *out)
{
    if (!out) return;
#define COPY(field) out->field = __atomic_load_n(&state.field, __ATOMIC_ACQUIRE)
    COPY(portableBusy); COPY(memoryBusy); COPY(portableReady); COPY(memoryReady);
    COPY(refusedInitializations); COPY(refusedShutdowns); COPY(invalidCompletions);
    COPY(initializerThread);
#undef COPY
}
