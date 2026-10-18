// SPDX-License-Identifier: MIT
#include "S540NvidiaGspDispatcher.hpp"
#include "../../nvidia-darwin-services/src/S540NvidiaDarwinInternal.hpp"
#if defined(KERNEL)
#include <mach/thread_act.h>
#endif

namespace S540NvidiaGspBootstrap {
using namespace S540DarwinInternal;
struct Dispatcher::Impl {
    Guard guard;
    struct Request { bool completed; NV_STATUS status; };
    struct Item { NvU32 command; Request *request; };
    static constexpr NvU32 capacity = 16;
    Item items[capacity];
    NvU32 head, count;
    Action action;
    void *context;
    Snapshot state;
#if defined(KERNEL)
    thread_t worker;
#else
    pthread_t worker;
#endif
    static void execute(Impl *self) {
        auto token = self->guard.lock();
        self->state.workerThread = identity();
        self->state.started = true;
        self->guard.wake(self);
        for (;;) {
            while (!self->count && self->state.accepting)
                if (!self->guard.wait(self, token, false)) violation("dispatcher worker wait");
            if (!self->count) break;
            const Item item = self->items[self->head];
            self->items[self->head] = Item{};
            self->head = (self->head + 1) % capacity;
            --self->count;
            self->state.pending = self->count;
            self->guard.unlock(token);
            const NV_STATUS status = self->action(self->context, item.command);
            token = self->guard.lock();
            ++self->state.completed;
            if (item.request) {
                item.request->status = status;
                item.request->completed = true;
            } else {
                self->state.lastPostedStatus = status;
                if (status != NV_OK) ++self->state.postedFailures;
            }
            self->guard.wake(self);
        }
        self->state.workerFinished = true;
        self->guard.wake(self);
        self->guard.unlock(token);
        // No owner/queue/action access after publishing workerFinished. XNU
        // self-termination never returns; its thread object retains the kernel
        // reference independently of the start caller's explicit reference.
    }
#if defined(KERNEL)
    static void entry(void *argument, wait_result_t) {
        execute(static_cast<Impl *>(argument));
        (void)thread_terminate(current_thread());
        violation("dispatcher kernel thread termination returned");
    }
#else
    static void *entry(void *argument) { execute(static_cast<Impl *>(argument)); return nullptr; }
#endif
    NV_STATUS enqueue(NvU32 command, Request *request) {
        const auto token = guard.lock();
        if (!state.accepting) { guard.unlock(token); return NV_ERR_NOT_READY; }
        if (count == capacity || state.accepted == ~NvU64{0}) {
            guard.unlock(token); return NV_ERR_INSUFFICIENT_RESOURCES;
        }
        items[(head + count) % capacity] = Item{command, request};
        ++count; ++state.accepted; state.pending = count;
        guard.wake(this);
        guard.unlock(token);
        return NV_OK;
    }
};
Dispatcher::Dispatcher() : impl_(nullptr) {}
Dispatcher::~Dispatcher() {
    // An unjoined dispatcher must keep its callback argument alive. The owner
    // must call stop, exclude callers and only then destroy the facade.
    if (impl_ && impl_->state.stopped) destroy(impl_);
}
NV_STATUS Dispatcher::start(Action action, void *context) {
    if (!ordinary()) return NV_ERR_INVALID_STATE;
    if (impl_) return NV_ERR_STATE_IN_USE;
    if (!action || !context) return NV_ERR_INVALID_ARGUMENT;
    auto *self = create<Impl>();
    if (!self) return NV_ERR_NO_MEMORY;
    self->action = action; self->context = context; self->state.accepting = true;
#if defined(KERNEL)
    const bool started = kernel_thread_start(Impl::entry, self, &self->worker) == KERN_SUCCESS;
#else
    const bool started = !fail(3) && pthread_create(&self->worker, nullptr, Impl::entry, self) == 0;
#endif
    if (!started) { destroy(self); return NV_ERR_INSUFFICIENT_RESOURCES; }
    impl_ = self;
    auto token = self->guard.lock();
    while (!self->state.started)
        if (!self->guard.wait(self, token, false)) violation("dispatcher startup wait");
    self->guard.unlock(token);
    return NV_OK;
}
NV_STATUS Dispatcher::invoke(NvU32 command) {
    if (!ordinary() || !impl_) return NV_ERR_INVALID_STATE;
    auto *self = impl_;
    auto token = self->guard.lock();
    const bool recursive = self->state.workerThread == identity();
    self->guard.unlock(token);
    if (recursive) return NV_ERR_ILLEGAL_ACTION;
    Impl::Request request{};
    const NV_STATUS status = self->enqueue(command, &request);
    if (status != NV_OK) return status;
    token = self->guard.lock();
    // Accepted stack requests cannot leave early: the worker still owns their
    // addresses until completion, even if stop closes further admission.
    while (!request.completed)
        if (!self->guard.wait(self, token, false)) violation("dispatcher invocation wait");
    self->guard.unlock(token);
    return request.status;
}
NV_STATUS Dispatcher::post(NvU32 command) {
    return impl_ ? impl_->enqueue(command, nullptr) : NV_ERR_NOT_READY;
}
NV_STATUS Dispatcher::stop() {
    if (!ordinary()) return NV_ERR_INVALID_STATE;
    if (!impl_) return NV_OK;
    auto *self = impl_;
    auto token = self->guard.lock();
    if (self->state.stopped) { self->guard.unlock(token); return NV_OK; }
    if (self->state.workerThread == identity()) {
        self->guard.unlock(token); return NV_ERR_ILLEGAL_ACTION;
    }
    self->state.accepting = false;
    self->guard.wake(self);
    while (!self->state.workerFinished)
        if (!self->guard.wait(self, token, false)) violation("dispatcher shutdown wait");
    self->guard.unlock(token);
#if defined(KERNEL)
    thread_deallocate(self->worker);
#else
    if (pthread_join(self->worker, nullptr)) violation("dispatcher worker join");
#endif
    token = self->guard.lock();
    self->state.stopped = true;
    self->guard.unlock(token);
    return NV_OK;
}
Dispatcher::Snapshot Dispatcher::snapshot() const {
    if (!impl_) return Snapshot{};
    const auto token = impl_->guard.lock();
    const auto result = impl_->state;
    impl_->guard.unlock(token);
    return result;
}
}
