// SPDX-License-Identifier: MIT
// Isolated prospective integration. No arbitrary stop/evidence callbacks.
#include "S540NvidiaFirstTxnServices.h"
#include "S540NvidiaGspFirstTransaction.h"

extern "C" NV_STATUS s540GspTimersStop(struct nv_state_t *);
namespace {
struct ServiceBinding {
    const void *nv;
    NvU64 generation;
    os_work_queue *device, *global;
};
// Single first transaction, immutable once published. There is deliberately no
// unbind/receipt issuer until final hardware and text-lifetime proof exists.
ServiceBinding binding;
NvU32 publication;
bool exact(const void *nv, NvU64 generation) {
    return __atomic_load_n(&publication, __ATOMIC_ACQUIRE) == 2 &&
        nv == binding.nv && generation == binding.generation;
}
}
extern "C" NV_STATUS s540FirstTxnServicesBind(const void *nv, NvU64 generation,
    os_work_queue *device, os_work_queue *global) {
    if (!nv || !generation || !device || !global || device == global ||
        !s540Darwin_os_semaphore_may_sleep()) return NV_ERR_INVALID_ARGUMENT;
    NvU32 empty = 0;
    if (!__atomic_compare_exchange_n(&publication, &empty, 1U, false,
            __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE)) return NV_ERR_STATE_IN_USE;
    // A partial binding remains owned and retry is refused, never discarded.
    binding = {nv, generation, device, global};
    NV_STATUS status = s540FirstTxnQueueBind(device, nv, generation);
    if (status == NV_OK) status = s540FirstTxnQueueBind(global, nv, generation);
    if (status == NV_OK) status = s540FirstTxnTimersBind(nv, generation);
    __atomic_store_n(&publication, status == NV_OK ? 2U : 3U, __ATOMIC_RELEASE);
    return status;
}
extern "C" NV_STATUS s540FirstTxnServicesSealAndDrain(const void *nv, NvU64 generation) {
    if (!exact(nv, generation)) return NV_ERR_INVALID_STATE;
    // Actual original lock ownership probe, outside every queue/timer guard.
    // Current RM-semaphore exclusion is an admission gap, never a caller flag.
    NV_STATUS status = s540FirstTxnOriginalLocksReleased(nv);
    if (status != NV_OK) return status;
    status = s540GspTimersStop(static_cast<struct nv_state_t *>(const_cast<void *>(nv)));
    if (status != NV_OK) return status;
    // Closed service identities stay published. NULL enqueue cannot fall back
    // to a fresh global queue and bypass these actual admission barriers.
    status = s540FirstTxnQueueSeal(binding.device, nv, generation);
    if (status != NV_OK) return status;
    status = s540FirstTxnQueueSeal(binding.global, nv, generation);
    if (status != NV_OK) return status;
    status = s540DarwinWorkQueueStop(binding.device);
    if (status != NV_OK) return status;
    status = s540DarwinWorkQueueStop(binding.global);
    if (status != NV_OK) return status;
    return s540FirstTxnServicesValidateRetired(nv, generation);
}
extern "C" NV_STATUS s540FirstTxnServicesValidateRetired(const void *nv, NvU64 generation) {
    if (!exact(nv, generation)) return NV_ERR_INVALID_STATE;
    NV_STATUS status = s540FirstTxnQueueValidateStopped(binding.device, nv, generation);
    if (status != NV_OK) return status;
    status = s540FirstTxnQueueValidateStopped(binding.global, nv, generation);
    if (status != NV_OK) return status;
    return s540FirstTxnTimersValidateStopped(nv, generation);
}
