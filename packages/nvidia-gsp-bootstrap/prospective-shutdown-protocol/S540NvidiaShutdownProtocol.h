/* SPDX-License-Identifier: MIT */
#ifndef S540_NVIDIA_SHUTDOWN_PROTOCOL_H
#define S540_NVIDIA_SHUTDOWN_PROTOCOL_H
#include "nv.h"
#ifdef __cplusplus
extern "C" {
#endif
/* An observation, never a DMA-stop receipt or authority to free anything. */
typedef struct S540ShutdownProtocolEvidence {
    NvU32 format;
    NvU64 generation, masterThread;
    const void *owner, *nv, *privateState, *gpu;
    const char *sourceProfileSha256;
    NV_STATUS operationStatus, originalReturnStatus, unlockStatus;
    NvBool claimed, originalEntered, originalReturned, protocolCompleted;
} S540ShutdownProtocolEvidence;
/* Requires the genuine first-transaction record and its full lock-capability
 * predicate. One image can claim at most one attempt, including a failed one.
 * The outer owner must retain all resources and module text after any claim.
 * No context destruction, transport drain, PM stop or retry is authorized. */
NV_STATUS s540ShutdownProtocolRun(nvidia_stack_t *stack, nv_state_t *exactNv,
    S540ShutdownProtocolEvidence *out);
#ifdef __cplusplus
}
#endif
#endif
