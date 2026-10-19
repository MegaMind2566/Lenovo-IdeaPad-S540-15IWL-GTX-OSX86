/* SPDX-License-Identifier: MIT */
#include "S540NvidiaGspCancellation.h"
#include "../../nvidia-darwin-services/src/S540NvidiaDarwinServices.h"

enum { BOUND = 1, OPERATION = 2, CLEANUP = 4, REVOKED = 8, PUBLISHING = 16,
       SHIFT = 5 };
#define GENERATION_MAX (~(NvU64)0 >> SHIFT)
#define PM_BUDGET_NS (30000000000ULL)
/* No constructor, allocator, borrowed owner or original RM lock. control==1
 * reserves construction, while generation zero is never a published binding.
 */
static struct {
    NvU64 control, generation, ownerThread, revokedAtNs, deadlineNs;
    const void *state;
    NvU32 checks, operationAborts, cleanupExpirations;
} slot;
static NvU64 word(void) { return __atomic_load_n(&slot.control, __ATOMIC_ACQUIRE); }
static NvU64 generation(NvU64 value) { return value >> SHIFT; }
static NvU64 thread(void) {
    NvU64 value = 0;
    return s540Darwin_os_get_current_thread(&value) == NV_OK ? value : 0;
}
static NvBool ownerThread(void) {
    const NvU64 current = thread();
    return current && current == __atomic_load_n(&slot.ownerThread, __ATOMIC_ACQUIRE);
}
static NvBool owner(void) {
    return s540Darwin_os_semaphore_may_sleep() && ownerThread();
}
static NvBool matches(NvU64 value, S540GspCancellationToken token) {
    return token && generation(value) == token && (value & BOUND);
}
static void increment(NvU32 *counter) {
    NvU32 value = __atomic_load_n(counter, __ATOMIC_RELAXED);
    while (value != ~(NvU32)0 && !__atomic_compare_exchange_n(counter, &value,
        value + 1, NV_FALSE, __ATOMIC_RELAXED, __ATOMIC_RELAXED)) {}
}
NV_STATUS s540GspCancellationBind(void *state, S540GspCancellationToken *out) {
    NvU64 empty = 0, next, tid = thread();
    if (!state || !out || !tid || !s540Darwin_os_semaphore_may_sleep())
        return NV_ERR_INVALID_ARGUMENT;
    if (!__atomic_compare_exchange_n(&slot.control, &empty, (NvU64)BOUND,
        NV_FALSE, __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE)) return NV_ERR_IN_USE;
    next = __atomic_load_n(&slot.generation, __ATOMIC_RELAXED);
    if (next == GENERATION_MAX) {
        __atomic_store_n(&slot.control, (NvU64)0, __ATOMIC_RELEASE);
        return NV_ERR_INSUFFICIENT_RESOURCES;
    }
    ++next;
    __atomic_store_n(&slot.generation, next, __ATOMIC_RELAXED);
    __atomic_store_n(&slot.state, state, __ATOMIC_RELAXED);
    __atomic_store_n(&slot.ownerThread, tid, __ATOMIC_RELAXED);
    __atomic_store_n(&slot.revokedAtNs, (NvU64)0, __ATOMIC_RELAXED);
    __atomic_store_n(&slot.deadlineNs, (NvU64)0, __ATOMIC_RELAXED);
    __atomic_store_n(&slot.checks, 0U, __ATOMIC_RELAXED);
    __atomic_store_n(&slot.operationAborts, 0U, __ATOMIC_RELAXED);
    __atomic_store_n(&slot.cleanupExpirations, 0U, __ATOMIC_RELAXED);
    __atomic_store_n(&slot.control, (next << SHIFT) | BOUND, __ATOMIC_RELEASE);
    *out = next;
    return NV_OK;
}
NV_STATUS s540GspCancellationBegin(S540GspCancellationToken token) {
    NvU64 value = word();
    if (!owner() || !matches(value, token)) return NV_ERR_INVALID_STATE;
    for (;;) {
        if (!matches(value, token)) return NV_ERR_INVALID_STATE;
        if (value & REVOKED) return NV_ERR_OPERATION_ABORTED;
        if (value & PUBLISHING) return NV_ERR_NOT_READY;
        if (value & (OPERATION | CLEANUP)) return NV_ERR_IN_USE;
        if (__atomic_compare_exchange_n(&slot.control, &value, value | OPERATION,
            NV_FALSE, __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE)) return NV_OK;
    }
}
NV_STATUS s540GspCancellationRevoke(S540GspCancellationToken token) {
    return s540GspCancellationRevokeAt(token, s540Darwin_os_get_monotonic_time_ns());
}
NV_STATUS s540GspCancellationRevokeAt(S540GspCancellationToken token, NvU64 eventNs) {
    NvU64 value = word(), now, deadline;
    /* Reserve publication before writing its payload, then publish REVOKED
     * with release ordering. An operation must never observe an abort whose
     * cleanup deadline is not available yet. The event timestamp is fixed
     * before reservation; scheduling cannot extend its PM budget.
     */
    now = s540Darwin_os_get_monotonic_time_ns();
    if (!eventNs || eventNs > now) return NV_ERR_INVALID_ARGUMENT;
    deadline = eventNs > ~(NvU64)0 - PM_BUDGET_NS ? ~(NvU64)0 : eventNs + PM_BUDGET_NS;
    for (;;) {
        if (!matches(value, token)) return NV_ERR_INVALID_STATE;
        if (value & (REVOKED | PUBLISHING)) return NV_OK;
        if (__atomic_compare_exchange_n(&slot.control, &value,
            value | PUBLISHING, NV_FALSE,
            __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE)) break;
    }
    __atomic_store_n(&slot.revokedAtNs, eventNs, __ATOMIC_RELAXED);
    __atomic_store_n(&slot.deadlineNs, deadline, __ATOMIC_RELEASE);
    /* Unbind refuses PUBLISHING, so a stale publisher cannot overwrite a
     * later binding. Preserve a concurrent owner's operation→cleanup change.
     */
    value = word();
    while (!__atomic_compare_exchange_n(&slot.control, &value,
        (value | REVOKED) & ~(NvU64)PUBLISHING, NV_FALSE,
        __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE)) {}
    return NV_OK;
}
NV_STATUS s540GspCancellationCheckState(const void *state) {
    NvU64 value = word(), deadline;
    if (!generation(value) || !(value & BOUND) || !state ||
        state != __atomic_load_n(&slot.state, __ATOMIC_ACQUIRE) || !ownerThread())
        return NV_OK;
    increment(&slot.checks);
    if ((value & (OPERATION | REVOKED)) == (OPERATION | REVOKED)) {
        increment(&slot.operationAborts); return NV_ERR_OPERATION_ABORTED;
    }
    if ((value & (CLEANUP | REVOKED)) != (CLEANUP | REVOKED)) return NV_OK;
    if (value & PUBLISHING) return NV_ERR_NOT_READY;
    deadline = __atomic_load_n(&slot.deadlineNs, __ATOMIC_ACQUIRE);
    if (!deadline) return NV_ERR_NOT_READY;
    if (s540Darwin_os_get_monotonic_time_ns() >= deadline) {
        increment(&slot.cleanupExpirations); return NV_ERR_TIMEOUT;
    }
    return NV_OK;
}
NvBool s540GspCancellationCurrentScopeActive(void) {
    const NvU64 value = word();
    return generation(value) && (value & BOUND) && (value & (OPERATION | CLEANUP)) && ownerThread();
}
NV_STATUS s540GspCancellationCheckCurrent(void) {
    return s540GspCancellationCheckState(__atomic_load_n(&slot.state, __ATOMIC_ACQUIRE));
}
NV_STATUS s540GspCancellationPauseCurrent(void) {
    NV_STATUS status;
    if (!owner() || !s540GspCancellationCurrentScopeActive()) return NV_ERR_INVALID_STATE;
    status = s540GspCancellationCheckCurrent();
    if (status != NV_OK) return status;
    status = s540Darwin_os_delay(1);
    return status != NV_OK ? status : s540GspCancellationCheckCurrent();
}
NV_STATUS s540GspCancellationBeginCleanupState(const void *state) {
    NvU64 value = word(), next;
    if (!generation(value) || !(value & BOUND) || !state ||
        state != __atomic_load_n(&slot.state, __ATOMIC_ACQUIRE) || !owner())
        return NV_ERR_INVALID_STATE;
    for (;;) {
        if (!(value & (OPERATION | CLEANUP))) return NV_ERR_INVALID_STATE;
        next = (value & ~(NvU64)OPERATION) | CLEANUP;
        if (__atomic_compare_exchange_n(&slot.control, &value, next,
            NV_FALSE, __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE)) return NV_OK;
    }
}
NV_STATUS s540GspCancellationFinish(S540GspCancellationToken token) {
    NvU64 value = word();
    if (!owner() || !matches(value, token)) return NV_ERR_INVALID_STATE;
    for (;;) {
        if (!matches(value, token)) return NV_ERR_INVALID_STATE;
        if (__atomic_compare_exchange_n(&slot.control, &value,
            value & ~(NvU64)(OPERATION | CLEANUP), NV_FALSE,
            __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE)) return NV_OK;
    }
}
NV_STATUS s540GspCancellationUnbind(S540GspCancellationToken token) {
    NvU64 value = word();
    if (!owner() || !matches(value, token)) return NV_ERR_INVALID_STATE;
    if (value & (OPERATION | CLEANUP | PUBLISHING)) return NV_ERR_IN_USE;
    if (!__atomic_compare_exchange_n(&slot.control, &value, (NvU64)0,
        NV_FALSE, __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE)) return NV_ERR_IN_USE;
    return NV_OK;
}
NV_STATUS s540GspCancellationGetSnapshot(S540GspCancellationToken token,
                                        S540GspCancellationSnapshot *out) {
    S540GspCancellationSnapshot result = {0};
    NvU64 value = word();
    if (!out || !matches(value, token)) return NV_ERR_INVALID_ARGUMENT;
    result.format = 1; result.bound = NV_TRUE; result.generation = token;
    result.phase = value & CLEANUP ? S540_GSP_CANCEL_CLEANUP :
        value & OPERATION ? S540_GSP_CANCEL_OPERATION : S540_GSP_CANCEL_IDLE;
    result.revoked = !!(value & REVOKED);
    result.publicationInFlight = !!(value & PUBLISHING);
    result.ownerThread = __atomic_load_n(&slot.ownerThread, __ATOMIC_ACQUIRE);
    result.revokedAtNs = __atomic_load_n(&slot.revokedAtNs, __ATOMIC_ACQUIRE);
    result.deadlineNs = __atomic_load_n(&slot.deadlineNs, __ATOMIC_ACQUIRE);
    result.checks = __atomic_load_n(&slot.checks, __ATOMIC_RELAXED);
    result.operationAborts = __atomic_load_n(&slot.operationAborts, __ATOMIC_RELAXED);
    result.cleanupExpirations = __atomic_load_n(&slot.cleanupExpirations, __ATOMIC_RELAXED);
    if (word() != value) return NV_ERR_BUSY_RETRY;
    *out = result;
    return NV_OK;
}
