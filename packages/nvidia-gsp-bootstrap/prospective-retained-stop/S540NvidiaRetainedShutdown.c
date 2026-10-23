/* SPDX-License-Identifier: MIT */
#include "nv.h"
#include "S540NvidiaRetainedStop.h"
#include "../prospective-shutdown-protocol/S540NvidiaShutdownProtocol.h"
NV_STATUS s540RetainedShutdownRun(void *stack, void *nv,
    S540RetainedShutdownResult *out)
{
    S540ShutdownProtocolEvidence evidence = {0};
    S540RetainedShutdownResult result = {0};
    NV_STATUS status;
    if (!out) return NV_ERR_INVALID_ARGUMENT;
    result.format = 1; result.bytes = sizeof(result);
    status = s540ShutdownProtocolRun((nvidia_stack_t *)stack, (nv_state_t *)nv, &evidence);
    result.generation = evidence.generation;
    result.operationStatus = evidence.operationStatus;
    result.originalReturnStatus = evidence.originalReturnStatus;
    result.unlockStatus = evidence.unlockStatus;
    result.claimed = evidence.claimed;
    result.originalEntered = evidence.originalEntered;
    result.originalReturned = evidence.originalReturned;
    result.protocolCompleted = evidence.protocolCompleted;
    *out = result;
    return status;
}
