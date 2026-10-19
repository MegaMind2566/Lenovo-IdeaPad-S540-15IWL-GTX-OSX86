/* SPDX-License-Identifier: MIT */
#ifndef S540_NVIDIA_GSP_CANCELLATION_ORIGINAL_H
#define S540_NVIDIA_GSP_CANCELLATION_ORIGINAL_H
#include "S540NvidiaGspCancellation.h"
struct OBJGPU;
#ifdef __cplusplus
extern "C" {
#endif
NV_STATUS s540GspCancellationCheckGpu(struct OBJGPU *);
NV_STATUS s540GspCancellationBeginCleanupGpu(struct OBJGPU *);
#ifdef __cplusplus
}
#endif
#endif
