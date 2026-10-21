/* SPDX-License-Identifier: MIT */
#ifndef S540_NVIDIA_DMA_PRODUCER_H
#define S540_NVIDIA_DMA_PRODUCER_H
#include "../prospective-first-transaction/record/S540NvidiaGspFirstTransaction.h"
#include "../prospective-pm-revocation-closure/S540NvidiaGspCommit.h"
#ifdef __cplusplus
extern "C" {
#endif
/* Actual little-endian PCI command byte, bit 2. This predicate identifies
 * an attempted BME enable; it grants no permission or device readiness. */
static inline NvBool s540DmaConfigWriteEnablesBusMaster(NvU32 offset,
    NvU32 width, NvU32 value)
{
    NvU32 lane;
    if ((width != 1 && width != 2 && width != 4) || offset > 4 ||
        width <= 4 - offset) return NV_FALSE;
    lane = 4 - offset;
    return ((value >> (lane * 8)) & 4U) != 0;
}
/* Sticky failure does not erase the retained master. This narrowly observes
 * a real revoked CLEANUP epoch after all tracked CPU producers are absent.
 * It never changes record status/phase, grants RM entry or proves DMA drain.
 * The IRQ mask path must repeat this query under its actual original locks. */
NV_STATUS s540FirstTxnCleanupMaskReadMaster(const void *exactNv,
    S540FirstTxnGlobalSnapshot *out);
#ifdef __cplusplus
}
#endif
#endif
