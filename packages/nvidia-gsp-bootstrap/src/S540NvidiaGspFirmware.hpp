// SPDX-License-Identifier: MIT
#ifndef S540_NVIDIA_GSP_FIRMWARE_HPP
#define S540_NVIDIA_GSP_FIRMWARE_HPP
#include "../../nvidia-os-adapter/upstream/include/nvtypes.h"
#include "../../nvidia-os-adapter/upstream/include/nvstatus.h"

namespace S540NvidiaGspFirmware {
constexpr NvU32 kMaximumLeases = 64;
// TU117 selects TU11X in the pinned original family selector. The original
// filename selector maps TU11X to the unchanged tu10x GSP/UCODES image pair.
constexpr NvU32 kTu117Family = 2;
constexpr NvU32 kGsp = 0;
constexpr NvU32 kUcodes = 2;
struct Snapshot {
    NvU32 acquisitions, releases, rejected, liveLeases;
    bool verified, deliveredGsp, deliveredUcodes, active, cleanShutdown, overflow;
};
// One ordinary owner thread serializes all successful operations. Wrong-thread
// calls only increment an atomic rejection counter. Image memory is borrowed
// immutable storage and must outlive this object and every original RM lease.
// A handle is an opaque generation token; it is never dereferenced as memory.
class Store {
public:
    Store();
    NV_STATUS initialize(const void *ownerState, NvU64 ownerThread,
                         const void *gsp, NvU64 gspBytes,
                         const void *ucodes, NvU64 ucodesBytes);
    const void *get(const void *ownerState, NvU64 thread, NvU32 type, NvU32 family,
                    const void **bytes, NvU32 *size);
    bool put(NvU64 thread, const void *handle);
    bool shutdown(NvU64 thread);
    Snapshot snapshot() const;
    bool ownedBy(NvU64 thread) const;
private:
    struct Lease { const void *token; NvU32 type; } leases_[kMaximumLeases];
    const void *owner_, *gsp_, *ucodes_;
    NvU64 thread_;
    NvU32 gspSize_, ucodesSize_;
    Snapshot state_;
    void reject();
    Store(const Store &) = delete;
    Store &operator=(const Store &) = delete;
};
// Binding/unbinding belongs to the outer RM startup lease. No producer may
// remain during unbind; the caller retains Store storage on any refusal.
NV_STATUS bind(Store *store);
NV_STATUS unbind(Store *store);
}
#endif
