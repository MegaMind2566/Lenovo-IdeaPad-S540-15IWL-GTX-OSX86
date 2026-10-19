/* SPDX-License-Identifier: MIT */
/* Exact NVIDIA types and entry; no model, caller readiness bit or stop issuer. */
#include "nv.h"
#include "nv-priv.h"
#include "osapi.h"
#include "gpu/gpu.h"
#include "core/locks.h"
#include "core/thread_state.h"
#include "rmapi/rmapi.h"
#include "S540NvidiaShutdownProtocol.h"
#include "SourceProfile.h"
#include "../prospective-first-transaction/record/S540NvidiaGspFirstTransaction.h"
#include "../../nvidia-darwin-services/src/S540NvidiaDarwinServices.h"

/* No reset/unbind entry exists: a partial protocol may not be safe to retry.
 * The claim remains even when an API/GPU token acquisition fails. */
static NvU32 protocolClaim;
static struct {
    const void *owner;
    nv_state_t *nv;
    nv_priv_t *privateState;
    OBJGPU *gpu;
    NvU64 generation, masterThread;
} protocolIdentity;

static NV_STATUS captureIdentity(nv_state_t *nv,
    S540FirstTxnSnapshot *snapshot, S540FirstTxnHostIdentity *identity)
{
    NvU64 thread = 0;
    NV_STATUS status;
    if (!nv || !snapshot || !identity || !s540Darwin_os_semaphore_may_sleep())
        return NV_ERR_INVALID_ARGUMENT;
    /* The exact-record pull must succeed BEFORE nv or its private GPU is read. */
    status = s540FirstTxnGetSnapshot(nv, snapshot);
    if (status != NV_OK) return status;
    if (snapshot->firstStatus != NV_OK) return snapshot->firstStatus;
    if (!snapshot->generation || snapshot->phase != S540_FIRST_OP ||
        snapshot->originalInFlight || !snapshot->originalReturned ||
        !snapshot->originalExitReady || snapshot->cleanupRequested ||
        snapshot->inFlightFreePermits)
        return NV_ERR_NOT_READY;
    status = s540Darwin_os_get_current_thread(&thread);
    if (status != NV_OK) return status;
    if (!thread || thread != snapshot->masterThread) return NV_ERR_INVALID_STATE;
    status = s540FirstTxnHostCaptureAllocation(identity);
    if (status != NV_OK) return status;
    if (!identity->owner || identity->generation != snapshot->generation)
        return NV_ERR_INVALID_STATE;
    return s540FirstTxnOriginalLocksReleased(nv);
}

static NvBool sameOriginalIdentity(nv_state_t *nv)
{
    nv_priv_t *privateState;
    OBJGPU *gpu;
    if (nv != protocolIdentity.nv) return NV_FALSE;
    privateState = NV_GET_NV_PRIV(nv);
    if (!privateState || privateState != protocolIdentity.privateState)
        return NV_FALSE;
    gpu = NV_GET_NV_PRIV_PGPU(nv);
    if (!gpu || gpu != protocolIdentity.gpu || NV_GET_NV_STATE(gpu) != nv)
        return NV_FALSE;
    if (!IS_GSP_CLIENT(gpu)) return NV_FALSE;
    return (privateState->flags & (NV_INIT_FLAG_GPU_STATE | NV_INIT_FLAG_GPU_STATE_LOAD)) ==
        (NV_INIT_FLAG_GPU_STATE | NV_INIT_FLAG_GPU_STATE_LOAD);
}

NV_STATUS s540ShutdownProtocolRun(nvidia_stack_t *stack, nv_state_t *nv,
    S540ShutdownProtocolEvidence *out)
{
    S540FirstTxnSnapshot before = {0}, after = {0};
    S540FirstTxnHostIdentity identity = {0};
    S540ShutdownProtocolEvidence evidence = {0};
    THREAD_STATE_NODE threadState;
    nv_priv_t *privateState;
    OBJGPU *gpu;
    void *fp;
    NvU32 expected = 0;
    NV_STATUS status, releaseStatus;
    if (!out) return NV_ERR_INVALID_ARGUMENT;
    evidence.format = 1;
    evidence.sourceProfileSha256 = S540_SHUTDOWN_SOURCE_PROFILE_SHA256;
    evidence.originalReturnStatus = NV_ERR_NOT_READY;
    evidence.unlockStatus = NV_OK;
    if (!stack || !nv) { status = NV_ERR_INVALID_ARGUMENT; goto publish; }
    if (__atomic_load_n(&protocolClaim, __ATOMIC_ACQUIRE)) {
        status = NV_ERR_STATE_IN_USE; goto publish;
    }
    status = captureIdentity(nv, &before, &identity);
    if (status != NV_OK) goto publish;
    privateState = NV_GET_NV_PRIV(nv);
    gpu = NV_GET_NV_PRIV_PGPU(nv);
    if (!privateState || !gpu || NV_GET_NV_STATE(gpu) != nv || !IS_GSP_CLIENT(gpu) ||
        (privateState->flags & (NV_INIT_FLAG_GPU_STATE | NV_INIT_FLAG_GPU_STATE_LOAD)) !=
            (NV_INIT_FLAG_GPU_STATE | NV_INIT_FLAG_GPU_STATE_LOAD)) {
        status = NV_ERR_INVALID_STATE; goto publish;
    }
    if (!__atomic_compare_exchange_n(&protocolClaim, &expected, 1U, NV_FALSE,
            __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE)) {
        status = NV_ERR_STATE_IN_USE; goto publish;
    }
    protocolIdentity.owner = identity.owner;
    protocolIdentity.nv = nv;
    protocolIdentity.privateState = privateState;
    protocolIdentity.gpu = gpu;
    protocolIdentity.generation = before.generation;
    protocolIdentity.masterThread = before.masterThread;
    evidence.claimed = NV_TRUE;
    evidence.owner = identity.owner;
    evidence.nv = nv;
    evidence.privateState = privateState;
    evidence.gpu = gpu;
    evidence.generation = before.generation;
    evidence.masterThread = before.masterThread;

    NV_ENTER_RM_RUNTIME(stack, fp);
    threadStateInit(&threadState, THREAD_STATE_FLAGS_NONE);
    status = s540GspCancellationBeginCleanupState(nv);
    if (status != NV_OK) goto runtime_done;
    status = s540GspCancellationCheckState(nv);
    if (status != NV_OK) goto runtime_done;
    /* Match the ordinary original wrapper's write-API then GPU lock order. */
    status = rmapiLockAcquire(API_LOCK_FLAGS_NONE, RM_LOCK_MODULES_DESTROY);
    if (status != NV_OK) goto runtime_done;
    status = rmGpuLocksAcquire(GPUS_LOCK_FLAGS_NONE, RM_LOCK_MODULES_DESTROY);
    if (status != NV_OK) goto api_done;
    status = s540FirstTxnGetSnapshot(nv, &after);
    if (status == NV_OK && after.firstStatus != NV_OK) status = after.firstStatus;
    if (status == NV_OK && (after.generation != protocolIdentity.generation ||
        after.masterThread != protocolIdentity.masterThread ||
        after.phase != S540_FIRST_OP || after.originalInFlight ||
        !after.originalReturned || !after.originalExitReady || after.cleanupRequested ||
        after.inFlightFreePermits || !sameOriginalIdentity(nv)))
        status = NV_ERR_INVALID_STATE;
    if (status == NV_OK) {
        S540FirstTxnHostIdentity current = {0};
        status = s540FirstTxnHostCaptureAllocation(&current);
        if (status == NV_OK && (current.owner != protocolIdentity.owner ||
            current.generation != protocolIdentity.generation))
            status = NV_ERR_INVALID_STATE;
    }
    if (status == NV_OK) status = s540GspCancellationCheckState(nv);
    if (status == NV_OK) {
        evidence.originalEntered = NV_TRUE;
        /* This exact frozen original function unloads state and invokes the
         * GSP shutdown protocol; it does not destroy the GPU or reclaim pages. */
        evidence.originalReturnStatus = gpuEnterShutdown(protocolIdentity.gpu);
        evidence.originalReturned = NV_TRUE;
        evidence.protocolCompleted = evidence.originalReturnStatus == NV_OK;
        status = evidence.originalReturnStatus;
        if (status == NV_OK && !sameOriginalIdentity(nv)) status = NV_ERR_INVALID_STATE;
    }
    /* Record the real failed operation before token release can dispatch
     * deferred CPU work or outer cleanup. Domain/site are diagnostics only. */
    if (status != NV_OK) s540FirstTxnObserveServiceRefusal(0x534450U, 1U, status);
    releaseStatus = rmGpuLocksRelease(GPUS_LOCK_FLAGS_NONE, NULL);
    if (releaseStatus != NV_OK) {
        evidence.unlockStatus = releaseStatus;
        if (status == NV_OK) status = releaseStatus;
        s540FirstTxnObserveServiceRefusal(0x534450U, 2U, releaseStatus);
    }
api_done:
    if (status != NV_OK) s540FirstTxnObserveServiceRefusal(0x534450U, 3U, status);
    rmapiLockRelease();
runtime_done:
    if (status != NV_OK) s540FirstTxnObserveServiceRefusal(0x534450U, 3U, status);
    threadStateFree(&threadState, THREAD_STATE_FLAGS_NONE);
    NV_EXIT_RM_RUNTIME(stack, fp);
    /* Preserve real original return separately when a later service/lock
     * refusal invalidates the apparent success of the outer operation. */
    releaseStatus = s540FirstTxnOriginalLocksReleased(nv);
    if (releaseStatus != NV_OK && evidence.unlockStatus == NV_OK)
        evidence.unlockStatus = releaseStatus;
    if (status == NV_OK && releaseStatus != NV_OK) status = releaseStatus;
    releaseStatus = s540FirstTxnGetSnapshot(nv, &after);
    if (status == NV_OK && releaseStatus != NV_OK) status = releaseStatus;
    if (status == NV_OK && (after.generation != protocolIdentity.generation ||
        after.masterThread != protocolIdentity.masterThread)) status = NV_ERR_INVALID_STATE;
    if (status == NV_OK && after.firstStatus != NV_OK) status = after.firstStatus;
    if (status != NV_OK) s540FirstTxnObserveServiceRefusal(0x534450U, 4U, status);
publish:
    evidence.operationStatus = status;
    *out = evidence;
    return status;
}
