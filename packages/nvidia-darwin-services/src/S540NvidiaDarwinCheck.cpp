// SPDX-License-Identifier: MIT
#include "S540NvidiaDarwinServices.h"
namespace {
void work(void *context, void *) { __atomic_fetch_add(static_cast<NvU32 *>(context), NvU32{1}, __ATOMIC_RELAXED); }
void timer(void *context) { __atomic_fetch_add(static_cast<NvU32 *>(context), NvU32{1}, __ATOMIC_RELAXED); }
}
S540NvidiaDarwinServices::Result S540NvidiaDarwinServices::check() {
    Result result{};
    const NvU32 initialObjects = s540DarwinLiveObjects();
    auto expect = [&](bool condition) { ++result.checks; if (!condition) ++result.failures; return condition; };
    result.context = expect(s540Darwin_os_semaphore_may_sleep() == NV_TRUE && s540Darwin_os_is_isr() == NV_FALSE);
    NvU64 thread = 0;
    result.context = expect(s540Darwin_os_get_current_thread(&thread) == NV_OK && thread != 0) && result.context;
    NvU32 seconds = 0, micros = 0;
    result.context = expect(s540Darwin_os_get_system_time(&seconds, &micros) == NV_OK && seconds != 0 && micros < 1000000) && result.context;
    const NvU64 before = s540Darwin_os_get_monotonic_time_ns_hr();
    result.context = expect(s540Darwin_os_delay_us(1000) == NV_OK) && result.context;
    result.context = expect(s540Darwin_os_get_monotonic_time_ns_hr() >= before && s540Darwin_os_get_monotonic_tick_resolution_ns() != 0) && result.context;
    if (!result.context) { result.cleanup = expect(s540DarwinLiveObjects() == initialObjects); return result; }
    const NvU32 syncStart = result.failures;
    void *mutex = nullptr, *spin = nullptr;
    expect(s540Darwin_os_alloc_mutex(&mutex) == NV_OK && mutex != nullptr);
    if (mutex != nullptr) {
        expect(s540Darwin_os_acquire_mutex(mutex) == NV_OK);
        expect(s540Darwin_os_cond_acquire_mutex(mutex) == NV_ERR_TIMEOUT_RETRY);
        s540Darwin_os_release_mutex(mutex);
        expect(s540Darwin_os_cond_acquire_mutex(mutex) == NV_OK);
        s540Darwin_os_release_mutex(mutex);
        s540Darwin_os_free_mutex(mutex);
    }
    expect(s540Darwin_os_alloc_spinlock(&spin) == NV_OK && spin != nullptr);
    if (spin != nullptr) {
        const NvU64 prior = s540Darwin_os_acquire_spinlock(spin);
        const bool cannotSleep = s540Darwin_os_semaphore_may_sleep() == NV_FALSE;
        s540Darwin_os_release_spinlock(spin, prior);
        expect(cannotSleep && s540Darwin_os_semaphore_may_sleep() == NV_TRUE);
        s540Darwin_os_free_spinlock(spin);
    }
    void *semaphore = s540Darwin_os_alloc_semaphore(0);
    expect(semaphore != nullptr);
    if (semaphore != nullptr) {
        expect(s540Darwin_os_cond_acquire_semaphore(semaphore) == NV_ERR_TIMEOUT_RETRY);
        expect(s540Darwin_os_release_semaphore(semaphore) == NV_OK);
        expect(s540Darwin_os_acquire_semaphore(semaphore) == NV_OK);
        s540Darwin_os_free_semaphore(semaphore);
    }
    void *rwlock = s540Darwin_os_alloc_rwlock();
    expect(rwlock != nullptr);
    if (rwlock != nullptr) {
        expect(s540Darwin_os_acquire_rwlock_read(rwlock) == NV_OK);
        expect(s540Darwin_os_cond_acquire_rwlock_read(rwlock) == NV_OK);
        expect(s540Darwin_os_cond_acquire_rwlock_write(rwlock) == NV_ERR_TIMEOUT_RETRY);
        s540Darwin_os_release_rwlock_read(rwlock);
        s540Darwin_os_release_rwlock_read(rwlock);
        expect(s540Darwin_os_acquire_rwlock_write(rwlock) == NV_OK);
        expect(s540Darwin_os_cond_acquire_rwlock_read(rwlock) == NV_ERR_TIMEOUT_RETRY);
        s540Darwin_os_release_rwlock_write(rwlock);
        s540Darwin_os_free_rwlock(rwlock);
    }
    os_wait_queue *completion = nullptr;
    expect(s540Darwin_os_alloc_wait_queue(&completion) == NV_OK && completion != nullptr);
    if (completion != nullptr) {
        s540Darwin_os_wake_up(completion);
        s540Darwin_os_wait_uninterruptible(completion);
        s540Darwin_os_wait_interruptible(completion);
        expect(true); // Both waits returned after the same sticky complete_all.
        s540Darwin_os_free_wait_queue(completion);
    }
    result.synchronization = result.failures == syncStart;
    const NvU32 workStart = result.failures;
    os_work_queue *queue = nullptr;
    NvU32 completed = 0;
    expect(s540DarwinWorkQueueCreate(work, &completed, &queue) == NV_OK && queue != nullptr);
    if (queue != nullptr) {
        expect(s540Darwin_os_queue_work_item(queue, nullptr) == NV_OK);
        expect(s540Darwin_os_flush_work_queue(queue, NV_FALSE) == NV_OK);
        expect(__atomic_load_n(&completed, __ATOMIC_RELAXED) == 1);
        expect(s540DarwinWorkQueueStop(queue) == NV_OK);
        expect(s540Darwin_os_queue_work_item(queue, nullptr) == NV_ERR_NOT_READY);
        s540DarwinWorkQueueDestroy(queue);
    }
    result.workQueue = result.failures == workStart;
    const NvU32 timerStart = result.failures;
    S540DarwinTimer *oneShot = nullptr;
    NvU32 fired = 0;
    expect(s540DarwinTimerCreate(timer, &fired, &oneShot) == NV_OK && oneShot != nullptr);
    if (oneShot != nullptr) {
        expect(s540DarwinTimerArm(oneShot, 1000000) == NV_OK);
        for (NvU32 attempt = 0; attempt < 200 && __atomic_load_n(&fired, __ATOMIC_RELAXED) == 0; ++attempt)
            (void)s540Darwin_os_delay(1);
        expect(s540DarwinTimerCancel(oneShot) == NV_OK);
        expect(__atomic_load_n(&fired, __ATOMIC_RELAXED) == 1);
        expect(s540DarwinTimerArm(oneShot, 60000000000ULL) == NV_OK);
        expect(s540DarwinTimerCancel(oneShot) == NV_OK);
        expect(__atomic_load_n(&fired, __ATOMIC_RELAXED) == 1);
        s540DarwinTimerDestroy(oneShot);
    }
    result.timer = result.failures == timerStart;
    result.cleanup = expect(s540DarwinLiveObjects() == initialObjects);
    return result;
}
