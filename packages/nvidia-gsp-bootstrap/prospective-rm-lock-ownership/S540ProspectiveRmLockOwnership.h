/* SPDX-License-Identifier: MIT */
#ifndef S540_PROSPECTIVE_RM_LOCK_OWNERSHIP_H
#define S540_PROSPECTIVE_RM_LOCK_OWNERSHIP_H
#include "nvtypes.h"
#include "nvstatus.h"
#include "rmconfig.h"
#if !defined(S540_NVIDIA_NO_LEGACY_RM_SEMAPHORE) || S540_NVIDIA_NO_LEGACY_RM_SEMAPHORE != 1
#error "Explicit sealed original no-legacy-RM-semaphore profile required"
#endif
#if RMCFG_FEATURE_RM_BASIC_LOCK_MODEL != 1
#error "Legacy RM semaphore exclusion requires the exact basic lock model"
#endif
struct OBJSYS;

typedef struct S540ProspectiveRmLockOwnership {
    NvU64 thread;
    NvU32 perGpuMask;
    NvBool apiOwned;
    NvBool allocationOwned;
} S540ProspectiveRmLockOwnership;

/* Internal original-TU probes. Call only through the complete query below. */
NV_STATUS s540ProspectiveOriginalApiOwnership(NvBool *);
NV_STATUS s540ProspectiveOriginalGpuOwnership(NvU32 *, NvBool *);

/* Caller must already hold the serialized, completed global-RM lifetime epoch
 * excluding global teardown and ISR/DPC owner transfers. These functions do
 * not acquire that epoch or authenticate a firstTxn entry. They observe ONLY
 * this ordinary thread's API, per-GPU and GPU-allocation ownership. A free
 * result cannot authorize foreign callback retirement or general cleanup.
 * All outputs remain unchanged when a read is refused. */
NV_STATUS s540ProspectiveReadOriginalLockOwnership(const struct OBJSYS *,
    S540ProspectiveRmLockOwnership *);
NV_STATUS s540ProspectiveOriginalCurrentThreadLocksReleased(const struct OBJSYS *);
#endif
