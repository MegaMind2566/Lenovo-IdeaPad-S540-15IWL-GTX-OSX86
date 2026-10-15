// SPDX-License-Identifier: MIT
#include "S540NvidiaSpinlock.hpp"

#if defined(KERNEL)
#include <IOKit/IOLib.h>
#include <IOKit/IOLocks.h>
#include <libkern/libkern.h>
#include <machine/machine_routines.h>
#else
#include <atomic>
#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <pthread.h>
#endif

static_assert(NVCPU_IS_X86_64 && sizeof(void *) == 8,
              "The NVPort spinlock adapter supports Intel x86_64 only.");

namespace {

alignas(NvU32) NvU32 liveObjectCount = 0;
static_assert(__atomic_always_lock_free(sizeof(NvU32), nullptr),
              "Spinlock object accounting must not acquire an implicit lock.");

#if !defined(KERNEL)
thread_local bool nativeInterruptContext = false;
thread_local bool nativeInterruptsEnabled = true;
std::atomic<NvU32> nativeNextFailure{0};
#endif

[[noreturn]] void contractFailure(const char *operation) {
#if defined(KERNEL)
    panic("NVIDIA spinlock contract violated: %s", operation);
#else
    std::fprintf(stderr, "NVIDIA spinlock contract violated: %s\n", operation);
    std::abort();
#endif
}

bool ordinaryThreadContext() {
#if defined(KERNEL)
    return !ml_at_interrupt_context() && ml_get_interrupts_enabled();
#else
    return !nativeInterruptContext && nativeInterruptsEnabled;
#endif
}

struct Spinlock {
#if defined(KERNEL)
    IOSimpleLock *guard;
#else
    pthread_mutex_t guard;
#endif
};

#if defined(KERNEL)
static_assert(sizeof(IOInterruptState) <= sizeof(NvU64),
              "The NVIDIA token must preserve the complete interrupt state.");
#else
NV_STATUS allocationStatus(int result) {
    return result == ENOMEM || result == EAGAIN
        ? NV_ERR_NO_MEMORY : NV_ERR_OPERATING_SYSTEM;
}
#endif

} // namespace

extern "C" NV_STATUS NV_API_CALL os_alloc_spinlock(void **output) {
    if (output == nullptr)
        return NV_ERR_INVALID_ARGUMENT;
    *output = nullptr;
    if (!ordinaryThreadContext())
        return NV_ERR_INVALID_REQUEST;

#if defined(KERNEL)
    auto *lock = static_cast<Spinlock *>(IOMalloc(sizeof(Spinlock)));
    if (lock == nullptr)
        return NV_ERR_NO_MEMORY;
    lock->guard = IOSimpleLockAlloc();
    if (lock->guard == nullptr) {
        IOFree(lock, sizeof(Spinlock));
        return NV_ERR_NO_MEMORY;
    }
#else
    const auto failure = static_cast<S540NvidiaSpinlockNative::Failure>(
        nativeNextFailure.exchange(0, std::memory_order_relaxed));
    if (failure == S540NvidiaSpinlockNative::Failure::Storage)
        return NV_ERR_NO_MEMORY;
    auto *lock = static_cast<Spinlock *>(std::malloc(sizeof(Spinlock)));
    if (lock == nullptr)
        return NV_ERR_NO_MEMORY;
    if (failure == S540NvidiaSpinlockNative::Failure::Initialization) {
        std::free(lock);
        return NV_ERR_NO_MEMORY;
    }
    // Native error checking catches owner/recursive misuse. The Darwin kernel
    // branch remains a true simple lock and relies on its caller contract.
    pthread_mutexattr_t attributes;
    int result = pthread_mutexattr_init(&attributes);
    if (result != 0) {
        std::free(lock);
        return allocationStatus(result);
    }
    result = pthread_mutexattr_settype(&attributes, PTHREAD_MUTEX_ERRORCHECK);
    if (result == 0)
        result = pthread_mutex_init(&lock->guard, &attributes);
    const int destroyed = pthread_mutexattr_destroy(&attributes);
    if (result != 0) {
        std::free(lock);
        return allocationStatus(result);
    }
    if (destroyed != 0) {
        if (pthread_mutex_destroy(&lock->guard) != 0)
            contractFailure("allocation cleanup");
        std::free(lock);
        return NV_ERR_OPERATING_SYSTEM;
    }
#endif
    (void)__atomic_add_fetch(&liveObjectCount, 1U, __ATOMIC_RELAXED);
    *output = lock;
    return NV_OK;
}

extern "C" void NV_API_CALL os_free_spinlock(void *handle) {
    if (handle == nullptr)
        return;
    if (!ordinaryThreadContext())
        contractFailure("destruction context");
    auto *lock = static_cast<Spinlock *>(handle);
    // The caller has ended all uses; a released lock alone proves no lifetime.
#if defined(KERNEL)
    IOSimpleLockFree(lock->guard);
    IOFree(lock, sizeof(Spinlock));
#else
    if (pthread_mutex_destroy(&lock->guard) != 0)
        contractFailure("destruction before quiescence");
    std::free(lock);
#endif
    (void)__atomic_sub_fetch(&liveObjectCount, 1U, __ATOMIC_RELAXED);
}

extern "C" NvU64 NV_API_CALL os_acquire_spinlock(void *handle) {
    if (handle == nullptr)
        contractFailure("null acquire");
    auto *lock = static_cast<Spinlock *>(handle);
#if defined(KERNEL)
    const IOInterruptState prior = IOSimpleLockLockDisableInterrupt(lock->guard);
    return static_cast<NvU64>(prior);
#else
    const NvU64 prior = nativeInterruptsEnabled ? 1U : 0U;
    nativeInterruptsEnabled = false;
    if (pthread_mutex_lock(&lock->guard) != 0)
        contractFailure("native acquisition");
    return prior;
#endif
}

extern "C" void NV_API_CALL os_release_spinlock(void *handle, NvU64 prior) {
    if (handle == nullptr)
        contractFailure("null release");
    auto *lock = static_cast<Spinlock *>(handle);
#if defined(KERNEL)
    IOSimpleLockUnlockEnableInterrupt(lock->guard, static_cast<IOInterruptState>(prior));
#else
    if (prior > 1U || nativeInterruptsEnabled)
        contractFailure("native interrupt-state token");
    if (pthread_mutex_unlock(&lock->guard) != 0)
        contractFailure("native release");
    nativeInterruptsEnabled = prior != 0;
#endif
}

namespace S540NvidiaSpinlock {
NvU32 liveObjects() { return __atomic_load_n(&liveObjectCount, __ATOMIC_RELAXED); }
} // namespace S540NvidiaSpinlock

#if !defined(KERNEL)
namespace S540NvidiaSpinlockNative {
void failNextAllocation(Failure failure) {
    nativeNextFailure.store(static_cast<NvU32>(failure), std::memory_order_relaxed);
}
void setContext(bool interruptContext, bool interruptsEnabled) {
    nativeInterruptContext = interruptContext;
    nativeInterruptsEnabled = interruptsEnabled;
}
bool interruptsEnabled() { return nativeInterruptsEnabled; }
bool contextAllowed() { return ordinaryThreadContext(); }
NvU32 liveObjects() { return S540NvidiaSpinlock::liveObjects(); }
} // namespace S540NvidiaSpinlockNative
#endif
