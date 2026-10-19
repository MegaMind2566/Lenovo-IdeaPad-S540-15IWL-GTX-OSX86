/* SPDX-License-Identifier: MIT */
#ifndef S540_NVIDIA_GSP_DMA_STOP_H
#define S540_NVIDIA_GSP_DMA_STOP_H
#include "../../nvidia-os-adapter/upstream/include/nvtypes.h"
#include "../../nvidia-os-adapter/upstream/include/nvstatus.h"
#ifdef __cplusplus
extern "C" {
#endif
/* Only a reviewed original shutdown bridge can issue this opaque receipt.
 * IRQ exclusion, an absent GPU pointer and Boolean init failure cannot issue
 * it. The current ten-overlay profile has no issuer and always refuses.
 */
typedef struct S540GspDmaStopReceipt S540GspDmaStopReceipt;
NV_STATUS s540GspContextValidateDmaStopReceipt(const void *originalState,
    const void *sessionIdentity, NvU64 sessionGeneration,
    const S540GspDmaStopReceipt *receipt);
#ifdef __cplusplus
}
#endif
#endif
