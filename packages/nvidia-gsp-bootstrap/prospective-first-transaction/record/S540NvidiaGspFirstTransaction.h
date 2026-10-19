/* SPDX-License-Identifier: MIT; isolated first-transaction implementation. */
#ifndef S540_NVIDIA_GSP_FIRST_TRANSACTION_H
#define S540_NVIDIA_GSP_FIRST_TRANSACTION_H
#include "deps/Participants.h"
#ifdef __cplusplus
extern "C" {
#endif
typedef NvU64 S540FirstTxnLease;
enum S540FirstTxnPhase { S540_FIRST_UNBOUND=0, S540_FIRST_OP=1,
    S540_FIRST_CLOSING=2, S540_FIRST_DRAINING=3, S540_FIRST_SEALED=4,
    S540_FIRST_DESTRUCTIVE=5, S540_FIRST_RETAINED=6 };
typedef struct S540FirstTxnServiceCounters {
    NvBool hostInitialized, cryptoOverflow;
    NvU64 hostUnavailable, hostInvalidFrees, memoryUnavailableEver,
        memoryViolationsEver, cryptoUnavailable, cryptoMaskLow, cryptoMaskHigh;
} S540FirstTxnServiceCounters;
typedef struct S540FirstTxnSnapshot {
    NvU32 phase, firstStatus, firstSite;
    NvU64 generation, masterThread, sealSerial;
    NvU32 workAccepted, workOriginalReturned, workActionReturned,
        directAccepted, directOriginalReturned, directActionReturned,
        liveWork, liveDirect, eventBorrowers, ownerCount, eventCount,
        unknownRetainedObjects, retainedOriginalAllocations, inFlightFreePermits;
    NvBool originalInFlight, originalExitReady, originalReturned,
        cleanupRequested, firmwareRetained;
    const void *firmware[3];
    S540FirstTxnServiceCounters counters;
} S540FirstTxnSnapshot;
/* Begin BEFORE first original global allocation. Attach exact nv once later;
 * owner/generation on already captured allocations are never retagged. */
NV_STATUS s540FirstTxnBeginOwner(const void *actualRetainedOwner);
NV_STATUS s540FirstTxnBind(const void *exactNv, S540GspCancellationToken);
NV_STATUS s540FirstTxnOriginalEnter(const void *exactNv);
NV_STATUS s540FirstTxnRequestDeferredCleanup(const void *exactNv, NV_STATUS);
NV_STATUS s540FirstTxnRetainInitFirmware(const void *exactNv,
    const void *firmware, const void *log, const void *ucodes);
/* Evidence-only retirement: never authorizes cleanup or publishes object fields. */
NV_STATUS s540FirstTxnRetainOriginalAllocation(const void *exactNv,
    const void *allocation, const void *mapping, const void *mappingPriv);
NV_STATUS s540FirstTxnOriginalExitReady(const void *exactNv, NV_STATUS);
NV_STATUS s540FirstTxnOriginalWrapperReturned(const void *exactNv);
NV_STATUS s540FirstTxnBeginClosing(const void *exactNv);
NV_STATUS s540FirstTxnSeal(const void *exactNv);
NV_STATUS s540FirstTxnBeginDestructive(const void *exactNv);
NV_STATUS s540FirstTxnCheckBeforeDestroy(const void *exactNv);
NV_STATUS s540FirstTxnCheckBeforeDeleteObject(const void *originalObject);
NV_STATUS s540FirstTxnRegisterOwner(const void *exactNv, const void *originalObject);
NV_STATUS s540FirstTxnEventConstruct(const void *exactNv, const void *originalEvent,
    const void *timerIdentity, S540FirstTxnLease *eventGeneration);
NV_STATUS s540FirstTxnEventCanDestroy(const void *exactNv, const void *originalEvent,
    const void *timerIdentity, S540FirstTxnLease eventGeneration);
NV_STATUS s540FirstTxnEventDestroyed(const void *exactNv, const void *originalEvent,
    const void *timerIdentity, S540FirstTxnLease eventGeneration);
/* Real service hook calls; no caller phase/authorization Boolean. Work data is
 * inspected only at admission/entry, never after original done may free it. */
NV_STATUS s540FirstTxnWorkAdmit(const void *exactNv, const void *queueIdentity,
    const void *originalWork, S540FirstTxnLease *out);
NV_STATUS s540FirstTxnWorkRejected(const void *exactNv, const void *queueIdentity,
    const void *originalWork, NV_STATUS);
NV_STATUS s540FirstTxnWorkEnter(const void *exactNv, const void *queueIdentity,
    const void *originalWork, S540FirstTxnLease);
NV_STATUS s540FirstTxnWorkOriginalReturned(const void *exactNv, NV_STATUS);
NV_STATUS s540FirstTxnWorkReturned(const void *exactNv, const void *queueIdentity,
    S540FirstTxnLease);
NV_STATUS s540FirstTxnWorkRetain(const void *exactNv, const void *queueIdentity,
    S540FirstTxnLease, NV_STATUS);
NV_STATUS s540FirstTxnDirectAdmit(const void *exactNv, const void *timerIdentity,
    const void *originalEvent, S540FirstTxnLease eventGeneration,
    NvU64 armGeneration, S540FirstTxnLease *out);
NV_STATUS s540FirstTxnDirectEnter(const void *exactNv, const void *timerIdentity,
    S540FirstTxnLease);
NV_STATUS s540FirstTxnDirectOriginalReturned(const void *exactNv, NV_STATUS);
NV_STATUS s540FirstTxnDirectReturned(const void *exactNv, const void *timerIdentity,
    S540FirstTxnLease);
NV_STATUS s540FirstTxnDirectRetain(const void *exactNv, const void *timerIdentity,
    S540FirstTxnLease, NV_STATUS);
NV_STATUS s540FirstTxnDirectCancelled(const void *exactNv, const void *timerIdentity,
    S540FirstTxnLease);
/* Actual source refusal producer only; domain/symbol are diagnostics, never
 * authorization. Atomic, no allocator/service/RM lock, safe on foreign/IRQ. */
void s540FirstTxnObserveServiceRefusal(NvU32 domain, NvU32 symbol, NV_STATUS status);
NV_STATUS s540FirstTxnGetSnapshot(const void *exactNv, S540FirstTxnSnapshot *);
/* Counter-free Host path: no HostSnapshot, allocator guard or RM lock. */
typedef struct S540FirstTxnHostIdentity { const void *owner; NvU64 generation; } S540FirstTxnHostIdentity;
typedef NvU64 S540FirstTxnHostFreePermit;
NV_STATUS s540FirstTxnHostCaptureAllocation(S540FirstTxnHostIdentity *);
NV_STATUS s540FirstTxnHostAcquireFree(const S540FirstTxnHostIdentity *, S540FirstTxnHostFreePermit *);
NV_STATUS s540FirstTxnHostCompleteFree(const S540FirstTxnHostIdentity *, S540FirstTxnHostFreePermit);
/* Internal fixed original adapters: implementation reads actual nv_work_item,
 * TMR_EVENT/NVOC metadata. Never pass a caller enum as callback authorization.
 * Only immutable link-time rows authorize known original addresses/types. */
enum { S540_FIRST_DESC_WORK=1, S540_FIRST_DESC_EVENT=2, S540_FIRST_DESC_OWNER=3 };
enum { S540_FIRST_ESSENTIAL_RUN_OR_RETAIN=1 };
typedef struct S540FirstTxnOriginalDescriptor {
    NvU32 role, policy, flagsMask, flagsValue;
    NvUPtr callback, ownerClass;
    NvBool eventArgument;
} S540FirstTxnOriginalDescriptor;
typedef struct S540FirstTxnOriginalWork {
    NvUPtr callback; NvU32 flags;
    const void *parameter;
} S540FirstTxnOriginalWork;
typedef struct S540FirstTxnOriginalEvent {
    NvUPtr callback; const void *owner;
} S540FirstTxnOriginalEvent;
extern const S540FirstTxnOriginalDescriptor s540FirstTxnOriginalDescriptors[];
extern const NvU32 s540FirstTxnOriginalDescriptorCount;
NV_STATUS s540FirstTxnInspectOriginalWork(const void *, S540FirstTxnOriginalWork *);
NV_STATUS s540FirstTxnInspectOriginalEvent(const void *, S540FirstTxnOriginalEvent *);
NV_STATUS s540FirstTxnInspectOriginalOwner(const void *, NvUPtr *classIdentity);
/* Genuine original bridge probes, supplied by the original-source owner. */
NV_STATUS s540FirstTxnOriginalLocksReleased(const void *exactNv);
NV_STATUS s540FirstTxnOriginalReadServiceCounters(const void *exactNv,
    S540FirstTxnServiceCounters *);
/* Genuine service evidence, supplied by real hook copies. ServiceContext is a
 * pull query of actual guarded dispatch, never a caller readiness setter. */
enum { S540_FIRST_SERVICE_ADMIT=1, S540_FIRST_SERVICE_ENTER=2,
    S540_FIRST_SERVICE_RETURNED=3, S540_FIRST_SERVICE_CANCELLED=4, S540_FIRST_SERVICE_DESTROYED=5 };
typedef struct S540FirstTxnServiceContext {
    NvU32 stage; NvU64 thread, generation;
    const void *data;
} S540FirstTxnServiceContext;
NV_STATUS s540FirstTxnServicesReadQueueContext(const void *queue,
    S540FirstTxnServiceContext *);
NV_STATUS s540FirstTxnServicesReadTimerContext(const void *timer,
    S540FirstTxnServiceContext *);
NV_STATUS s540FirstTxnServicesSealAndDrain(const void *exactNv, NvU64 generation);
NV_STATUS s540FirstTxnServicesValidateRetired(const void *exactNv, NvU64 generation);
#ifdef __cplusplus
}
#endif
#endif
