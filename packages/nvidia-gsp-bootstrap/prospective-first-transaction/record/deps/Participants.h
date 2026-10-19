/* SPDX-License-Identifier: MIT; SCRATCH PROPOSAL ONLY */
#pragma once
#include "nvidia-gsp-bootstrap/cancellation/S540NvidiaGspCancellation.h"
#ifdef __cplusplus
extern "C" {
#endif
typedef NvU64 S540GspCancellationLease;
NV_STATUS s540GspCancellationCaptureCurrent(const void *, S540GspCancellationLease *);
NV_STATUS s540GspCancellationEnterLease(S540GspCancellationLease, const void *);
NV_STATUS s540GspCancellationLeaveLease(S540GspCancellationLease, const void *);
NV_STATUS s540GspCancellationDiscardLease(S540GspCancellationLease, const void *);
NvU32 s540GspCancellationPendingLeases(void);
NvBool s540GspCancellationSkipOptionalCurrent(void);
#ifdef __cplusplus
}
#endif
