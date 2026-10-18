// SPDX-License-Identifier: MIT
#include "S540NvidiaDarwinInternal.hpp"
#if defined(KERNEL)
#include <kern/task.h>
#else
#include <cerrno>
#include <fcntl.h>
#include <unistd.h>
#endif

namespace {
// XNU's pinned x86-64 copyio limits one invocation to 64 MiB. Keep each
// fault-recoverable operation below that bound, including 32-bit-size callers.
constexpr NvU32 kCopyChunk = 1024U * 1024U;
bool validRange(const void *pointer, NvU32 bytes) {
    const NvUPtr address = reinterpret_cast<NvUPtr>(pointer);
    return pointer && address <= ~NvUPtr{0} - (bytes - 1U);
}
#if !defined(KERNEL)
NV_STATUS nativeCopy(void *output, const void *input, NvU32 bytes) {
    // Native control only. A private kernel pipe performs actual fault-checked
    // user-buffer reads and writes in this process. It neither installs global
    // signal handlers nor bypasses page protections via /proc/self/mem.
    int descriptors[2];
    if (pipe(descriptors)) return NV_ERR_OPERATING_SYSTEM;
    NV_STATUS status = NV_OK;
    const long atomicBytes = fpathconf(descriptors[1], _PC_PIPE_BUF);
    if (atomicBytes <= 0 || fcntl(descriptors[0], F_SETFL, O_NONBLOCK) ||
        fcntl(descriptors[1], F_SETFL, O_NONBLOCK)) status = NV_ERR_OPERATING_SYSTEM;
    auto *to = static_cast<NvU8 *>(output);
    const auto *from = static_cast<const NvU8 *>(input);
    while (bytes && status == NV_OK) {
        const NvU32 maximum = atomicBytes > kCopyChunk ? kCopyChunk : static_cast<NvU32>(atomicBytes);
        const NvU32 chunk = bytes < maximum ? bytes : maximum;
        ssize_t written, received = 0;
        do { written = write(descriptors[1], from, chunk); } while (written < 0 && errno == EINTR);
        const int writeError = errno;
        if (written > 0) {
            do { received = read(descriptors[0], to, static_cast<size_t>(written)); }
            while (received < 0 && errno == EINTR);
        }
        const int readError = errno;
        if (written != chunk || received != chunk) {
            status = ((written < 0 && writeError != EFAULT) ||
                      (received < 0 && readError != EFAULT))
                ? NV_ERR_OPERATING_SYSTEM : NV_ERR_INVALID_ADDRESS;
            break;
        }
        to += chunk; from += chunk; bytes -= chunk;
    }
    const int firstClose = close(descriptors[0]);
    const int secondClose = close(descriptors[1]);
    return status == NV_OK && (firstClose || secondClose) ? NV_ERR_OPERATING_SYSTEM : status;
}
#endif
NV_STATUS copyUser(void *output, const void *input, NvU32 bytes, bool fromUser) {
    if (!bytes) return NV_OK;
    if (!S540DarwinInternal::ordinary()) return NV_ERR_INVALID_STATE;
    if (!validRange(output, bytes) || !validRange(input, bytes))
        return NV_ERR_INVALID_ADDRESS;
#if defined(KERNEL)
    // User addresses belong to the invoking task. A timer/work thread with
    // kernel_task is not a substitute for a retained userspace caller's map.
    if (current_task() == kernel_task) return NV_ERR_INVALID_STATE;
    auto *to = static_cast<NvU8 *>(output);
    const auto *from = static_cast<const NvU8 *>(input);
    while (bytes) {
        const NvU32 chunk = bytes < kCopyChunk ? bytes : kCopyChunk;
        const int status = fromUser
            ? copyin(static_cast<user_addr_t>(reinterpret_cast<NvUPtr>(from)), to, chunk)
            : copyout(from, static_cast<user_addr_t>(reinterpret_cast<NvUPtr>(to)), chunk);
        if (status) return NV_ERR_INVALID_ADDRESS;
        to += chunk; from += chunk; bytes -= chunk;
    }
    return NV_OK;
#else
    (void)fromUser;
    return nativeCopy(output, input, bytes);
#endif
}
}
extern "C" NV_STATUS NV_API_CALL s540Darwin_os_memcpy_from_user(
    void *output, const void *input, NvU32 bytes) {
    return copyUser(output, input, bytes, true);
}
extern "C" NV_STATUS NV_API_CALL s540Darwin_os_memcpy_to_user(
    void *output, const void *input, NvU32 bytes) {
    return copyUser(output, input, bytes, false);
}
