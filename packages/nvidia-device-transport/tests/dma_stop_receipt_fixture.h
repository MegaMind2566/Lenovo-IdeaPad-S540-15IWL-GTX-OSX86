// SPDX-License-Identifier: MIT
#ifndef S540_DMA_STOP_RECEIPT_FIXTURE_H
#define S540_DMA_STOP_RECEIPT_FIXTURE_H
#if defined(KERNEL)
#error "Native DMA stop authority fixture must never enter a production kernel bridge"
#endif
#include "../src/S540NvidiaDeviceTransport.hpp"
// Native-only mock authority. This file is never a production bridge.
namespace S540DmaStopFixture {
const S540GspDmaStopReceipt *issue(const void *state, const void *session,
    NvU64 generation, bool stopped, NV_STATUS status = NV_OK);
void reset();
NvU32 calls();
}
#endif
