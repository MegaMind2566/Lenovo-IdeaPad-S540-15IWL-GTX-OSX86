/* SPDX-License-Identifier: MIT */
/* Genuine per-attempt state for the image that admits no user mappings.
 * This is separate from kernel BAR maps and every DMA ownership receipt. */
#include "nv.h"
#include "../prospective-first-transaction/record/S540NvidiaGspFirstTransaction.h"
#include "../../nvidia-darwin-services/src/S540NvidiaDarwinServices.h"

#if !defined(S540_NVIDIA_NO_USER_MAPPINGS) || S540_NVIDIA_NO_USER_MAPPINGS != 1
#error "The mapping backend requires the selected image with no user mapping ingress"
#endif
#if defined(NV_UVM_ENABLE)
#error "The no-user-mapping backend cannot serve an enabled UVM backend"
#endif
#if defined(NV_PM_RUNTIME_AVAILABLE)
#error "The selected retained image has no runtime-PM backend"
#endif

/* A successful partial initialization is permanent. There is no replacement,
 * reset, release issuer, or public mapping-registration API in this profile. */
static struct {
    NvU32 state; /* 0 empty, 1 constructing, 2 ready, 3 failed and retained */
    nv_state_t *nv;
    const void *owner;
    NvU64 generation, holder;
    void *mutex;
    NvBool allRevoked, safeToMmap, wakeupNeeded;
} mappings;
#define LOAD(field) __atomic_load_n(&mappings.field, __ATOMIC_ACQUIRE)
#define STORE(field, value) __atomic_store_n(&mappings.field, (value), __ATOMIC_RELEASE)

static NV_STATUS refusal(NV_STATUS status)
{
    if (status == NV_OK) status = NV_ERR_INVALID_STATE;
    s540FirstTxnObserveServiceRefusal(0x4d4d4150U, 1U, status);
    return status;
}

static NV_STATUS authenticate(nv_state_t *nv, NvU64 *thread,
    S540FirstTxnSnapshot *snapshot, S540FirstTxnHostIdentity *identity)
{
    NV_STATUS status;
    if (!nv || !thread || !snapshot || !identity ||
        !s540Darwin_os_semaphore_may_sleep()) return NV_ERR_INVALID_ARGUMENT;
    /* Pull exact identity before any dereference of the candidate nv. */
    status = s540FirstTxnGetSnapshot(nv, snapshot);
    if (status != NV_OK) return status;
    if (snapshot->firstStatus != NV_OK) return snapshot->firstStatus;
    if (!snapshot->generation || snapshot->phase != S540_FIRST_OP)
        return NV_ERR_NOT_READY;
    status = s540FirstTxnHostCaptureAllocation(identity);
    if (status != NV_OK) return status;
    if (!identity->owner || identity->generation != snapshot->generation)
        return NV_ERR_INVALID_STATE;
    status = s540Darwin_os_get_current_thread(thread);
    return status != NV_OK ? status : (*thread ? NV_OK : NV_ERR_INVALID_STATE);
}

static NV_STATUS ready(nv_state_t *nv, NvU64 *thread)
{
    S540FirstTxnSnapshot snapshot;
    S540FirstTxnHostIdentity identity;
    NvU32 empty = 0;
    NV_STATUS status = authenticate(nv, thread, &snapshot, &identity);
    if (status != NV_OK) return refusal(status);
    if (LOAD(state) == 0 && __atomic_compare_exchange_n(&mappings.state,
            &empty, 1U, NV_FALSE, __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE)) {
        /* Original Linux storage starts zeroed. In particular, an empty list
         * alone does not initially manufacture an all-revoked receipt. */
        mappings.nv = nv;
        mappings.owner = identity.owner;
        mappings.generation = identity.generation;
        status = s540Darwin_os_alloc_mutex(&mappings.mutex);
        if (status != NV_OK || !mappings.mutex) {
            STORE(state, 3U);
            return refusal(status != NV_OK ? status : NV_ERR_NO_MEMORY);
        }
        STORE(state, 2U);
    }
    if (LOAD(state) != 2U) return refusal(NV_ERR_NOT_READY);
    if (mappings.nv != nv || mappings.owner != identity.owner ||
        mappings.generation != snapshot.generation)
        return refusal(NV_ERR_INVALID_STATE);
    return NV_OK;
}

static NV_STATUS acquire(nv_state_t *nv)
{
    NvU64 thread = 0, after = 0;
    NV_STATUS status = ready(nv, &thread);
    if (status != NV_OK) return status;
    if (LOAD(holder) == thread) return refusal(NV_ERR_INVALID_LOCK_STATE);
    status = s540Darwin_os_acquire_mutex(mappings.mutex);
    if (status != NV_OK) return refusal(status);
    /* Waiting is real: recheck the immutable tuple and sticky record after
     * acquisition; a refusal while blocked cannot turn into new mutation. */
    status = ready(nv, &after);
    if (status != NV_OK || after != thread) {
        s540Darwin_os_release_mutex(mappings.mutex);
        return status != NV_OK ? status : refusal(NV_ERR_INVALID_STATE);
    }
    STORE(holder, thread);
    return NV_OK;
}

static NvBool held(nv_state_t *nv, NvBool afterRefusal)
{
    NvU64 thread = 0;
    S540FirstTxnSnapshot snapshot;
    if (LOAD(state) != 2U || nv != mappings.nv ||
        !s540Darwin_os_semaphore_may_sleep() ||
        s540Darwin_os_get_current_thread(&thread) != NV_OK || !thread ||
        thread != LOAD(holder) ||
        s540FirstTxnGetSnapshot(nv, &snapshot) != NV_OK ||
        snapshot.generation != mappings.generation) {
        (void)refusal(NV_ERR_INVALID_LOCK_STATE);
        return NV_FALSE;
    }
    if (!afterRefusal && snapshot.firstStatus != NV_OK) {
        (void)refusal(snapshot.firstStatus);
        return NV_FALSE;
    }
    return NV_TRUE;
}

void NV_API_CALL nv_acquire_mmap_lock(nv_state_t *nv)
{
    (void)acquire(nv);
}
void NV_API_CALL nv_release_mmap_lock(nv_state_t *nv)
{
    /* The real owner must release its actual token even after sticky failure.
     * A foreign release cannot unlock or replace the retained object. */
    if (!held(nv, NV_TRUE)) return;
    STORE(holder, 0ULL);
    s540Darwin_os_release_mutex(mappings.mutex);
}
NvBool NV_API_CALL nv_get_all_mappings_revoked_locked(nv_state_t *nv)
{
    return held(nv, NV_FALSE) ? mappings.allRevoked : NV_FALSE;
}
void NV_API_CALL nv_set_safe_to_mmap_locked(nv_state_t *nv, NvBool safe)
{
    if (!held(nv, NV_FALSE)) return;
    if (!safe && LOAD(safeToMmap)) STORE(wakeupNeeded, NV_TRUE);
    STORE(safeToMmap, safe);
}
NV_STATUS NV_API_CALL nv_revoke_gpu_mappings(nv_state_t *nv)
{
    S540FirstTxnSnapshot after;
    NvU64 thread = 0;
    NV_STATUS status = ready(nv, &thread);
    if (status != NV_OK) return status;
    if (NV_IS_CTL_DEVICE(nv)) return NV_ERR_NOT_SUPPORTED;
    status = acquire(nv);
    if (status != NV_OK) return status;
    /* There is no user-memory method, mmap/fault ingress or registration API in
     * this selected image. Its admitted user mapping set is empty. This sets
     * only the matching Linux user-mapping state under the actual mutex; it
     * never revokes an IOMemoryMap or certifies DMA/hardware quiescence. */
    mappings.allRevoked = NV_TRUE;
    nv_release_mmap_lock(nv);
    /* Report an observed concurrent refusal as the actual operation result;
     * an ordinary user-mapping state update cannot erase the transaction. */
    status = s540FirstTxnGetSnapshot(nv, &after);
    if (status != NV_OK) return refusal(status);
    return after.firstStatus != NV_OK ? after.firstStatus : NV_OK;
}
