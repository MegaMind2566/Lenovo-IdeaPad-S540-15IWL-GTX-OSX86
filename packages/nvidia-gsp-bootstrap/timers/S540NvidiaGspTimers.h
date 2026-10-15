// SPDX-License-Identifier: MIT
#ifndef S540_NVIDIA_GSP_TIMERS_H
#define S540_NVIDIA_GSP_TIMERS_H
#include "../../nvidia-darwin-services/src/S540NvidiaDarwinServices.h"
#ifdef __cplusplus
extern "C" {
#endif
struct nv_state_t;
// Bind after HostInitialize and before original adapter initialization. Stop
// before adapter/global state is destroyed. Unbind only after every original
// RM timer user has relinquished its references. Failed cancellation retains
// all implicated storage and makes Unbind refuse cleanup.
NV_STATUS s540GspTimersBind(struct nv_state_t *);
NV_STATUS s540GspTimersStop(struct nv_state_t *);
NV_STATUS s540GspTimersUnbind(struct nv_state_t *);
typedef struct S540GspTimersSnapshot {
    NvU32 liveNanoTimers;
    NvU32 callbacks;
    NvU32 callbackFailures;
    NvU32 cancellationFailures;
    NvU32 rejectedCalls;
    NvBool bound;
    NvBool stopped;
    NvBool quarantined;
} S540GspTimersSnapshot;
void s540GspTimersGetSnapshot(S540GspTimersSnapshot *);
#ifdef __cplusplus
}
#endif
#endif
