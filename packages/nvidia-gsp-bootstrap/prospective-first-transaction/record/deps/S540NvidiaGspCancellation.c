/* SPDX-License-Identifier: MIT */
#include "Participants.h"
#include "nvidia-darwin-services/src/S540NvidiaDarwinServices.h"

enum { BOUND = 1, OPERATION = 2, CLEANUP = 4, REVOKED = 8, PUBLISHING = 16,
       CAPTURE_BUSY = 32, SHIFT = 6 };
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
enum { LEASE_READY = 1, LEASE_CLAIMED = 2, LEASE_ACTIVE = 3 };
#define LEASE_CAPACITY 64
/* tag==0 is FREE; monotonic opaque ids are never reused. Every nonzero tag
 * retains the exact binding, including claim/exit publication windows. */
static struct { NvU64 tag, binding, stateIdentity, origin, activeThread, creatorThread; } leases[LEASE_CAPACITY];
static NvU64 nextLease;
static NvBool leasesPending(void) {
    NvU32 i;
    for (i = 0; i < LEASE_CAPACITY; ++i)
        if (__atomic_load_n(&leases[i].tag, __ATOMIC_ACQUIRE)) return NV_TRUE;
    return NV_FALSE;
}
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
/* An enrolled callback is recognized solely by actual platform thread id,
 * exact binding, and ACTIVE release-published tag. No caller provides a tid. */
static NvU64 currentOrigin(NvU64 value) {
    NvU32 i; NvU64 tid = thread();
    if (!generation(value) || !(value & BOUND) || !tid) return 0;
    if (ownerThread()) return value & CLEANUP ? CLEANUP : value & OPERATION ? OPERATION : 0;
    for (i = 0; i < LEASE_CAPACITY; ++i) {
        NvU64 tag = __atomic_load_n(&leases[i].tag, __ATOMIC_ACQUIRE);
        if ((tag & 3) == LEASE_ACTIVE &&
            __atomic_load_n(&leases[i].binding, __ATOMIC_RELAXED) == generation(value) &&
            __atomic_load_n(&leases[i].activeThread, __ATOMIC_RELAXED) == tid &&
            __atomic_load_n(&leases[i].tag, __ATOMIC_ACQUIRE) == tag)
            return __atomic_load_n(&leases[i].origin, __ATOMIC_RELAXED);
    }
    return 0;
}
static NV_STATUS checkOrigin(NvU64 value, NvU64 origin) {
    NvU64 deadline;
    if (!origin) return NV_ERR_INVALID_STATE;
    increment(&slot.checks);
    if (origin == OPERATION && ((value & REVOKED) || !(value & OPERATION))) {
        increment(&slot.operationAborts); return NV_ERR_OPERATION_ABORTED;
    }
    if (origin != CLEANUP) return NV_OK;
    if (!(value & CLEANUP)) return NV_ERR_INVALID_STATE;
    if (!(value & REVOKED)) return NV_OK;
    if (value & PUBLISHING) return NV_ERR_NOT_READY;
    deadline = __atomic_load_n(&slot.deadlineNs, __ATOMIC_ACQUIRE);
    if (!deadline) return NV_ERR_NOT_READY;
    if (s540Darwin_os_get_monotonic_time_ns() >= deadline) {
        increment(&slot.cleanupExpirations); return NV_ERR_TIMEOUT;
    }
    return NV_OK;
}
NV_STATUS s540GspCancellationCaptureCurrent(const void *state, S540GspCancellationLease *out) {
    NvU64 value = word(), origin, reserved, id; NvU32 i; NV_STATUS status;
    if (out) *out = 0;
    if (!state || !out || state != __atomic_load_n(&slot.state, __ATOMIC_ACQUIRE)) return NV_ERR_INVALID_STATE;
    origin = currentOrigin(value);
    if (!origin || !(value & (OPERATION | CLEANUP))) return NV_ERR_INVALID_STATE;
    if (value & (CAPTURE_BUSY | PUBLISHING)) return NV_ERR_BUSY_RETRY;
    status = checkOrigin(value, origin);
    if (status != NV_OK) return status;
    reserved = value | CAPTURE_BUSY;
    /* Admission linearizes at this exact word CAS: its immutable origin
     * is validated against phase/revoke in the same compared control word. */
    if (!__atomic_compare_exchange_n(&slot.control, &value, reserved, NV_FALSE,
        __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE)) return NV_ERR_BUSY_RETRY;
    for (i = 0; i < LEASE_CAPACITY; ++i)
        if (!__atomic_load_n(&leases[i].tag, __ATOMIC_ACQUIRE)) break;
    if (i == LEASE_CAPACITY || nextLease == (~(NvU64)0 >> 2)) status = NV_ERR_INSUFFICIENT_RESOURCES;
    else {
        id = ++nextLease;
        __atomic_store_n(&leases[i].binding, generation(reserved), __ATOMIC_RELAXED);
        __atomic_store_n(&leases[i].stateIdentity, (NvU64)(NvUPtr)state, __ATOMIC_RELAXED);
        __atomic_store_n(&leases[i].origin, origin, __ATOMIC_RELAXED);
        __atomic_store_n(&leases[i].creatorThread, thread(), __ATOMIC_RELAXED);
        __atomic_store_n(&leases[i].activeThread, 0, __ATOMIC_RELAXED);
        __atomic_store_n(&leases[i].tag, (id << 2) | LEASE_READY, __ATOMIC_RELEASE);
        *out = id; status = NV_OK;
    }
    (void)__atomic_fetch_and(&slot.control, ~(NvU64)CAPTURE_BUSY, __ATOMIC_RELEASE);
    return status;
}
static NvS32 findLease(S540GspCancellationLease id, const void *state, NvU64 *tag) {
    NvU32 i; NvU64 value = word();
    if (!id || !state || !(value & BOUND) || !generation(value) ||
        state != __atomic_load_n(&slot.state, __ATOMIC_ACQUIRE)) return -1;
    for (i = 0; i < LEASE_CAPACITY; ++i) {
        *tag = __atomic_load_n(&leases[i].tag, __ATOMIC_ACQUIRE);
        if ((*tag >> 2) == id && (*tag & 3) &&
            __atomic_load_n(&leases[i].binding, __ATOMIC_RELAXED) == generation(value) &&
            __atomic_load_n(&leases[i].stateIdentity, __ATOMIC_RELAXED) == (NvU64)(NvUPtr)state)
            return (NvS32)i;
    }
    return -1;
}
NV_STATUS s540GspCancellationEnterLease(S540GspCancellationLease id, const void *state) {
    NvU64 tag, tid = thread(), claimed; NvS32 i = findLease(id, state, &tag);
    if (i < 0 || !tid || ownerThread() || currentOrigin(word()) || (tag & 3) != LEASE_READY)
        return NV_ERR_INVALID_STATE;
    claimed = (id << 2) | LEASE_CLAIMED;
    if (!__atomic_compare_exchange_n(&leases[i].tag, &tag, claimed, NV_FALSE,
        __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE)) return NV_ERR_IN_USE;
    __atomic_store_n(&leases[i].activeThread, tid, __ATOMIC_RELAXED);
    __atomic_store_n(&leases[i].tag, (id << 2) | LEASE_ACTIVE, __ATOMIC_RELEASE);
    /* Even a revoked OP lease enters: the original done block must dispose
     * accepted data. CheckCurrent decides whether its function may execute. */
    return NV_OK;
}
NV_STATUS s540GspCancellationLeaveLease(S540GspCancellationLease id, const void *state) {
    NvU64 tag; NvS32 i = findLease(id, state, &tag);
    if (i < 0 || (tag & 3) != LEASE_ACTIVE ||
        __atomic_load_n(&leases[i].activeThread, __ATOMIC_RELAXED) != thread()) return NV_ERR_INVALID_STATE;
    if (!__atomic_compare_exchange_n(&leases[i].tag, &tag, (id << 2) | LEASE_CLAIMED, NV_FALSE,
        __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE)) return NV_ERR_IN_USE;
    __atomic_store_n(&leases[i].activeThread, 0, __ATOMIC_RELAXED);
    __atomic_store_n(&leases[i].tag, 0, __ATOMIC_RELEASE);
    return NV_OK;
}
NV_STATUS s540GspCancellationDiscardLease(S540GspCancellationLease id, const void *state) {
    NvU64 tag, tid = thread(); NvS32 i = findLease(id, state, &tag);
    if (i < 0 || (tag & 3) != LEASE_READY || (!ownerThread() &&
        __atomic_load_n(&leases[i].creatorThread, __ATOMIC_RELAXED) != tid)) return NV_ERR_INVALID_STATE;
    /* Caller must separately prove queue rejection or real timer cancellation;
     * this API does not attest that the callback cannot still execute. */
    return __atomic_compare_exchange_n(&leases[i].tag, &tag, 0, NV_FALSE,
        __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE) ? NV_OK : NV_ERR_IN_USE;
}
NvU32 s540GspCancellationPendingLeases(void) {
    NvU32 i, n = 0; for (i = 0; i < LEASE_CAPACITY; ++i)
        if (__atomic_load_n(&leases[i].tag, __ATOMIC_ACQUIRE)) ++n;
    return n;
}
NvBool s540GspCancellationSkipOptionalCurrent(void) {
    NvU64 value = word();
    return generation(value) && (value & BOUND) && (value & (OPERATION | CLEANUP)) &&
        (value & REVOKED) && currentOrigin(value);
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
    NvU64 value = word(), origin;
    if (!generation(value) || !(value & BOUND) || !state ||
        state != __atomic_load_n(&slot.state, __ATOMIC_ACQUIRE)) return NV_OK;
    origin = currentOrigin(value);
    return origin ? checkOrigin(value, origin) : NV_OK;
}
NvBool s540GspCancellationCurrentScopeActive(void) {
    NvU64 value = word();
    return generation(value) && (value & BOUND) && (value & (OPERATION | CLEANUP)) && currentOrigin(value);
}
NV_STATUS s540GspCancellationCheckCurrent(void) {
    return s540GspCancellationCheckState(__atomic_load_n(&slot.state, __ATOMIC_ACQUIRE));
}
NV_STATUS s540GspCancellationPauseCurrent(void) {
    NV_STATUS status;
    if (!s540Darwin_os_semaphore_may_sleep() || !s540GspCancellationCurrentScopeActive()) return NV_ERR_INVALID_STATE;
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
        if (value & CAPTURE_BUSY) return NV_ERR_BUSY_RETRY;
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
        if ((value & (CAPTURE_BUSY | PUBLISHING)) || leasesPending()) return NV_ERR_IN_USE;
        if (__atomic_compare_exchange_n(&slot.control, &value,
            value & ~(NvU64)(OPERATION | CLEANUP), NV_FALSE,
            __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE)) return NV_OK;
    }
}
NV_STATUS s540GspCancellationUnbind(S540GspCancellationToken token) {
    NvU64 value = word();
    if (!owner() || !matches(value, token)) return NV_ERR_INVALID_STATE;
    if ((value & (OPERATION | CLEANUP | PUBLISHING | CAPTURE_BUSY)) || leasesPending()) return NV_ERR_IN_USE;
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
