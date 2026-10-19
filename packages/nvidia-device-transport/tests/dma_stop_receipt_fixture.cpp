// SPDX-License-Identifier: MIT
#include "dma_stop_receipt_fixture.h"
// Opaque in the public headers; only this native mock authority owns the
// fixture representation. Production links the strong original Context bridge.
struct S540GspDmaStopReceipt {
    const void *state;
    const void *session;
    NvU64 generation;
    bool stopped;
    NV_STATUS status;
};
namespace {
S540GspDmaStopReceipt receipts[32]{};
NvU32 issued;
NvU32 verifications;
}
const S540GspDmaStopReceipt *S540DmaStopFixture::issue(const void *state,
    const void *session, NvU64 generation, bool stopped, NV_STATUS status) {
    if (issued == 32) return nullptr;
    receipts[issued] = S540GspDmaStopReceipt{state,session,generation,stopped,status};
    return &receipts[issued++];
}
void S540DmaStopFixture::reset() {
    for (auto &receipt : receipts) receipt = S540GspDmaStopReceipt{};
    issued = verifications = 0;
}
NvU32 S540DmaStopFixture::calls() { return verifications; }
extern "C" NV_STATUS s540GspContextValidateDmaStopReceipt(const void *state,
    const void *session, NvU64 generation, const S540GspDmaStopReceipt *receipt) {
    ++verifications;
    const S540GspDmaStopReceipt *owned = nullptr;
    for (NvU32 i = 0; i < issued; ++i) if (receipt == &receipts[i]) { owned = &receipts[i]; break; }
    if (!owned) return NV_ERR_NOT_SUPPORTED;
    if (owned->state != state || owned->session != session || owned->generation != generation)
        return NV_ERR_INVALID_STATE;
    if (owned->status != NV_OK) return owned->status;
    return owned->stopped ? NV_STATUS(NV_OK) : NV_STATUS(NV_ERR_BUSY_RETRY);
}
