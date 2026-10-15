// SPDX-License-Identifier: MIT
#include "S540NvidiaDarwinInternal.hpp"
#if defined(KERNEL)
#include <sys/random.h>
#else
#include <cerrno>
#include <unistd.h>
#if defined(__APPLE__)
// Darwin declares userspace getentropy in sys/random.h, not unistd.h.
#include <sys/random.h>
#endif
#endif
extern "C" NV_STATUS NV_API_CALL s540Darwin_os_get_random_bytes(NvU8 *output, NvU16 count) {
    if (count != 0 && output == nullptr) return NV_ERR_INVALID_ARGUMENT;
    if (!S540DarwinInternal::ordinary()) return NV_ERR_INVALID_REQUEST;
#if defined(KERNEL)
    if (count != 0) read_random(output, count);
#else
    // getentropy is an actual OS CSPRNG API on both native Darwin and Linux.
    // Its per-call limit is 256 bytes, smaller than NVIDIA's 16-bit length.
    NvU32 offset = 0;
    while (offset < count) {
        const NvU32 chunk = count - offset > 256 ? 256 : count - offset;
        int result;
        do { result = getentropy(output + offset, chunk); } while (result != 0 && errno == EINTR);
        if (result != 0) return NV_ERR_OPERATING_SYSTEM;
        offset += chunk;
    }
#endif
    return NV_OK;
}
extern "C" NV_STATUS NV_API_CALL s540Darwin_os_schedule(void) {
    if (!S540DarwinInternal::ordinary()) return NV_ERR_ILLEGAL_ACTION;
    // Linux's original schedule_timeout(1) blocks for one scheduler tick;
    // an actual one-millisecond OS sleep yields this ordinary Darwin thread.
    return s540Darwin_os_delay(1);
}
extern "C" void NV_API_CALL s540Darwin_os_flush_cpu_write_combine_buffer(void) {
    // Exact x86_64 instruction used by the pinned original Linux backend.
    // A compiler-only barrier or success-without-fence would be insufficient.
    __asm__ volatile("sfence" ::: "memory");
}
