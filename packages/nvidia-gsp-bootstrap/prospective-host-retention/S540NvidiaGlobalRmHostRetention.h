/* SPDX-License-Identifier: MIT; isolated prospective Host retention. */
#ifndef S540_NVIDIA_GLOBAL_RM_HOST_RETENTION_H
#define S540_NVIDIA_GLOBAL_RM_HOST_RETENTION_H
#include "S540NvidiaGspFirstTransaction.h"
#ifdef __cplusplus
extern "C" {
#endif
typedef struct S540GlobalRmHostRetentionSnapshot {
    NvU32 format, retiredAllocations, pendingAllocations, pendingFrees, releasedPendingCompletions, acquireFailures,
        completionFailures, firstStatus, preexistingOriginalAllocations;
    NvU64 retiredBytes, taggedAllocations, unassociatedAllocations;
} S540GlobalRmHostRetentionSnapshot;
typedef struct S540GlobalRmHostAllocationSnapshot {
    S540FirstTxnHostIdentity identity;
    NvU64 allocationSerial, bytes;
    NvBool original, retired, pendingFree;
} S540GlobalRmHostAllocationSnapshot;
/* A pull query only. Outer startup serialization must hold across this cold
 * preflight and BeginOwner; no old allocation is retagged or adopted. */
NV_STATUS s540GlobalRmHostRetentionPreflight(void);
void s540GlobalRmHostRetentionSnapshot(S540GlobalRmHostRetentionSnapshot *);
NV_STATUS s540GlobalRmHostRetentionInspect(const void *, S540GlobalRmHostAllocationSnapshot *);
#ifdef __cplusplus
}
#if !defined(KERNEL)
namespace S540HostRetentionNative {
// Scheduling observer around real std::free. Test-only; no substitute backing.
void observePhysicalFree(void (*)(NvU32 stage, const void *pointer, NvU64 bytes,
    const S540FirstTxnHostIdentity *, S540FirstTxnHostFreePermit));
}
#endif
#endif
#endif
