/* SPDX-License-Identifier: MIT */
#ifndef S540_NVIDIA_RETAINED_STOP_H
#define S540_NVIDIA_RETAINED_STOP_H
#include "../../nvidia-os-adapter/upstream/include/nvtypes.h"
#include "../../nvidia-os-adapter/upstream/include/nvstatus.h"
#ifdef __cplusplus
extern "C" {
#endif
typedef struct S540RetainedShutdownResult {
    NvU32 format, bytes;
    NvU64 generation;
    NV_STATUS operationStatus, originalReturnStatus, unlockStatus;
    NvBool claimed, originalEntered, originalReturned, protocolCompleted;
} S540RetainedShutdownResult;
/* Plain C boundary: nv.h and the original nvidia_stack_t remain inside a
 * separately compiled original-C translation unit, with exact original ABI. */
NV_STATUS s540RetainedShutdownRun(void *stack, void *nv, S540RetainedShutdownResult *);
typedef struct S540RetainedStopSnapshot {
    NvU32 format, bytes, attempts;
    NV_STATUS status, firstError, snapshotStatus;
    NV_STATUS identityStatus, locksStatus, protocolStatus, closingStatus;
    NV_STATUS servicesStatus, sealStatus, disableStatus, interruptStatus, shutdownStatus;
    NvU64 generation;
    NvBool requested, retained, originalReturned, originalExitReady, locksReleased;
    NvBool protocolAttempted, servicesAttempted, interruptAttempted, disableAttempted, shutdownAttempted;
    NvBool servicesDrained, interruptSoftwareDrained, interruptFullyDrained;
    NvBool cleanupComplete, physicalReleaseAuthorized, pmAcknowledgementSent;
    S540RetainedShutdownResult protocol;
} S540RetainedStopSnapshot;
#ifdef __cplusplus
}
#endif
#endif
