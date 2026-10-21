/* SPDX-License-Identifier: MIT */
#ifndef S540_NVIDIA_ALLOCATOR_EPOCH_H
#define S540_NVIDIA_ALLOCATOR_EPOCH_H
#include "nvtypes.h"
#include "nvstatus.h"
typedef struct {
    NvU32 portableBusy, memoryBusy, portableReady, memoryReady;
    NvU64 refusedInitializations, refusedShutdowns, invalidCompletions;
    NvU64 initializerThread;
} S540AllocatorEpochSnapshot;
NV_STATUS s540AllocatorPortableBegin(void);
NV_STATUS s540AllocatorPortableEnd(NV_STATUS originalStatus);
NV_STATUS s540AllocatorMemoryBegin(void);
NV_STATUS s540AllocatorMemoryEnd(NV_STATUS originalStatus);
NV_STATUS s540AllocatorPortableRelease(NvU32 actualReferenceCount);
NV_STATUS s540AllocatorMemoryShutdown(void);
NV_STATUS s540AllocatorGlobalUse(void);
void s540AllocatorTrackingRefused(void);
NvBool s540AllocatorPortableVisible(void);
void s540AllocatorEpochSnapshot(S540AllocatorEpochSnapshot *out);
#endif
