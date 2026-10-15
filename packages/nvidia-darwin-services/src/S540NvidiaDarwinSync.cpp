// SPDX-License-Identifier: MIT
#include "S540NvidiaDarwinServices.h"
#include "S540NvidiaDarwinInternal.hpp"

#if defined(KERNEL)
#include <kern/clock.h>
#include <kern/thread.h>
#else
#include <chrono>
#include <thread>
#include <time.h>
#endif

using namespace S540DarwinInternal;

namespace {
struct Semaphore {
    Guard guard;
    NvU32 value, waiters;
};
struct RwLock {
    Guard guard;
    NvU32 readers, readWaiters, writeWaiters;
    bool writer;
};
}
struct os_wait_queue {
    Guard guard;
    bool completed;
    NvU32 waiters;
};

extern "C" NV_STATUS NV_API_CALL s540Darwin_os_alloc_mutex(void **output) {
    if (output == nullptr) return NV_ERR_INVALID_ARGUMENT;
    *output = nullptr;
    if (!ordinary()) return NV_ERR_INVALID_REQUEST;
    auto *object = create<Semaphore>();
    if (object == nullptr) return NV_ERR_NO_MEMORY;
    object->value = 1;
    *output = object;
    return NV_OK;
}
extern "C" void NV_API_CALL s540Darwin_os_free_mutex(void *handle) {
    if (handle == nullptr) return;
    auto *object = static_cast<Semaphore *>(handle);
    if (!ordinary() || object->waiters != 0 || object->value != 1)
        violation("mutex destruction requires quiescence and released token");
    destroy(object);
}
extern "C" NV_STATUS NV_API_CALL s540Darwin_os_acquire_mutex(void *handle) {
    if (!ordinary()) return NV_ERR_INVALID_REQUEST;
    return s540Darwin_os_acquire_semaphore(handle);
}
extern "C" NV_STATUS NV_API_CALL s540Darwin_os_cond_acquire_mutex(void *handle) {
    if (!ordinary()) return NV_ERR_INVALID_REQUEST;
    return s540Darwin_os_cond_acquire_semaphore(handle);
}
extern "C" void NV_API_CALL s540Darwin_os_release_mutex(void *handle) {
    if (handle == nullptr) violation("null mutex release");
    auto *object = static_cast<Semaphore *>(handle);
    auto token = object->guard.lock();
    if (object->value != 0) violation("unbalanced mutex release");
    object->value = 1;
    object->guard.wake(object);
    object->guard.unlock(token);
}
extern "C" NV_STATUS NV_API_CALL s540Darwin_os_alloc_spinlock(void **output) {
    if (output == nullptr) return NV_ERR_INVALID_ARGUMENT;
    *output = nullptr;
    if (!ordinary()) return NV_ERR_INVALID_REQUEST;
    auto *object = create<GuardObject>();
    if (object == nullptr) return NV_ERR_NO_MEMORY;
    *output = object;
    return NV_OK;
}
extern "C" void NV_API_CALL s540Darwin_os_free_spinlock(void *handle) {
    if (handle == nullptr) return;
    if (!ordinary()) violation("spinlock destruction context");
    destroy(static_cast<GuardObject *>(handle));
}
extern "C" NvU64 NV_API_CALL s540Darwin_os_acquire_spinlock(void *handle) {
    if (handle == nullptr) violation("null spinlock acquire");
    return static_cast<GuardObject *>(handle)->guard.lock();
}
extern "C" void NV_API_CALL s540Darwin_os_release_spinlock(void *handle, NvU64 token) {
    if (handle == nullptr) violation("null spinlock release");
    static_cast<GuardObject *>(handle)->guard.unlock(token);
}
extern "C" void *NV_API_CALL s540Darwin_os_alloc_semaphore(NvU32 count) {
    if (!ordinary()) return nullptr;
    auto *object = create<Semaphore>();
    if (object != nullptr) object->value = count;
    return object;
}
extern "C" void NV_API_CALL s540Darwin_os_free_semaphore(void *handle) {
    if (handle == nullptr) return;
    auto *object = static_cast<Semaphore *>(handle);
    if (!ordinary() || object->waiters != 0) violation("semaphore destruction before quiescence");
    destroy(object);
}
extern "C" NV_STATUS NV_API_CALL s540Darwin_os_acquire_semaphore(void *handle) {
    if (handle == nullptr) return NV_ERR_INVALID_ARGUMENT;
    if (!ordinary()) return NV_ERR_INVALID_REQUEST;
    auto *object = static_cast<Semaphore *>(handle);
    auto token = object->guard.lock();
    while (object->value == 0) {
        ++object->waiters;
        const bool awakened = object->guard.wait(object, token, false);
        --object->waiters;
        if (!awakened) { object->guard.unlock(token); return NV_ERR_OPERATING_SYSTEM; }
    }
    --object->value;
    object->guard.unlock(token);
    return NV_OK;
}
extern "C" NV_STATUS NV_API_CALL s540Darwin_os_cond_acquire_semaphore(void *handle) {
    if (handle == nullptr) return NV_ERR_INVALID_ARGUMENT;
    auto *object = static_cast<Semaphore *>(handle);
    const auto token = object->guard.lock();
    const bool available = object->value != 0;
    if (available) --object->value;
    object->guard.unlock(token);
    return available ? NV_OK : NV_ERR_TIMEOUT_RETRY;
}
extern "C" NV_STATUS NV_API_CALL s540Darwin_os_release_semaphore(void *handle) {
    if (handle == nullptr) return NV_ERR_INVALID_ARGUMENT;
    auto *object = static_cast<Semaphore *>(handle);
    const auto token = object->guard.lock();
    if (object->value == ~NvU32{0}) { object->guard.unlock(token); return NV_ERR_INVALID_STATE; }
    ++object->value;
    object->guard.wake(object);
    object->guard.unlock(token);
    return NV_OK;
}
extern "C" void *NV_API_CALL s540Darwin_os_alloc_rwlock(void) {
    return ordinary() ? create<RwLock>() : nullptr;
}
extern "C" void NV_API_CALL s540Darwin_os_free_rwlock(void *handle) {
    if (handle == nullptr) return;
    auto *object = static_cast<RwLock *>(handle);
    if (!ordinary() || object->writer || object->readers || object->readWaiters || object->writeWaiters)
        violation("rwlock destruction before quiescence");
    destroy(object);
}
namespace {
NV_STATUS acquireRw(void *handle, bool write, bool conditional) {
    if (handle == nullptr) return NV_ERR_INVALID_ARGUMENT;
    if (!conditional && !ordinary()) return NV_ERR_INVALID_REQUEST;
    auto *object = static_cast<RwLock *>(handle);
    auto token = object->guard.lock();
    auto unavailable = [&]() {
        return object->writer || (write ? object->readers != 0 : object->writeWaiters != 0);
    };
    if (conditional && unavailable()) { object->guard.unlock(token); return NV_ERR_TIMEOUT_RETRY; }
    auto &waiters = write ? object->writeWaiters : object->readWaiters;
    ++waiters;
    while (unavailable()) {
        if (!object->guard.wait(object, token, false)) {
            --waiters;
            object->guard.wake(object);
            object->guard.unlock(token);
            return NV_ERR_OPERATING_SYSTEM;
        }
    }
    --waiters;
    if (write) object->writer = true;
    else {
        if (object->readers == ~NvU32{0}) violation("rwlock reader overflow");
        ++object->readers;
    }
    object->guard.unlock(token);
    return NV_OK;
}
void releaseRw(void *handle, bool write) {
    if (handle == nullptr) violation("null rwlock release");
    auto *object = static_cast<RwLock *>(handle);
    const auto token = object->guard.lock();
    if (write) {
        if (!object->writer) violation("unbalanced rwlock writer release");
        object->writer = false;
    } else {
        if (object->readers == 0) violation("unbalanced rwlock reader release");
        --object->readers;
    }
    object->guard.wake(object);
    object->guard.unlock(token);
}
}
extern "C" NV_STATUS NV_API_CALL s540Darwin_os_acquire_rwlock_read(void *p) { return acquireRw(p, false, false); }
extern "C" NV_STATUS NV_API_CALL s540Darwin_os_acquire_rwlock_write(void *p) { return acquireRw(p, true, false); }
extern "C" NV_STATUS NV_API_CALL s540Darwin_os_cond_acquire_rwlock_read(void *p) { return acquireRw(p, false, true); }
extern "C" NV_STATUS NV_API_CALL s540Darwin_os_cond_acquire_rwlock_write(void *p) { return acquireRw(p, true, true); }
extern "C" void NV_API_CALL s540Darwin_os_release_rwlock_read(void *p) { releaseRw(p, false); }
extern "C" void NV_API_CALL s540Darwin_os_release_rwlock_write(void *p) { releaseRw(p, true); }
extern "C" NV_STATUS NV_API_CALL s540Darwin_os_alloc_wait_queue(os_wait_queue **output) {
    if (output == nullptr) return NV_ERR_INVALID_ARGUMENT;
    *output = nullptr;
    if (!ordinary()) return NV_ERR_INVALID_REQUEST;
    *output = create<os_wait_queue>();
    return *output == nullptr ? NV_ERR_NO_MEMORY : NV_OK;
}
extern "C" void NV_API_CALL s540Darwin_os_free_wait_queue(os_wait_queue *object) {
    if (object == nullptr) return;
    if (!ordinary() || object->waiters != 0) violation("waitqueue destruction before quiescence");
    destroy(object);
}
namespace {
void waitCompletion(os_wait_queue *object, bool interruptible) {
    if (object == nullptr || !ordinary()) violation("waitqueue wait context or handle");
    auto token = object->guard.lock();
    while (!object->completed) {
        ++object->waiters;
        const bool awakened = object->guard.wait(object, token, interruptible);
        --object->waiters;
        if (!awakened && interruptible) break;
        if (!awakened) violation("uninterruptible wait failed");
    }
    object->guard.unlock(token);
}
}
extern "C" void NV_API_CALL s540Darwin_os_wait_uninterruptible(os_wait_queue *object) { waitCompletion(object, false); }
extern "C" void NV_API_CALL s540Darwin_os_wait_interruptible(os_wait_queue *object) { waitCompletion(object, true); }
extern "C" void NV_API_CALL s540Darwin_os_wake_up(os_wait_queue *object) {
    if (object == nullptr) violation("null waitqueue wake");
    const auto token = object->guard.lock();
    object->completed = true; // Linux complete_all is sticky, not a consumed token.
    object->guard.wake(object);
    object->guard.unlock(token);
}
extern "C" NvBool NV_API_CALL s540Darwin_os_semaphore_may_sleep(void) { return ordinary() ? NV_TRUE : NV_FALSE; }
extern "C" NvBool NV_API_CALL s540Darwin_os_is_isr(void) { return interruptContext() ? NV_TRUE : NV_FALSE; }
extern "C" NV_STATUS NV_API_CALL s540Darwin_os_get_current_thread(NvU64 *output) {
    if (output == nullptr) return NV_ERR_INVALID_ARGUMENT;
    *output = interruptContext() ? 0 : identity();
    return NV_OK;
}
extern "C" NV_STATUS NV_API_CALL s540Darwin_os_get_system_time(NvU32 *seconds, NvU32 *micros) {
    if (seconds == nullptr || micros == nullptr) return NV_ERR_INVALID_ARGUMENT;
#if defined(KERNEL)
    clock_sec_t sec = 0;
    clock_usec_t usec = 0;
    clock_get_calendar_microtime(&sec, &usec);
    *seconds = static_cast<NvU32>(sec);
    *micros = static_cast<NvU32>(usec);
#else
    struct timespec now{};
    if (clock_gettime(CLOCK_REALTIME, &now) != 0) return NV_ERR_OPERATING_SYSTEM;
    *seconds = static_cast<NvU32>(now.tv_sec);
    *micros = static_cast<NvU32>(now.tv_nsec / 1000);
#endif
    return NV_OK;
}
extern "C" NvU64 NV_API_CALL s540Darwin_os_get_monotonic_time_ns_hr(void) { return monotonic(); }
extern "C" NvU64 NV_API_CALL s540Darwin_os_get_monotonic_time_ns(void) { return monotonic(); }
extern "C" NvU64 NV_API_CALL s540Darwin_os_get_monotonic_tick_resolution_ns(void) {
#if defined(KERNEL)
    mach_timebase_info_data_t info{};
    clock_timebase_info(&info);
    return info.denom == 0 ? 0 : (NvU64(info.numer) + info.denom - 1) / info.denom;
#else
    struct timespec resolution{};
    if (clock_getres(CLOCK_MONOTONIC, &resolution) != 0) return 0;
    return NvU64(resolution.tv_sec) * 1000000000ULL + NvU64(resolution.tv_nsec);
#endif
}
extern "C" NV_STATUS NV_API_CALL s540Darwin_os_delay(NvU32 milliseconds) {
    if (!ordinary()) return NV_ERR_INVALID_REQUEST;
#if defined(KERNEL)
    IOSleep(milliseconds);
#else
    std::this_thread::sleep_for(std::chrono::milliseconds(milliseconds));
#endif
    return NV_OK;
}
extern "C" NV_STATUS NV_API_CALL s540Darwin_os_delay_us(NvU32 microseconds) {
    if (!ordinary()) return NV_ERR_INVALID_REQUEST;
#if defined(KERNEL)
    // Avoid long busy waits. Sub-millisecond tail matches IODelay's contract.
    if (microseconds >= 1000) IOSleep(microseconds / 1000);
    if (microseconds % 1000 != 0) IODelay(microseconds % 1000);
#else
    std::this_thread::sleep_for(std::chrono::microseconds(microseconds));
#endif
    return NV_OK;
}
