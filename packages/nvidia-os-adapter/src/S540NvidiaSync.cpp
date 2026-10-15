// SPDX-License-Identifier: MIT
#include "S540NvidiaSync.hpp"

#if defined(KERNEL)
#include <IOKit/IOLocks.h>
#include <machine/machine_routines.h>
#else
#include <cerrno>
#include <cstdlib>
#include <pthread.h>
#endif

static_assert(NVCPU_IS_X86_64 && sizeof(void *) == 8,
              "The mutex adapter supports Intel x86_64 only.");

namespace {

bool ordinaryThreadContext() {
#if defined(KERNEL)
    // These guards reject interrupt handlers and disabled-interrupt callers.
    // They do not prove that no spin lock is held. That remains a precondition.
    return !ml_at_interrupt_context() && ml_get_interrupts_enabled();
#else
    return true;
#endif
}

#if defined(KERNEL)
using NativeMutex = IOLock;
#else
using NativeMutex = pthread_mutex_t;
#endif

} // namespace

extern "C" NV_STATUS NV_API_CALL os_alloc_mutex(void **mutex) {
    if (mutex == nullptr)
        return NV_ERR_INVALID_ARGUMENT;
    *mutex = nullptr;
    if (!ordinaryThreadContext())
        return NV_ERR_INVALID_REQUEST;

#if defined(KERNEL)
    *mutex = IOLockAlloc();
    return *mutex != nullptr ? NV_OK : NV_ERR_NO_MEMORY;
#else
    auto *native = static_cast<NativeMutex *>(std::malloc(sizeof(NativeMutex)));
    if (native == nullptr)
        return NV_ERR_NO_MEMORY;
    const int result = pthread_mutex_init(native, nullptr);
    if (result != 0) {
        std::free(native);
        return result == ENOMEM || result == EAGAIN
            ? NV_ERR_NO_MEMORY : NV_ERR_OPERATING_SYSTEM;
    }
    *mutex = native;
    return NV_OK;
#endif
}

extern "C" void NV_API_CALL os_free_mutex(void *mutex) {
    if (mutex == nullptr || !ordinaryThreadContext())
        return;
    auto *native = static_cast<NativeMutex *>(mutex);
#if defined(KERNEL)
    IOLockFree(native);
#else
    // A nonzero result means the caller violated the no-owner/no-waiter
    // lifetime precondition. Do not free storage still used by a pthread lock.
    if (pthread_mutex_destroy(native) == 0)
        std::free(native);
#endif
}

extern "C" NV_STATUS NV_API_CALL os_acquire_mutex(void *mutex) {
    if (mutex == nullptr)
        return NV_ERR_INVALID_ARGUMENT;
    if (!ordinaryThreadContext())
        return NV_ERR_INVALID_REQUEST;
    auto *native = static_cast<NativeMutex *>(mutex);
#if defined(KERNEL)
    IOLockLock(native);
    return NV_OK;
#else
    return pthread_mutex_lock(native) == 0 ? NV_OK : NV_ERR_OPERATING_SYSTEM;
#endif
}

extern "C" NV_STATUS NV_API_CALL os_cond_acquire_mutex(void *mutex) {
    if (mutex == nullptr)
        return NV_ERR_INVALID_ARGUMENT;
    if (!ordinaryThreadContext())
        return NV_ERR_INVALID_REQUEST;
    auto *native = static_cast<NativeMutex *>(mutex);
#if defined(KERNEL)
    return IOLockTryLock(native) ? NV_OK : NV_ERR_TIMEOUT_RETRY;
#else
    const int result = pthread_mutex_trylock(native);
    if (result == 0)
        return NV_OK;
    return result == EBUSY ? NV_ERR_TIMEOUT_RETRY : NV_ERR_OPERATING_SYSTEM;
#endif
}

extern "C" void NV_API_CALL os_release_mutex(void *mutex) {
    if (mutex == nullptr || !ordinaryThreadContext())
        return;
    auto *native = static_cast<NativeMutex *>(mutex);
#if defined(KERNEL)
    IOLockUnlock(native);
#else
    // Owner-only release is an API precondition, as with IOLockUnlock.
    (void)pthread_mutex_unlock(native);
#endif
}
