// SPDX-License-Identifier: MIT
#include "S540NvidiaDarwinInternal.hpp"
#if defined(KERNEL)
#include <kern/thread_call.h>
#endif
using namespace S540DarwinInternal;
struct os_work_queue {
    Guard guard;
    S540DarwinWorkAction action;
    void *context;
    void *items[64];
    NvU32 head, count, unloadFlushes;
    NvU64 accepted, completed, workerThread;
    bool accepting, scheduled;
#if defined(KERNEL)
    thread_call_t call;
#else
    pthread_t worker;
    bool nativeExit;
#endif
};
namespace {
os_work_queue *globalQueue;
os_work_queue *resolve(os_work_queue *queue) {
    return queue != nullptr ? queue : __atomic_load_n(&globalQueue, __ATOMIC_ACQUIRE);
}
void execute(os_work_queue *queue) {
    auto token = queue->guard.lock();
    queue->workerThread = identity();
    while (queue->count != 0) {
        void *data = queue->items[queue->head];
        queue->items[queue->head] = nullptr;
        queue->head = (queue->head + 1) % 64;
        --queue->count;
        queue->guard.unlock(token);
        queue->action(queue->context, data);
        token = queue->guard.lock();
        ++queue->completed;
        queue->guard.wake(queue);
    }
    queue->workerThread = 0;
    queue->scheduled = false;
    queue->guard.wake(queue);
    queue->guard.unlock(token);
}
#if defined(KERNEL)
void workCallback(thread_call_param_t queue, thread_call_param_t) { execute(static_cast<os_work_queue *>(queue)); }
#else
void *workCallback(void *argument) {
    auto *queue = static_cast<os_work_queue *>(argument);
    auto token = queue->guard.lock();
    for (;;) {
        while (!queue->scheduled && !queue->nativeExit)
            if (!queue->guard.wait(queue, token, false)) violation("worker wait");
        if (queue->nativeExit) break;
        queue->guard.unlock(token);
        execute(queue);
        token = queue->guard.lock();
    }
    queue->guard.unlock(token);
    return nullptr;
}
#endif
}
extern "C" NV_STATUS s540DarwinWorkQueueCreate(S540DarwinWorkAction action, void *context, os_work_queue **output) {
    if (output == nullptr || action == nullptr) return NV_ERR_INVALID_ARGUMENT;
    *output = nullptr;
    if (!ordinary()) return NV_ERR_INVALID_REQUEST;
    auto *queue = create<os_work_queue>();
    if (queue == nullptr) return NV_ERR_NO_MEMORY;
    queue->action = action;
    queue->context = context;
    queue->accepting = true;
#if defined(KERNEL)
    queue->call = thread_call_allocate_with_options(workCallback, queue, THREAD_CALL_PRIORITY_KERNEL, THREAD_CALL_OPTIONS_ONCE);
    if (queue->call == nullptr) { destroy(queue); return NV_ERR_NO_MEMORY; }
#else
    if (fail(3) || pthread_create(&queue->worker, nullptr, workCallback, queue) != 0) {
        destroy(queue);
        return NV_ERR_NO_MEMORY;
    }
#endif
    *output = queue;
    return NV_OK;
}
extern "C" NV_STATUS s540DarwinBindGlobalWorkQueue(os_work_queue *queue) {
    if (queue == nullptr || !ordinary()) return NV_ERR_INVALID_ARGUMENT;
    os_work_queue *expected = nullptr;
    return __atomic_compare_exchange_n(&globalQueue, &expected, queue, false, __ATOMIC_RELEASE, __ATOMIC_RELAXED)
        ? NV_OK : NV_ERR_IN_USE;
}
extern "C" NV_STATUS s540DarwinUnbindGlobalWorkQueue(os_work_queue *queue) {
    if (queue == nullptr || !ordinary()) return NV_ERR_INVALID_ARGUMENT;
    auto *expected = queue;
    return __atomic_compare_exchange_n(&globalQueue, &expected, static_cast<os_work_queue *>(nullptr), false, __ATOMIC_ACQ_REL, __ATOMIC_RELAXED)
        ? NV_OK : NV_ERR_INVALID_STATE;
}
extern "C" NV_STATUS NV_API_CALL s540Darwin_os_queue_work_item(os_work_queue *argument, void *data) {
    auto *queue = resolve(argument);
    if (queue == nullptr) return NV_ERR_NOT_READY;
    const auto token = queue->guard.lock();
    if (!queue->accepting) { queue->guard.unlock(token); return NV_ERR_NOT_READY; }
    if (queue->count == 64 || queue->accepted == ~NvU64{0}) {
        queue->guard.unlock(token);
        return NV_ERR_NO_MEMORY;
    }
    queue->items[(queue->head + queue->count) % 64] = data;
    ++queue->count;
    ++queue->accepted;
    if (!queue->scheduled) {
        queue->scheduled = true;
#if defined(KERNEL)
        // Preallocated call and ring: enqueue never allocates or sleeps.
        (void)thread_call_enter(queue->call);
#else
        queue->guard.wake(queue);
#endif
    }
    queue->guard.unlock(token);
    return NV_OK;
}
extern "C" NV_STATUS NV_API_CALL s540Darwin_os_flush_work_queue(os_work_queue *argument, NvBool unload) {
    if (!ordinary()) return NV_ERR_ILLEGAL_ACTION;
    auto *queue = resolve(argument);
    if (queue == nullptr) return NV_ERR_NOT_READY;
    auto token = queue->guard.lock();
    if (queue->workerThread == identity()) { queue->guard.unlock(token); return NV_ERR_ILLEGAL_ACTION; }
    const NvU64 target = queue->accepted;
    if (unload) ++queue->unloadFlushes;
    while (queue->completed < target) {
        if (!queue->guard.wait(queue, token, false)) {
            if (unload) --queue->unloadFlushes;
            queue->guard.unlock(token);
            return NV_ERR_OPERATING_SYSTEM;
        }
    }
    if (unload) --queue->unloadFlushes;
    queue->guard.unlock(token);
    return NV_OK;
}
extern "C" NvBool NV_API_CALL s540Darwin_os_is_queue_flush_ongoing(os_work_queue *argument) {
    auto *queue = resolve(argument);
    if (queue == nullptr) violation("workqueue flush state requires a bound queue");
    const auto token = queue->guard.lock();
    const bool flushing = queue->unloadFlushes != 0;
    queue->guard.unlock(token);
    return flushing ? NV_TRUE : NV_FALSE;
}
extern "C" NV_STATUS s540DarwinWorkQueueStop(os_work_queue *queue) {
    if (queue == nullptr) return NV_ERR_INVALID_ARGUMENT;
    if (!ordinary()) return NV_ERR_INVALID_REQUEST;
    auto token = queue->guard.lock();
    if (queue->workerThread == identity()) { queue->guard.unlock(token); return NV_ERR_ILLEGAL_ACTION; }
    queue->accepting = false;
    queue->guard.unlock(token);
    const auto status = s540Darwin_os_flush_work_queue(queue, NV_TRUE);
    if (status != NV_OK) return status;
#if defined(KERNEL)
    // The drain can finish just before the callback returns. Wait for that
    // return before freeing callback-owned queue storage.
    (void)thread_call_cancel_wait(queue->call);
#endif
    return NV_OK;
}
extern "C" void s540DarwinWorkQueueDestroy(os_work_queue *queue) {
    if (queue == nullptr) return;
    if (__atomic_load_n(&globalQueue, __ATOMIC_ACQUIRE) == queue)
        violation("global workqueue must be unbound before destruction");
    if (s540DarwinWorkQueueStop(queue) != NV_OK) violation("workqueue destruction context");
#if defined(KERNEL)
    if (!thread_call_free(queue->call)) violation("workqueue call still pending");
#else
    const auto token = queue->guard.lock();
    queue->nativeExit = true;
    queue->guard.wake(queue);
    queue->guard.unlock(token);
    if (pthread_join(queue->worker, nullptr) != 0) violation("workqueue join");
#endif
    if (queue->count != 0 || queue->accepted != queue->completed || queue->workerThread != 0)
        violation("workqueue accepted data was not drained");
    destroy(queue);
}
