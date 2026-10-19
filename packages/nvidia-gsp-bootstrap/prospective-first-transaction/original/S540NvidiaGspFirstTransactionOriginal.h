/* SPDX-License-Identifier: MIT */
#ifndef S540_NVIDIA_GSP_FIRST_TRANSACTION_ORIGINAL_H
#define S540_NVIDIA_GSP_FIRST_TRANSACTION_ORIGINAL_H
#include "../record/S540NvidiaGspFirstTransaction.h"
#include "nvoc/prelude.h"
struct OBJGPU;
NV_STATUS s540FirstTxnCheckBeforeDestroyGpu(struct OBJGPU *);
NV_STATUS s540FirstTxnRequestDeferredCleanupGpu(struct OBJGPU *, NV_STATUS);
NV_STATUS s540FirstTxnRetainOriginalAllocationGpu(struct OBJGPU *, const void *, const void *, const void *);
NV_STATUS s540FirstTxnObjDeleteChecked(Dynamic *);
/* Deliberately narrow probe for controls; never substitutes for the generic
 * full lock-capability predicate consumed by the transaction record. */
NV_STATUS s540FirstTxnOriginalApiGpuLocksReleased(const void *);
/* Canonical policy bits are decoded from each actual original bitfield.
 * They are not a new layout cast or a caller authorization enum. */
enum {
    S540_FIRST_WORK_DONT_FREE=1U, S540_FIRST_WORK_FALLBACK=2U,
    S540_FIRST_WORK_REQUIRES_GPU=4U, S540_FIRST_WORK_SEMA=8U,
    S540_FIRST_WORK_API_WRITE=16U, S540_FIRST_WORK_API_READ=32U,
    S540_FIRST_WORK_ALL_GPUS=64U, S540_FIRST_WORK_GROUP_DEVICE=128U,
    S540_FIRST_WORK_GROUP_SUBDEVICE=256U, S540_FIRST_WORK_FULL_SANITY=512U,
    S540_FIRST_WORK_DROP_FLUSH=1024U, S540_FIRST_WORK_EXPANDED=2048U,
    S540_FIRST_WORK_ALL_KNOWN=4095U
};
#endif
