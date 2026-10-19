/* SPDX-License-Identifier: MIT */
#ifndef S540_NVIDIA_GSP_CONTEXT_H
#define S540_NVIDIA_GSP_CONTEXT_H
#include "../../nvidia-os-adapter/upstream/include/nvtypes.h"
#include "../../nvidia-os-adapter/upstream/include/nvstatus.h"
#include "S540NvidiaGspDmaStop.h"
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
    // Complete bounded console enumeration found positive Intel ownership,
    // no bound-NVIDIA console and no unresolved console owner.
    NvBool nvidiaConsoleExcluded;
} S540GspDeviceFacts;
typedef struct S540GspContextSnapshot {
    NvBool created, eventLocks, privateState, adapterAttempted;
    NvBool adapterInitialized, adapterDisabled, adapterShutdown;
    NvBool workStopped, quiescent, quarantined;
    NvBool originalReleased, finalDetach;
    NvU32 interruptsHandled, lockedBottomHalves, unlockedBottomHalves;
} S540GspContextSnapshot;
// Registered by the externally serialized operational owner before attaching
// any firmware, timer, platform or transport binding. The callback performs
// actual unbind operations while the original state and metadata still live.
// A refusal preserves the context and may be retried; it is not a detached
// Boolean supplied by the caller. Successful callbacks must be idempotent.
typedef struct S540GspContextDetacher {
    void *owner;
    NV_STATUS (*detach)(void *owner, void *state, void *dmaDevice);
} S540GspContextDetacher;
// On cleanup failure, out receives the quarantined owner even with an error;
// retain it. Ordinary validation/allocation failures leave out unchanged.
NV_STATUS s540GspContextCreate(const S540GspDeviceFacts *, S540GspContext **out);
void *s540GspContextState(S540GspContext *);
void *s540GspContextDmaDevice(S540GspContext *);
void *s540GspContextMainStack(S540GspContext *);
NV_STATUS s540GspContextSetPciHandle(S540GspContext *, void *);
NV_STATUS s540GspContextSetDetacher(S540GspContext *, const S540GspContextDetacher *);
NV_STATUS s540GspContextPrepare(S540GspContext *);
NV_STATUS s540GspContextInitializeAdapter(S540GspContext *);
// Original disable must run while IRQ, queues, MMIO, DMA and power remain live.
NV_STATUS s540GspContextDisableAdapter(S540GspContext *);
// The caller stops/drains interrupt producers before original shutdown.
NV_STATUS s540GspContextShutdownAdapter(S540GspContext *, NvBool irqQuiescent);
// Stop timer/work producers and release original private/event state. Keep
// nv_state, the metadata owner and bound global queue alive for actual external
// unbind operations. Calling this again after success is harmless.
NV_STATUS s540GspContextReleaseOriginalState(S540GspContext *, NvBool irqQuiescent);
// Destroy refuses incomplete teardown and preserves all context storage.
// With a registered detacher, it releases original state, executes real
// detach operations, verifies that no timer binding remains, then frees the
// retained context. Without one, only a never-prepared context can be freed.
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
