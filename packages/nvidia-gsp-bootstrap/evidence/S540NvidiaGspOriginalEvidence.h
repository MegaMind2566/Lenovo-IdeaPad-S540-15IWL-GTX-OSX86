/* SPDX-License-Identifier: MIT */
#ifndef S540_NVIDIA_GSP_ORIGINAL_EVIDENCE_H
#define S540_NVIDIA_GSP_ORIGINAL_EVIDENCE_H

/* Include the pinned original nv.h before this private integration header. */
#ifndef _NV_H_
#error "Include the pinned original nv.h before S540NvidiaGspOriginalEvidence.h"
#endif

#ifdef __cplusplus
extern "C" {
#endif

typedef struct S540GspOriginalEvidence {
    NvU32 checks;
    NvU32 failures;
    NvU32 bootAttempts;
    NvBool apiLockAcquired;
    NvBool gpuLockAcquired;
    NvBool locksReleased;
    NvBool gpuObjectPresent;
    NvBool targetDevice;
    NvBool ownerMatches;
    NvBool gspClient;
    NvBool gspObjectPresent;
    NvBool gspInitResponseDecoded;
    NvBool gpuFullyConstructed;
    NvBool gpuStateLoaded;
    NvBool gpuStateStable;
    NvBool originalInitFlagsComplete;
    NvBool gpuConnected;
    NvBool gpuNotLost;
    NvBool gspHealthy;
    NvBool adapterReady;
} S540GspOriginalEvidence;

/*
 * The observer reads fields and does not issue GPU commands, firmware uploads,
 * or marker writes. Original GPU-lock wrappers retain their normal interrupt
 * mask/restore side effects. Call after rm_init_adapter returned true and before
 * adapter shutdown. The outer ordinary owner must keep nv/sp alive and stop
 * teardown while this function acquires original API-then-device-GPU locks.
 * This function must be compiled with the global RM namespace header.
 *
 * gspInitResponseDecoded observes the sole original persistent success marker:
 * it is set only after GSP_INIT completes and its static-info response decodes.
 * It is never inferred from requesting firmware, image delivery, or a timeout.
 * Counts are observation checks and the original bootAttempts field, not a
 * fabricated count of GPU requests, interrupts, or successfully executed jobs.
 */
NV_STATUS s540GspObserveOriginal(nvidia_stack_t *sp, nv_state_t *nv,
                               S540GspOriginalEvidence *out);

#ifdef __cplusplus
}
#endif
#endif
