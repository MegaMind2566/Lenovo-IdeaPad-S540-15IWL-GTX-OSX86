/* SPDX-License-Identifier: MIT */
#include "core/core.h"
#include "core/system.h"
#include "os/os.h"
#include "S540ProspectiveRmLockOwnership.h"
#include "../../nvidia-global-rm/src/S540NvidiaGlobalRm.h"
#include "../../nvidia-darwin-services/src/S540NvidiaDarwinServices.h"

#if !defined(S540_NVIDIA_NO_LEGACY_RM_SEMAPHORE) || S540_NVIDIA_NO_LEGACY_RM_SEMAPHORE != 1
#error "Explicit sealed original no-legacy-RM-semaphore profile required"
#endif
#if RMCFG_FEATURE_RM_BASIC_LOCK_MODEL != 1
#error "Legacy RM semaphore exclusion requires the exact basic lock model"
#endif

NV_STATUS s540ProspectiveReadOriginalLockOwnership(const struct OBJSYS *exactSys,
    S540ProspectiveRmLockOwnership *out)
{
    S540ProspectiveRmLockOwnership view = {0};
    NV_STATUS status;
    if (exactSys == NULL || out == NULL) return NV_ERR_INVALID_ARGUMENT;
    if (!s540Darwin_os_semaphore_may_sleep()) return NV_ERR_INVALID_REQUEST;
    /* These are actual lifecycle observations, never an outer-epoch substitute.
     * g_pSys is published before locks initialize; running stays true during
     * RmShutdownRm. The caller's live epoch remains mandatory. */
    if (!s540GlobalRmIsInitialized() || !portIsInitialized() ||
        SYS_GET_INSTANCE() != exactSys) return NV_ERR_NOT_READY;
    if (exactSys->PDB_PROP_SYS_DESTRUCTING || exactSys->pSema != NULL)
        return NV_ERR_INVALID_STATE;
    status = osGetCurrentThread(&view.thread);
    if (status != NV_OK) return status;
    if (view.thread == 0 || view.thread == ~(NvU64)0) return NV_ERR_INVALID_STATE;
    /* TLS takes its own state lock: read it before the GPU state spinlock. */
    status = s540ProspectiveOriginalApiOwnership(&view.apiOwned);
    if (status != NV_OK) return status;
    status = s540ProspectiveOriginalGpuOwnership(&view.perGpuMask, &view.allocationOwned);
    if (status != NV_OK) return status;
    *out = view;
    return NV_OK;
}

NV_STATUS s540ProspectiveOriginalCurrentThreadLocksReleased(const struct OBJSYS *exactSys)
{
    S540ProspectiveRmLockOwnership view;
    NV_STATUS status = s540ProspectiveReadOriginalLockOwnership(exactSys, &view);
    if (status != NV_OK) return status;
    return view.apiOwned || view.perGpuMask || view.allocationOwned
        ? NV_ERR_INVALID_LOCK_STATE : NV_OK;
}
