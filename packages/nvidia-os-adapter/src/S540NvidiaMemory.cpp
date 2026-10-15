// SPDX-License-Identifier: MIT
#include "S540NvidiaMemory.hpp"

#if defined(KERNEL)
#include <libkern/libkern.h>
#else
#include <string.h>
#endif

static_assert(NVCPU_IS_X86_64 && sizeof(void *) == 8,
              "The memory adapter supports Intel x86_64 only.");
static_assert(sizeof(NvLength) == 8 && sizeof(NvU32) == 4,
              "Preserve NVIDIA's native wide length and 32-bit OS-hook ABI.");
static_assert(sizeof(int) == sizeof(NvS32),
              "Darwin memcmp and NVIDIA comparison results must have equal width.");

// Only ordinary CPU-accessible RAM with valid complete object ranges is allowed.
// These hooks do not allocate, pin, map, touch MMIO, or provide volatile access.
extern "C" void *NV_API_CALL os_mem_copy(void *destination, const void *source,
                                        NvU32 length) {
    return length == 0 ? destination : memcpy(destination, source, length);
}

extern "C" void *NV_API_CALL os_mem_set(void *destination, NvU8 value,
                                       NvU32 length) {
    return length == 0 ? destination : memset(destination, value, length);
}

extern "C" NvS32 NV_API_CALL os_mem_cmp(const NvU8 *left, const NvU8 *right,
                                       NvU32 length) {
    return length == 0 ? 0 : static_cast<NvS32>(memcmp(left, right, length));
}

extern "C" void *s540NvidiaMemoryCopy(void *destination, const void *source,
                                      NvLength length) {
    NvU8 *output = static_cast<NvU8 *>(destination);
    const NvU8 *input = static_cast<const NvU8 *>(source);
    while (length != 0) {
        const NvU32 chunk = S540NvidiaMemory::chunkLength(length);
        os_mem_copy(output, input, chunk);
        length -= chunk;
        if (length != 0) {
            output += chunk;
            input += chunk;
        }
    }
    return destination;
}

extern "C" void *s540NvidiaMemorySet(void *destination, NvU8 value,
                                     NvLength length) {
    NvU8 *output = static_cast<NvU8 *>(destination);
    while (length != 0) {
        const NvU32 chunk = S540NvidiaMemory::chunkLength(length);
        os_mem_set(output, value, chunk);
        length -= chunk;
        if (length != 0)
            output += chunk;
    }
    return destination;
}

extern "C" NvS32 s540NvidiaMemoryCompare(const NvU8 *left, const NvU8 *right,
                                         NvLength length) {
    while (length != 0) {
        const NvU32 chunk = S540NvidiaMemory::chunkLength(length);
        const NvS32 result = os_mem_cmp(left, right, chunk);
        if (result != 0)
            return result;
        length -= chunk;
        if (length != 0) {
            left += chunk;
            right += chunk;
        }
    }
    return 0;
}
