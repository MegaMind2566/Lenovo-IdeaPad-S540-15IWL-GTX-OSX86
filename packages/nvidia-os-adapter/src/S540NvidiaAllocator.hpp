// SPDX-License-Identifier: MIT
#ifndef S540_NVIDIA_ALLOCATOR_HPP
#define S540_NVIDIA_ALLOCATOR_HPP

#include "../upstream/include/nvtypes.h"
#include "../upstream/include/nvstatus.h"
#include "../upstream/include/nv-kernel-interface-api.h"
#include <stddef.h>

namespace S540NvidiaAllocator {

// Ordinary CPU RAM only. Allocation/free require thread context, interrupts
// enabled, and no spin lock held; Darwin may block. No physical contiguity, DMA
// address, or GPU mapping is given. These are not interrupt-safe NvPort hooks.
static constexpr size_t kAlignment = 16;
static constexpr size_t kHeaderBytes = 16;
static constexpr size_t kMaximumOverhead = kHeaderBytes + kAlignment - 1;

inline bool allocationSize(NvU64 requested, size_t &total) {
    total = 0;
    const size_t maximum = static_cast<size_t>(-1);
    if (requested == 0 || requested > maximum - kMaximumOverhead)
        return false;
    total = static_cast<size_t>(requested) + kMaximumOverhead;
    return true;
}

} // namespace S540NvidiaAllocator

extern "C" {

// The declarations preserve the pinned NVIDIA OS interface ABI. A zero-sized
// request is rejected; memory is uninitialized. All failures clear a valid out
// pointer. Free accepts NULL, otherwise it requires the exact allocation result.
NV_STATUS NV_API_CALL os_alloc_mem(void **output, NvU64 length);
void NV_API_CALL os_free_mem(void *memory);

}

#endif
