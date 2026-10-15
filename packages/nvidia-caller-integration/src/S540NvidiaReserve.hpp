// SPDX-License-Identifier: MIT
#ifndef S540_NVIDIA_RESERVE_HPP
#define S540_NVIDIA_RESERVE_HPP

#include "../../nvidia-os-adapter/upstream/include/nvtypes.h"
#include "../../nvidia-os-adapter/upstream/include/nvstatus.h"
#include "../../nvidia-os-adapter/upstream/include/nv-kernel-interface-api.h"

namespace S540NvidiaReserve {

constexpr NvU32 kSlotCount = 32;
constexpr NvU64 kSlotBytes = 128ULL * 1024ULL;
constexpr NvU64 kReserveBytes = kSlotCount * kSlotBytes;
constexpr NvU32 kAlignment = 16;

// Lifecycle calls require an ordinary thread, externally serialized against
// one another, with every hook invocation quiesced. They are not IRQ APIs.
// initialize() is idempotent. Failed lifecycle calls preserve the reserve.
bool initialize();
bool shutdown();
bool ready();
NvU32 liveSlots();

} // namespace S540NvidiaReserve

extern "C" {
// One bounded slot scan may return NV_ERR_NO_MEMORY under contention, even
// when the reserve was not globally full at a single instant during the call.
NV_STATUS NV_API_CALL os_alloc_mem(void **address, NvU64 size);
void NV_API_CALL os_free_mem(void *address);
}

#endif
