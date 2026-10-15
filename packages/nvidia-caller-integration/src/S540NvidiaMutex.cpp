// SPDX-License-Identifier: MIT
#include "S540NvidiaMutex.hpp"

#if defined(KERNEL)
#include <IOKit/IOLib.h>
#include <IOKit/IOLocks.h>
#include <kern/sched_prim.h>
#include <machine/machine_routines.h>
#else
#include <cerrno>
#include <cstdlib>
#include <pthread.h>
#endif

static_assert(NVCPU_IS_X86_64 && sizeof(void *) == 8,
              "The NVPort mutex caller adapter supports Intel x86_64 only.");

namespace {

alignas(4) NvU32 gLiveObjects;
static_assert(__atomic_always_lock_free(sizeof(gLiveObjects), nullptr),
              "Object accounting must not introduce a runtime lock.");
#if !defined(KERNEL)
alignas(4) NvU32 gNextNativeFailure;
#endif

bool ordinaryThreadContext() {
#if defined(KERNEL)
    return !ml_at_interrupt_context() && ml_get_interrupts_enabled();
#else
    return true;
#endif
}

struct Mutex {
#if defined(KERNEL)
    IOSimpleLock *guard;
#else
    pthread_mutex_t guard;
    pthread_cond_t changed;
#endif
    bool available;
};

} // namespace

NvU32 S540NvidiaMutex::liveObjects() {
    return __atomic_load_n(&gLiveObjects, __ATOMIC_RELAXED);
}

#if !defined(KERNEL)
void S540NvidiaMutexNative::failNextAllocation(Failure failure) {
    __atomic_store_n(&gNextNativeFailure, static_cast<NvU32>(failure),
                     __ATOMIC_RELAXED);
}
#endif

extern "C" NV_STATUS NV_API_CALL os_alloc_mutex(void **output) {
    if (output == nullptr)
        return NV_ERR_INVALID_ARGUMENT;
    *output = nullptr;
    if (!ordinaryThreadContext())
        return NV_ERR_INVALID_REQUEST;

#if defined(KERNEL)
    auto *mutex = static_cast<Mutex *>(IOMalloc(sizeof(Mutex)));
    if (mutex == nullptr)
        return NV_ERR_NO_MEMORY;
    mutex->guard = IOSimpleLockAlloc();
    if (mutex->guard == nullptr) {
        IOFree(mutex, sizeof(Mutex));
        return NV_ERR_NO_MEMORY;
    }
#else
    const auto failure = static_cast<S540NvidiaMutexNative::Failure>(
        __atomic_exchange_n(&gNextNativeFailure, NvU32{0}, __ATOMIC_RELAXED));
    if (failure == S540NvidiaMutexNative::Failure::Storage)
        return NV_ERR_NO_MEMORY;
    auto *mutex = static_cast<Mutex *>(std::malloc(sizeof(Mutex)));
    if (mutex == nullptr)
        return NV_ERR_NO_MEMORY;
    int result = failure == S540NvidiaMutexNative::Failure::Guard
        ? ENOMEM : pthread_mutex_init(&mutex->guard, nullptr);
    if (result != 0) {
        std::free(mutex);
        return result == ENOMEM || result == EAGAIN
            ? NV_ERR_NO_MEMORY : NV_ERR_OPERATING_SYSTEM;
    }
    result = failure == S540NvidiaMutexNative::Failure::Condition
        ? ENOMEM : pthread_cond_init(&mutex->changed, nullptr);
    if (result != 0) {
        (void)pthread_mutex_destroy(&mutex->guard);
        std::free(mutex);
        return result == ENOMEM || result == EAGAIN
            ? NV_ERR_NO_MEMORY : NV_ERR_OPERATING_SYSTEM;
    }
#endif
    mutex->available = true;
    __atomic_fetch_add(&gLiveObjects, NvU32{1}, __ATOMIC_RELAXED);
    *output = mutex;
    return NV_OK;
}

extern "C" void NV_API_CALL os_free_mutex(void *handle) {
    if (handle == nullptr || !ordinaryThreadContext())
        return;
    auto *mutex = static_cast<Mutex *>(handle);
    // Quiescence is a caller lifetime precondition, not inferred from the token.
#if defined(KERNEL)
    IOSimpleLockFree(mutex->guard);
    IOFree(mutex, sizeof(Mutex));
#else
    // A destroy failure means the quiescence precondition was violated. Keep
    // the storage; this is not a recoverable or reusable object state.
    if (pthread_cond_destroy(&mutex->changed) != 0)
        return;
    if (pthread_mutex_destroy(&mutex->guard) != 0)
        return;
    std::free(mutex);
#endif
    __atomic_fetch_sub(&gLiveObjects, NvU32{1}, __ATOMIC_RELAXED);
}

extern "C" NV_STATUS NV_API_CALL os_acquire_mutex(void *handle) {
    if (handle == nullptr)
        return NV_ERR_INVALID_ARGUMENT;
    if (!ordinaryThreadContext())
        return NV_ERR_INVALID_REQUEST;
    auto *mutex = static_cast<Mutex *>(handle);
#if defined(KERNEL)
    IOInterruptState interruptState = IOSimpleLockLockDisableInterrupt(mutex->guard);
    while (!mutex->available) {
        // Register the wait while holding the state guard. A release cannot
        // publish availability and signal between the token check and this
        // assertion. A wake before thread_block cancels the asserted wait.
        const wait_result_t asserted = assert_wait(static_cast<event_t>(mutex), THREAD_UNINT);
        IOSimpleLockUnlockEnableInterrupt(mutex->guard, interruptState);
        wait_result_t result = asserted;
        if (asserted == THREAD_WAITING)
            result = thread_block(THREAD_CONTINUE_NULL);
        if (result != THREAD_AWAKENED)
            return NV_ERR_OPERATING_SYSTEM;
        interruptState = IOSimpleLockLockDisableInterrupt(mutex->guard);
    }
    mutex->available = false;
    IOSimpleLockUnlockEnableInterrupt(mutex->guard, interruptState);
    return NV_OK;
#else
    if (pthread_mutex_lock(&mutex->guard) != 0)
        return NV_ERR_OPERATING_SYSTEM;
    while (!mutex->available) {
        const int result = pthread_cond_wait(&mutex->changed, &mutex->guard);
        if (result != 0) {
            (void)pthread_mutex_unlock(&mutex->guard);
            return NV_ERR_OPERATING_SYSTEM;
        }
    }
    mutex->available = false;
    return pthread_mutex_unlock(&mutex->guard) == 0
        ? NV_OK : NV_ERR_OPERATING_SYSTEM;
#endif
}

extern "C" NV_STATUS NV_API_CALL os_cond_acquire_mutex(void *handle) {
    if (handle == nullptr)
        return NV_ERR_INVALID_ARGUMENT;
    if (!ordinaryThreadContext())
        return NV_ERR_INVALID_REQUEST;
    auto *mutex = static_cast<Mutex *>(handle);
#if defined(KERNEL)
    const IOInterruptState state = IOSimpleLockLockDisableInterrupt(mutex->guard);
    const bool acquired = mutex->available;
    if (acquired)
        mutex->available = false;
    IOSimpleLockUnlockEnableInterrupt(mutex->guard, state);
    return acquired ? NV_OK : NV_ERR_TIMEOUT_RETRY;
#else
    // This native functional backend may sleep on its short state guard. It
    // does not establish the kernel conditional-acquire no-sleep guarantee.
    if (pthread_mutex_lock(&mutex->guard) != 0)
        return NV_ERR_OPERATING_SYSTEM;
    const bool acquired = mutex->available;
    if (acquired)
        mutex->available = false;
    if (pthread_mutex_unlock(&mutex->guard) != 0)
        return NV_ERR_OPERATING_SYSTEM;
    return acquired ? NV_OK : NV_ERR_TIMEOUT_RETRY;
#endif
}

extern "C" void NV_API_CALL os_release_mutex(void *handle) {
    if (handle == nullptr || !ordinaryThreadContext())
        return;
    auto *mutex = static_cast<Mutex *>(handle);
#if defined(KERNEL)
    const IOInterruptState state = IOSimpleLockLockDisableInterrupt(mutex->guard);
    mutex->available = true;
    IOSimpleLockUnlockEnableInterrupt(mutex->guard, state);
    // Wake every token waiter: they recheck availability under the guard, and
    // exactly one consumes the token. No sleepable lock is used on release.
    (void)thread_wakeup_prim(static_cast<event_t>(mutex), FALSE, THREAD_AWAKENED);
#else
    if (pthread_mutex_lock(&mutex->guard) != 0)
        return;
    mutex->available = true;
    (void)pthread_mutex_unlock(&mutex->guard);
    (void)pthread_cond_broadcast(&mutex->changed);
#endif
}
