/* SPDX-License-Identifier: MIT */
#ifndef S540_NVIDIA_POWER_COUPLING_H
#define S540_NVIDIA_POWER_COUPLING_H
#include "../cancellation/S540NvidiaGspCancellation.h"
#ifdef __cplusplus
extern "C" {
#endif
/* The genuine PM guard owns this fixed cancellation binding. No callback
 * owner pointer is borrowed by cancellation and no power claim is made. */
NV_STATUS s540GspCancellationPowerAcquireState(const void *, S540GspCancellationToken);
NV_STATUS s540GspCancellationPowerReleaseState(const void *, S540GspCancellationToken);
NV_STATUS s540GspCancellationPowerRevokeAtState(const void *, S540GspCancellationToken, NvU64);
#ifdef __cplusplus
}
#endif
#endif
