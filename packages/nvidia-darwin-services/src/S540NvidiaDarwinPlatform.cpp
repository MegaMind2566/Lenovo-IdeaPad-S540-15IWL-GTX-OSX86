// SPDX-License-Identifier: MIT
#include "S540NvidiaDarwinInternal.hpp"
namespace {
alignas(NvU32) NvU32 liveObjects;
#if !defined(KERNEL)
thread_local bool nativeInterruptContext;
thread_local bool nativeInterruptsEnabled = true;
alignas(NvU32) NvU32 nextFailure;
#endif
}
namespace S540DarwinInternal {
bool ordinary() {
#if defined(KERNEL)
    return !ml_at_interrupt_context() && ml_get_interrupts_enabled();
#else
    return !nativeInterruptContext && nativeInterruptsEnabled;
#endif
}
bool interruptContext() {
#if defined(KERNEL)
    return ml_at_interrupt_context();
#else
    return nativeInterruptContext;
#endif
}
NvU64 identity() {
#if defined(KERNEL)
    return thread_tid(current_thread());
#elif defined(__APPLE__)
    uint64_t tid = 0;
    if (pthread_threadid_np(nullptr, &tid) != 0) violation("native thread identity");
    return tid;
#else
    static_assert(sizeof(pthread_t) <= sizeof(NvU64), "Native pthread identity must fit.");
    NvU64 tid = 0;
    const auto thread = pthread_self();
    std::memcpy(&tid, &thread, sizeof(thread));
    return tid;
#endif
}
NvU64 monotonic() {
#if defined(KERNEL)
    uint64_t ticks = 0, ns = 0;
    clock_get_uptime(&ticks);
    absolutetime_to_nanoseconds(ticks, &ns);
    return ns;
#else
    struct timespec time{};
    if (clock_gettime(CLOCK_MONOTONIC, &time) != 0) violation("native monotonic clock");
    return NvU64(time.tv_sec) * 1000000000ULL + NvU64(time.tv_nsec);
#endif
}
bool fail(NvU32 point) {
#if defined(KERNEL)
    (void)point;
    return false;
#else
    NvU32 expected = point;
    return __atomic_compare_exchange_n(&nextFailure, &expected, NvU32{0}, false, __ATOMIC_RELAXED, __ATOMIC_RELAXED);
#endif
}
void *allocate(NvU32 size) {
    if (!ordinary() || fail(1)) return nullptr;
#if defined(KERNEL)
    void *result = IOMalloc(size);
    if (result != nullptr) bzero(result, size);
    return result;
#else
    return std::calloc(1, size);
#endif
}
void deallocate(void *object, NvU32 size) {
#if defined(KERNEL)
    IOFree(object, size);
#else
    (void)size;
    std::free(object);
#endif
}
void account(NvS32 delta) {
    if (delta > 0) __atomic_fetch_add(&liveObjects, NvU32(delta), __ATOMIC_RELAXED);
    else __atomic_fetch_sub(&liveObjects, NvU32(-delta), __ATOMIC_RELAXED);
}
[[noreturn]] void violation(const char *message) {
#if defined(KERNEL)
    panic("NVIDIA Darwin services contract violated: %s", message);
#else
    std::fprintf(stderr, "NVIDIA Darwin services contract violated: %s\n", message);
    std::abort();
#endif
}
bool Guard::init() {
    if (fail(2)) return false;
#if defined(KERNEL)
    value = IOSimpleLockAlloc();
    return value != nullptr;
#else
    pthread_mutexattr_t attributes;
    if (pthread_mutexattr_init(&attributes) != 0) return false;
    int result = pthread_mutexattr_settype(&attributes, PTHREAD_MUTEX_ERRORCHECK);
    if (result == 0) result = pthread_mutex_init(&value, &attributes);
    const int disposed = pthread_mutexattr_destroy(&attributes);
    if (result != 0) return false;
    if (disposed != 0) violation("native attributes cleanup");
    if (pthread_cond_init(&changed, nullptr) != 0) {
        if (pthread_mutex_destroy(&value) != 0) violation("native guard unwind");
        return false;
    }
    return true;
#endif
}
void Guard::dispose() {
#if defined(KERNEL)
    IOSimpleLockFree(value);
#else
    if (pthread_cond_destroy(&changed) != 0 || pthread_mutex_destroy(&value) != 0)
        violation("native guard destruction before quiescence");
#endif
}
NvU64 Guard::lock() {
#if defined(KERNEL)
    return static_cast<NvU64>(IOSimpleLockLockDisableInterrupt(value));
#else
    const NvU64 prior = nativeInterruptsEnabled ? 1 : 0;
    nativeInterruptsEnabled = false;
    if (pthread_mutex_lock(&value) != 0) violation("native guard lock");
    return prior;
#endif
}
void Guard::unlock(NvU64 token) {
#if defined(KERNEL)
    IOSimpleLockUnlockEnableInterrupt(value, static_cast<IOInterruptState>(token));
#else
    if (token > 1 || nativeInterruptsEnabled || pthread_mutex_unlock(&value) != 0)
        violation("native guard release token");
    nativeInterruptsEnabled = token != 0;
#endif
}
bool Guard::wait(void *event, NvU64 &token, bool interruptible) {
#if defined(KERNEL)
    // Assert under the state lock, release it and restore interrupts before
    // sleeping. A wake in between cancels the asserted wait: no lost wakeup.
    wait_result_t result = assert_wait(static_cast<event_t>(event), interruptible ? THREAD_ABORTSAFE : THREAD_UNINT);
    unlock(token);
    if (result == THREAD_WAITING) result = thread_block(THREAD_CONTINUE_NULL);
    token = lock();
    return result == THREAD_AWAKENED;
#else
    (void)event;
    (void)interruptible; // POSIX condition waits are not a Darwin signal model.
    if (token != 1) violation("native sleep with interrupts disabled");
    nativeInterruptsEnabled = true;
    const int result = pthread_cond_wait(&changed, &value);
    nativeInterruptsEnabled = false;
    return result == 0;
#endif
}
void Guard::wake(void *event) {
#if defined(KERNEL)
    (void)thread_wakeup_prim(static_cast<event_t>(event), FALSE, THREAD_AWAKENED);
#else
    (void)event;
    if (pthread_cond_broadcast(&changed) != 0) violation("native wakeup");
#endif
}
}
extern "C" NvU32 s540DarwinLiveObjects(void) { return __atomic_load_n(&liveObjects, __ATOMIC_RELAXED); }
#if !defined(KERNEL)
void S540NvidiaDarwinServicesNative::failNext(Failure failure) {
    __atomic_store_n(&nextFailure, static_cast<NvU32>(failure), __ATOMIC_RELAXED);
}
void S540NvidiaDarwinServicesNative::setContext(bool interrupt, bool enabled) {
    nativeInterruptContext = interrupt;
    nativeInterruptsEnabled = enabled;
}
#endif
