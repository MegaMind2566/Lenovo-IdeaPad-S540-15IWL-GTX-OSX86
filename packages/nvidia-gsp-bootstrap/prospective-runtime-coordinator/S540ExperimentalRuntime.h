/* SPDX-License-Identifier: MIT */
#ifndef S540_EXPERIMENTAL_RUNTIME_H
#define S540_EXPERIMENTAL_RUNTIME_H
#include "../../nvidia-os-adapter/upstream/include/nvtypes.h"
#include "../../nvidia-os-adapter/upstream/include/nvstatus.h"
#ifdef __cplusplus
extern "C" {
#endif
#define S540_EXPERIMENTAL_MANUAL_ACK 0x5335343054524941ULL
#define S540_EXPERIMENTAL_TARGET_BUILD "25G241"
/* The final native linker supplies these immutable 104 bytes after measuring
 * the actual complete compiled graph. The code contract excludes only this
 * profile payload, avoiding an impossible hash of its own hash. */
typedef struct S540ExperimentalNativeProfile {
    NvU32 format, bytes;
    NvU8 codeContractSha256[32];
    char targetBuild[16];
    NvU64 workerStackBytes, irqStackBytes;
    NvU64 frameworkAllowanceBytes, unknownAllowanceBytes;
    NvU64 recursionAllowanceBytes, exceptionAllowanceBytes;
} S540ExperimentalNativeProfile;
typedef struct S540ExperimentalRuntimeRequest {
    NvU32 format, bytes;
    NvU64 observedHostStackBytes, manualAcknowledgement;
    NvU8 codeContractSha256[32];
    char targetBuild[16];
} S540ExperimentalRuntimeRequest;
enum S540ExperimentalRuntimeStage {
    S540_RUNTIME_UNUSED=0, S540_RUNTIME_REQUEST=1, S540_RUNTIME_RETAINED=2,
    S540_RUNTIME_CANCEL_OPERATION=3, S540_RUNTIME_OWNER_EPOCH=4,
    S540_RUNTIME_GLOBAL=5, S540_RUNTIME_GLOBAL_READY=6,
    S540_RUNTIME_CONTEXT=7, S540_RUNTIME_TRANSACTION=8,
    S540_RUNTIME_IRQ=9, S540_RUNTIME_ORIGINAL=10,
    S540_RUNTIME_RETURNED=11, S540_RUNTIME_FAILED=12
};
/* Diagnostic wire-safe integers. No field authorizes entry or reclamation. */
typedef struct S540ExperimentalRuntimeSnapshot {
    NvU32 format, bytes, stage, firstStatus;
    NvU32 globalStatus, contextStatus, bindStatus, irqStatus, originalStatus;
    NvU32 lifetimeRetained, cancellationBegun, ownerEpochBegun;
    NvU32 globalInitialized, globalOriginalReturned, globalOriginalStatus;
    NvU32 originalEntered, adapterAttempted, adapterInitialized;
    NvU32 originalReturned, interruptInstalled, interruptArmed, cancellationRevoked;
    NvU32 snapshotStatus;
    NvU64 workerThread, generation, observedHostStackBytes;
    NvU64 requiredWorkerStackBytes, requiredIrqStackBytes;
} S540ExperimentalRuntimeSnapshot;
NV_STATUS s540RuntimeReadCompiledProfile(S540ExperimentalNativeProfile *);
NV_STATUS s540RuntimeEmbeddedFirmware(const void **gsp, NvU64 *gspBytes,
                                    const void **ucodes, NvU64 *ucodesBytes);
/* Exact active retained owner/master/cancellation pull. Not a readiness flag. */
NV_STATUS s540RuntimeRequireGlobalEntry(void);
#ifdef __cplusplus
}
static_assert(sizeof(S540ExperimentalNativeProfile)==104,"native profile ABI");
static_assert(sizeof(S540ExperimentalRuntimeRequest)==72,"runtime request ABI");
#endif
#endif
