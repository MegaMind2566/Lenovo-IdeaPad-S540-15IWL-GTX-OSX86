/* SPDX-License-Identifier: MIT */
#pragma once
#include "../record/S540NvidiaGspFirstTransaction.h"
typedef struct S540OriginalControlResult {
    NvU32 apiAcquired, apiReleased, gpuAcquired, gpuReleased, deferredCalls,
        cleanupCalls, exitReadyCalls, runtimeDepth, threadDepth, identityErrors,
        originalDestructors, originalUnlinks, originalFrees, constructorBaseDestructors;
    NV_STATUS firstStatus, wrapperStatus, guardStatus;
    NvBool apiHeldAtDeferred, gpuHeldAtDeferred, firmwareRetained,
        ownershipPreserved, exitAfterActualTokens, wrapperReturned;
    S540FirstTxnServiceCounters counters;
} S540OriginalControlResult;
#ifdef __cplusplus
extern "C" {
#endif
NV_STATUS s540OriginalControlInitialize(void);
void s540OriginalControlShutdown(void);
void s540OriginalControlWrapper(NvU32 scenario, S540OriginalControlResult *);
void s540OriginalControlNvoc(NvU32 scenario, S540OriginalControlResult *);
void s540OriginalControlCtor(NvU32 scenario, S540OriginalControlResult *);
void s540OriginalControlBootArgs(NvU32 scenario, S540OriginalControlResult *);
NvBool s540OriginalControlRealTokensAvailable(void);
void s540OriginalControlCurrentCounters(S540FirstTxnServiceCounters *);
NV_STATUS s540OriginalControlCurrentGuard(void);
NV_STATUS s540OriginalControlFullLocksStatus(void);
#ifdef __cplusplus
}
#endif
