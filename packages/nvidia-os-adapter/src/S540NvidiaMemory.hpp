// SPDX-License-Identifier: MIT
#ifndef S540_NVIDIA_MEMORY_HPP
#define S540_NVIDIA_MEMORY_HPP

#include "../upstream/nvport_memory_primitives.h"

namespace S540NvidiaMemory {

// The real OS-hook ABI has a 32-bit length; NvPort's NvLength is 64-bit here.
// This pure policy is shared by all wide-length loops and targeted edge tests.
static constexpr NvLength kMaximumChunkLength = 0xffffffffULL;

inline NvU32 chunkLength(NvLength remaining) {
    return static_cast<NvU32>(remaining > kMaximumChunkLength
                                 ? kMaximumChunkLength : remaining);
}

} // namespace S540NvidiaMemory

#endif
