/* SPDX-License-Identifier: MIT */
/* Compile with the pinned original headers and the authentic namespace. */
#include "nv.h"
#include "gpu/gpu.h"
#include "S540NvidiaGspCancellationOriginal.h"
NV_STATUS s540GspCancellationCheckGpu(OBJGPU *gpu) {
    return s540GspCancellationCheckState(NV_GET_NV_STATE(gpu));
}
NV_STATUS s540GspCancellationBeginCleanupGpu(OBJGPU *gpu) {
    return s540GspCancellationBeginCleanupState(NV_GET_NV_STATE(gpu));
}
