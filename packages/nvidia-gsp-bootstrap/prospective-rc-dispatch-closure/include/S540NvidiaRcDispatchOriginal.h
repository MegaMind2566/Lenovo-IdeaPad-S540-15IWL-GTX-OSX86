/* SPDX-License-Identifier: MIT */
#ifndef S540_NVIDIA_RC_DISPATCH_ORIGINAL_H
#define S540_NVIDIA_RC_DISPATCH_ORIGINAL_H
#include "nvtypes.h"
#include "nvstatus.h"
struct OBJGPU;
#ifdef __cplusplus
extern "C" {
#endif
/* Explicit private original namespace. Legacy generated declarations and ABI
 * remain unchanged. A nonzero result retains the actual queued obligation. */
NV_STATUS s540Global_s540OsRun1HzCallbacksNowStatus(struct OBJGPU *);
NV_STATUS s540Global_s540OsRunQueued1HzCallbacksUnderLockStatus(struct OBJGPU *);
#ifdef __cplusplus
}
#endif
#endif
