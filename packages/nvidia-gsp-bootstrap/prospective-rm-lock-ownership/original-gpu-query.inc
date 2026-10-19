/* SPDX-License-Identifier: MIT */
/* Appended only to the sealed original locks.c, where the real state and
 * _rmGpuAllocLockIsOwner are visible. No new lock or ownership field. */
#include "S540ProspectiveRmLockOwnership.h"
NV_STATUS s540ProspectiveOriginalGpuOwnership(NvU32 *perGpuMask, NvBool *allocationOwned)
{
    NvU32 mask;
    NvBool allocation;
    if (perGpuMask == NULL || allocationOwned == NULL) return NV_ERR_INVALID_ARGUMENT;
    if (rmGpuLockInfo.pLock == NULL || rmGpuLockInfo.gpuAllocLock.pWaitSema == NULL)
        return NV_ERR_NOT_READY;
    /* The outer lifetime/producer epoch is required: this state lock does not
     * serialize all pending-DPC owner transfers or concurrent destruction. */
    portSyncSpinlockAcquire(rmGpuLockInfo.pLock);
    mask = rmGpuLocksGetOwnedMask();
    allocation = _rmGpuAllocLockIsOwner();
    portSyncSpinlockRelease(rmGpuLockInfo.pLock);
    *perGpuMask = mask;
    *allocationOwned = allocation;
    return NV_OK;
}
