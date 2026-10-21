/* SPDX-License-Identifier: MIT */
/* Internal opt-in bridge compiled with the complete original NVIDIA profile.
 * It changes neither adapter lifecycle nor the frozen original source. */
#define NVOC_GPU_H_PRIVATE_ACCESS_ALLOWED
#define NVOC_INTR_H_PRIVATE_ACCESS_ALLOWED
#include "nv.h"
#include "nv-priv.h"
#include "osapi.h"
#include "gpu/gpu.h"
#include "gpu/intr/intr.h"
#include "gpu/timer/objtmr.h"
#include "core/system.h"
#include "core/locks.h"
#include "core/thread_state.h"
#include "S540NvidiaGspFirstTransaction.h"
#include "S540ProspectiveRmLockOwnership.h"
#include "S540NvidiaIrqOriginal.h"
#include "../S540NvidiaIrqClosure.h"

#if !defined(S540_NVIDIA_IRQ_CALLBACK_CLOSURE) || S540_NVIDIA_IRQ_CALLBACK_CLOSURE != 1
#error "Explicit isolated IRQ/callback composition required"
#endif

static NV_STATUS masterIdentity(nv_state_t *nv, S540FirstTxnGlobalSnapshot *out)
{
    S540FirstTxnGlobalSnapshot epoch;
    NV_STATUS status;
    if (nv == NULL || out == NULL) return NV_ERR_INVALID_ARGUMENT;
    /* The strong record authenticates the immutable actual owner, generation,
     * ordinary master and OP phase. A diagnostic snapshot cannot replace it. */
    status = s540FirstTxnGlobalReadMaster(&epoch);
    if (status != NV_OK) return status;
    if (epoch.nv != nv || epoch.owner == NULL || !epoch.generation ||
        !epoch.masterThread || epoch.firstStatus || !epoch.validated ||
        epoch.state != S540_FIRST_GLOBAL_READY)
        return NV_ERR_INVALID_STATE;
    *out = epoch;
    return NV_OK;
}

static NV_STATUS readLocks(const S540FirstTxnGlobalSnapshot *epoch,
    S540ProspectiveRmLockOwnership *out)
{
    NV_STATUS status = s540ProspectiveReadOriginalLockOwnership(SYS_GET_INSTANCE(), out);
    if (status != NV_OK) return status;
    return out->thread == epoch->masterThread ? NV_OK : NV_ERR_INVALID_STATE;
}

static NV_STATUS operation(nvidia_stack_t *sp, nv_state_t *nv, NvBool mask)
{
    S540FirstTxnGlobalSnapshot epoch, recheck;
    S540ProspectiveRmLockOwnership locks;
    OBJGPU *gpu;
    Intr *intr;
    NV_STATUS status, released;
    NvBool apiLocked = NV_FALSE, gpuLocked = NV_FALSE;
    THREAD_STATE_NODE threadState;
    void *fp;
    if (sp == NULL) return NV_ERR_INVALID_ARGUMENT;
    status = masterIdentity(nv, &epoch);
    if (status != NV_OK) return status;
    /* Original GPU lock ownership may be transferred by ISR/DPC paths. The
     * complete lock reader requires their genuine backend exclusion, beyond
     * an ordinary current thread and a retained original-state lifetime. */
    status = s540FirstTxnIrqValidateSoftwareDrained();
    if (status != NV_OK) return status;
    status = readLocks(&epoch, &locks);
    if (status != NV_OK) return status;
    if (locks.apiOwned || locks.perGpuMask || locks.allocationOwned)
        return NV_ERR_INVALID_LOCK_STATE;
    status = rm_acquire_api_lock(sp);
    if (status != NV_OK) return status;
    apiLocked = NV_TRUE;
    /* Reading original GPU/private state starts only after API ownership.
     * The retained outer transaction lifetime excludes its destruction. */
    gpu = NV_GET_NV_PRIV_PGPU(nv);
    if (gpu == NULL || NV_GET_NV_STATE(gpu) != nv || gpu->gpuInstance >= 32) {
        status = NV_ERR_INVALID_STATE;
        goto done;
    }
    status = rm_acquire_gpu_lock(sp, nv);
    if (status != NV_OK) goto done;
    gpuLocked = NV_TRUE;
    status = masterIdentity(nv, &recheck);
    if (status != NV_OK) goto done;
    if (recheck.owner != epoch.owner || recheck.generation != epoch.generation ||
        recheck.masterThread != epoch.masterThread) {
        status = NV_ERR_INVALID_STATE;
        goto done;
    }
    status = readLocks(&epoch, &locks);
    if (status != NV_OK) goto done;
    if (!locks.apiOwned || locks.allocationOwned ||
        locks.perGpuMask != (1U << gpu->gpuInstance) ||
        !rmDeviceGpuLockIsOwner(gpu->gpuInstance)) {
        status = NV_ERR_INVALID_LOCK_STATE;
        goto done;
    }
    /* The exact basic-lock profile has no legacy RM semaphore. Its complete
     * ownership reader independently requires SYS.pSema == NULL; the generated
     * osIsRmSemaOwner literal true is never treated as a lock receipt. */
    NV_ENTER_RM_RUNTIME(sp, fp);
    threadStateInit(&threadState, THREAD_STATE_FLAGS_NONE);
    if (mask) {
        intr = GPU_GET_INTR(gpu);
        if (intr == NULL || !intr->halIntrEnabled ||
            gpu->getProperty(gpu, PDB_PROP_GPU_TEGRA_SOC_NVDISPLAY)) {
            status = NV_ERR_NOT_SUPPORTED;
        } else {
            /* Persist the logical source disable BEFORE the genuine HAL mask.
             * GPU lock release may call osEnableInterrupts; it must read the
             * disabled value, so it cannot restore the old enable selection.
             * A frozen HAL refuses intrSetIntrEn, hence the refusal above. */
            intrSetIntrEn(intr, INTERRUPT_TYPE_DISABLED);
            if (intrGetIntrEn(intr) != INTERRUPT_TYPE_DISABLED) {
                status = NV_ERR_INVALID_STATE;
            } else {
                osDisableInterrupts(gpu, NV_FALSE);
                status = intrGetIntrEn(intr) == INTERRUPT_TYPE_DISABLED
                    ? NV_OK : NV_ERR_INVALID_STATE;
            }
        }
    } else {
        /* This is the original plain 1Hz list path, also used by original
         * _gpuLocksReleaseHandleDeferredWork. No TMR_EVENT/OWNER is invented. */
        osRunQueued1HzCallbacksUnderLock(gpu);
        status = gpu->bCallbackQueued ? NV_ERR_BUSY_RETRY : NV_OK;
    }
    threadStateFree(&threadState, THREAD_STATE_FLAGS_NONE);
    NV_EXIT_RM_RUNTIME(sp, fp);
done:
    if (gpuLocked) {
        released = rm_release_gpu_lock(sp, nv);
        if (released != NV_OK) status = released;
    }
    if (apiLocked) {
        released = rm_release_api_lock(sp);
        if (released != NV_OK) status = released;
    }
    if (status == NV_OK)
        status = s540ProspectiveOriginalCurrentThreadLocksReleased(SYS_GET_INSTANCE());
    return status;
}

NV_STATUS s540FirstTxnIrqMaskHardware(nvidia_stack_t *sp, nv_state_t *nv)
{
    return operation(sp, nv, NV_TRUE);
}

NV_STATUS s540FirstTxnDrainQueued1Hz(nvidia_stack_t *sp, nv_state_t *nv)
{
    return operation(sp, nv, NV_FALSE);
}
