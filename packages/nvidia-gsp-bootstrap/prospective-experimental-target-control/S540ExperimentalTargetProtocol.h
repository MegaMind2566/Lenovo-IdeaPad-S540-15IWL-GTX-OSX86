/* SPDX-License-Identifier: MIT */
#ifndef S540_EXPERIMENTAL_TARGET_PROTOCOL_H
#define S540_EXPERIMENTAL_TARGET_PROTOCOL_H
#include "../../nvidia-os-adapter/upstream/include/nvtypes.h"
#include "../../nvidia-os-adapter/upstream/include/nvstatus.h"
#include "../prospective-preparation-observation/S540PreparationObservation.h"
#define S540_EXPERIMENTAL_PROTOCOL_VERSION 1U
#define S540_EXPERIMENTAL_SNAPSHOT_VERSION 3U
#define S540_EXPERIMENTAL_CONNECTION_TYPE 0x53355452U
#define S540_EXPERIMENTAL_SELECTOR_SNAPSHOT 0U
#define S540_EXPERIMENTAL_SELECTOR_REQUEST 1U
#define S540_EXPERIMENTAL_SELECTOR_STOP 2U
#define S540_EXPERIMENTAL_MANUAL_ACK 0x5335343054524941ULL
typedef struct S540ExperimentalBuildIdentity {
    NvU32 format, bytes;
    NvU8 sourceSha256[32], policySha256[32];
    NvU64 requiredKernelStackBytes;
} S540ExperimentalBuildIdentity;
typedef struct S540ExperimentalRequest {
    NvU32 format, bytes;
    NvU64 generation, observedKernelStackBytes, manualAcknowledgement;
    NvU8 sourceSha256[32], policySha256[32], nativeCodeContractSha256[32];
    char targetBuild[16];
} S540ExperimentalRequest;
typedef enum S540ExperimentalPhase {
    S540_EXPERIMENTAL_COLD = 0,
    S540_EXPERIMENTAL_MODULE_ENTERED = 1,
    S540_EXPERIMENTAL_CONTROL_STARTED = 2,
    S540_EXPERIMENTAL_RUNNING = 3,
    S540_EXPERIMENTAL_RETURNED = 4,
    S540_EXPERIMENTAL_STOPPING = 5,
    S540_EXPERIMENTAL_RETAINED = 6
} S540ExperimentalPhase;
typedef struct S540ExperimentalStopObservation {
    NvU32 format, bytes, attempts;
    NV_STATUS status, firstError, snapshotStatus;
    NV_STATUS identityStatus, locksStatus, protocolStatus, closingStatus;
    NV_STATUS servicesStatus, sealStatus, disableStatus, interruptStatus, shutdownStatus;
    NvU64 generation;
    NvU32 requested, retained, originalReturned, originalExitReady, locksReleased;
    NvU32 protocolAttempted, servicesAttempted, interruptAttempted, disableAttempted, shutdownAttempted;
    NvU32 servicesDrained, interruptSoftwareDrained, interruptFullyDrained;
    NvU32 cleanupComplete, physicalReleaseAuthorized, pmAcknowledgementSent;
    NvU32 protocolFormat, protocolBytes;
    NvU64 protocolGeneration;
    NV_STATUS protocolOperationStatus, protocolOriginalReturnStatus, protocolUnlockStatus;
    NvU32 protocolClaimed, protocolOriginalEntered, protocolOriginalReturned, protocolCompleted;
} S540ExperimentalStopObservation;
/* Returned bits make a genuine NV_ERR_NOT_READY distinguishable from a status
 * slot that has never been filled. These bits report calls; they grant no
 * execution, cleanup, PM or release authority. */
#define S540_RUNTIME_CALL_GLOBAL 1U
#define S540_RUNTIME_CALL_CONTEXT 2U
#define S540_RUNTIME_CALL_BIND 4U
#define S540_RUNTIME_CALL_IRQ 8U
#define S540_RUNTIME_CALL_ORIGINAL 16U
#define S540_RUNTIME_CALL_ALL 31U
typedef struct S540ExperimentalRuntimeObservation {
    NvU32 format, bytes, snapshotStatus;
    NvU32 stage, lastStage, firstFailureStage, firstStatus;
    NvU32 attemptedMask, returnedMask;
    NV_STATUS globalStatus, contextStatus, bindStatus, irqStatus, originalStatus;
    NvU32 lifetimeRetained, cancellationBegun, ownerEpochBegun;
    NvU32 globalInitialized, globalOriginalReturned, globalOriginalStatus;
    NvU32 originalEntered, adapterAttempted, adapterInitialized, originalReturned;
    NvU32 interruptInstalled, interruptArmed, cancellationRevoked;
    NvU64 generation, observedHostStackBytes, requiredWorkerStackBytes, requiredIrqStackBytes;
} S540ExperimentalRuntimeObservation;
typedef struct S540ExperimentalIrqSourceObservation {
    NvU32 format, bytes;
    NvU32 sourceProbeAttempted, sourceProbeReturned, sourceProbeStatus, sourceCount;
    NvU32 sourcesObserved, messagedSources, selectedSourceValid, selectedSource;
    NvU32 selectedInterruptType, selectedTypeValid;
    NvU32 inventoryValid, msiCapable, msixCapable, msiVectors;
} S540ExperimentalIrqSourceObservation;
/* Fixed integer-only wire ABI. Snapshot version3 appends runtime and IRQ-route
 * diagnostics after the existing preparation record at offset464;
 * the request/identity ABI remains version1. Unknown observations remain zero;
 * their independent status fields say whether an observation was obtained.
 * No diagnostic field grants memory, PM or unload authority. */
typedef struct S540ExperimentalSnapshot {
    NvU32 format, bytes, phase;
    NV_STATUS lastStatus;
    NvU64 generation, observedKernelStackBytes;
    NvU32 moduleEntryAccepted, controlServiceStarted, requestConsumed, requestRunning;
    NvU32 stopRequested, retainedUntilReboot, ownerAllocated, providerFound;
    NvU32 preparationAttempted, preparationReturned, initializationAttempted, initializationReturned;
    NvU32 stopAttempted, stopReturned, originalEntryObserved, globalInitialized;
    NvU32 adapterInitialized, firmwareLoaded, interruptInstalled, interruptArmed;
    NvU32 powerRevoked, cancellationRevoked, powerAcknowledged, reserved0;
    NV_STATUS preparationStatus, initializationStatus, cancellationStatus, stopStatus;
    NV_STATUS runtimeObservationStatus, stopObservationStatus;
    NvU32 wholeDmaStopProven, pmAcknowledgementAuthorized, accelerationTest, reserved1;
    NvU64 nativeRequiredKernelStackBytes, nativeRequiredIrqStackBytes;
    NvU8 sourceSha256[32], policySha256[32], nativeCodeContractSha256[32];
    S540ExperimentalStopObservation retainedStop;
    S540PreparationObservation preparation;
    S540ExperimentalRuntimeObservation runtime;
    S540ExperimentalIrqSourceObservation irqSource;
} S540ExperimentalSnapshot;
#ifdef __cplusplus
extern "C" {
#endif
const S540ExperimentalBuildIdentity *s540ExperimentalGetBuildIdentity(void);
#ifdef __cplusplus
}
#endif
#endif
