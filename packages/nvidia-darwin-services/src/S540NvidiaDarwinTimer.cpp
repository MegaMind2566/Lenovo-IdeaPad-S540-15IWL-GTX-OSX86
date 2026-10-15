// SPDX-License-Identifier: MIT
#include "S540NvidiaDarwinInternal.hpp"
#if defined(KERNEL)
#include <kern/thread_call.h>
#else
#include <chrono>
#include <thread>
#endif
using namespace S540DarwinInternal;
struct S540DarwinTimer {
    Guard guard;
    S540DarwinTimerAction action;
    void *context;
    NvU64 deadline, callbackThread;
    bool armed, cancelling;
#if defined(KERNEL)
    thread_call_t call;
#else
    pthread_t worker;
    bool nativeExit;
#endif
};
namespace {
#if defined(KERNEL)
void schedule(S540DarwinTimer *timer) {
    uint64_t deadline = 0;
    nanoseconds_to_absolutetime(timer->deadline, &deadline);
    (void)thread_call_enter_delayed(timer->call, deadline);
}
#endif
void execute(S540DarwinTimer *timer) {
    auto token = timer->guard.lock();
    if (!timer->armed || timer->cancelling) { timer->guard.unlock(token); return; }
    if (monotonic() < timer->deadline) {
#if defined(KERNEL)
        // A previously dequeued invocation may race a later arm. It must
        // honor the current deadline, never fire the new timer early.
        schedule(timer);
#endif
        timer->guard.unlock(token);
        return;
    }
    timer->armed = false;
    timer->callbackThread = identity();
    timer->guard.unlock(token);
    timer->action(timer->context);
    token = timer->guard.lock();
    timer->callbackThread = 0;
    timer->guard.wake(timer);
    timer->guard.unlock(token);
}
#if defined(KERNEL)
void timerCallback(thread_call_param_t timer, thread_call_param_t) { execute(static_cast<S540DarwinTimer *>(timer)); }
#else
void *timerCallback(void *argument) {
    auto *timer = static_cast<S540DarwinTimer *>(argument);
    auto token = timer->guard.lock();
    for (;;) {
        while (!timer->armed && !timer->nativeExit)
            if (!timer->guard.wait(timer, token, false)) violation("native timer wait");
        if (timer->nativeExit) break;
        const NvU64 now = monotonic();
        const NvU64 remaining = timer->deadline > now ? timer->deadline - now : 0;
        timer->guard.unlock(token);
        if (remaining != 0) {
            // Functional userspace backend only. Polling is bounded to 1 ms
            // so cancel/join does not wait for a distant deadline.
            std::this_thread::sleep_for(std::chrono::nanoseconds(remaining > 1000000 ? 1000000 : remaining));
        } else execute(timer);
        token = timer->guard.lock();
    }
    timer->guard.unlock(token);
    return nullptr;
}
#endif
}
extern "C" NV_STATUS s540DarwinTimerCreate(S540DarwinTimerAction action, void *context, S540DarwinTimer **output) {
    if (output == nullptr || action == nullptr) return NV_ERR_INVALID_ARGUMENT;
    *output = nullptr;
    if (!ordinary()) return NV_ERR_INVALID_REQUEST;
    auto *timer = create<S540DarwinTimer>();
    if (timer == nullptr) return NV_ERR_NO_MEMORY;
    timer->action = action;
    timer->context = context;
#if defined(KERNEL)
    timer->call = thread_call_allocate_with_options(timerCallback, timer, THREAD_CALL_PRIORITY_KERNEL, THREAD_CALL_OPTIONS_ONCE);
    if (timer->call == nullptr) { destroy(timer); return NV_ERR_NO_MEMORY; }
#else
    if (fail(3) || pthread_create(&timer->worker, nullptr, timerCallback, timer) != 0) {
        destroy(timer);
        return NV_ERR_NO_MEMORY;
    }
#endif
    *output = timer;
    return NV_OK;
}
extern "C" NV_STATUS s540DarwinTimerArm(S540DarwinTimer *timer, NvU64 delay) {
    if (timer == nullptr) return NV_ERR_INVALID_ARGUMENT;
    const NvU64 now = monotonic();
    if (delay > ~NvU64{0} - now) return NV_ERR_INVALID_ARGUMENT;
    const auto token = timer->guard.lock();
    if (timer->cancelling) { timer->guard.unlock(token); return NV_ERR_IN_USE; }
    timer->deadline = now + delay;
    timer->armed = true;
#if defined(KERNEL)
    schedule(timer);
#else
    timer->guard.wake(timer);
#endif
    timer->guard.unlock(token);
    return NV_OK;
}
extern "C" NV_STATUS s540DarwinTimerCancel(S540DarwinTimer *timer) {
    if (timer == nullptr) return NV_ERR_INVALID_ARGUMENT;
    if (!ordinary()) return NV_ERR_INVALID_REQUEST;
    auto token = timer->guard.lock();
    if (timer->callbackThread == identity()) { timer->guard.unlock(token); return NV_ERR_ILLEGAL_ACTION; }
    if (timer->cancelling) { timer->guard.unlock(token); return NV_ERR_IN_USE; }
    timer->cancelling = true;
    timer->armed = false;
    timer->guard.unlock(token);
#if defined(KERNEL)
    (void)thread_call_cancel_wait(timer->call);
#endif
    token = timer->guard.lock();
    while (timer->callbackThread != 0)
        if (!timer->guard.wait(timer, token, false)) violation("timer cancellation wait");
    timer->cancelling = false;
    timer->guard.unlock(token);
    return NV_OK;
}
extern "C" void s540DarwinTimerDestroy(S540DarwinTimer *timer) {
    if (timer == nullptr) return;
    // All concurrent arm/cancel callers must have relinquished their object
    // references before destruction; cancel alone cannot prove that lifetime.
    if (s540DarwinTimerCancel(timer) != NV_OK) violation("timer destruction context");
#if defined(KERNEL)
    if (!thread_call_free(timer->call)) violation("timer call still pending");
#else
    const auto token = timer->guard.lock();
    timer->nativeExit = true;
    timer->guard.wake(timer);
    timer->guard.unlock(token);
    if (pthread_join(timer->worker, nullptr) != 0) violation("timer worker join");
#endif
    destroy(timer);
}
