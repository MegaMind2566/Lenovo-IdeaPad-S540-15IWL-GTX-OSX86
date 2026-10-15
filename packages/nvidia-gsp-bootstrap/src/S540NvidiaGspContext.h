/* SPDX-License-Identifier: MIT */
#ifndef S540_NVIDIA_GSP_CONTEXT_H
#define S540_NVIDIA_GSP_CONTEXT_H
#include "../../nvidia-os-adapter/upstream/include/nvtypes.h"
#include "../../nvidia-os-adapter/upstream/include/nvstatus.h"
#ifdef __cplusplus
extern "C" {
#endif
typedef struct S540GspContext S540GspContext;
typedef struct S540GspBar { NvU64 physical, bytes; NvU32 offset; } S540GspBar;
typedef struct S540GspDeviceFacts {
    NvU32 format;
    NvU32 segment;
    NvU8 bus, slot, function;
    NvU16 vendor, device, subsystemVendor, subsystemDevice;
    NvU32 configuration[16];
    S540GspBar bars[3];
    void *pciHandle;
    // Each bit is evidence collected from the actual retained provider.
    NvBool segmentKnown, pciConfigurationRead, barsVerified, poweredD0;
    NvBool intelConsoleVerified, noCoherentGpuMemoryProfile;
} S540GspDeviceFacts;
typedef struct S540GspContextSnapshot {
    NvBool created, eventLocks, privateState, adapterAttempted;
    NvBool adapterInitialized, adapterDisabled, adapterShutdown;
    NvBool workStopped, quiescent, quarantined;
    NvU32 interruptsHandled, lockedBottomHalves, unlockedBottomHalves;
} S540GspContextSnapshot;
// On cleanup failure, out receives the quarantined owner even with an error;
// retain it. Ordinary validation/allocation failures leave out unchanged.
NV_STATUS s540GspContextCreate(const S540GspDeviceFacts *, S540GspContext **out);
void *s540GspContextState(S540GspContext *);
void *s540GspContextDmaDevice(S540GspContext *);
void *s540GspContextMainStack(S540GspContext *);
NV_STATUS s540GspContextSetPciHandle(S540GspContext *, void *);
NV_STATUS s540GspContextPrepare(S540GspContext *);
NV_STATUS s540GspContextInitializeAdapter(S540GspContext *);
// Original disable must run while IRQ, queues, MMIO, DMA and power remain live.
NV_STATUS s540GspContextDisableAdapter(S540GspContext *);
// The caller stops/drains interrupt producers before original shutdown.
NV_STATUS s540GspContextShutdownAdapter(S540GspContext *, NvBool irqQuiescent);
// Destroy refuses incomplete teardown and preserves all context storage.
NV_STATUS s540GspContextDestroy(S540GspContext *, NvBool irqQuiescent,
                               S540GspContextSnapshot *finalSnapshot);
void s540GspContextSnapshot(S540GspContext *, S540GspContextSnapshot *);
NvBool s540GspContextInterruptTop(S540GspContext *, NvBool *, NvBool *);
void s540GspContextLockedBottomHalf(S540GspContext *);
void s540GspContextUnlockedBottomHalf(S540GspContext *);
#ifdef __cplusplus
}
#endif
#endif
