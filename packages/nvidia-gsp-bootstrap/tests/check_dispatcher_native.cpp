// SPDX-License-Identifier: MIT
#include "../src/S540NvidiaGspDispatcher.hpp"
#include "../../nvidia-darwin-services/src/S540NvidiaDarwinServices.h"
#include <atomic>
#include <condition_variable>
#include <cstdio>
#include <cstdlib>
#include <mutex>
#include <thread>
#include <vector>
using namespace S540NvidiaGspBootstrap;
namespace {
NvU32 checks;
void expect(bool value, const char *message) {
    ++checks;
    if (!value) { std::fprintf(stderr, "Dispatcher: %s\n", message); std::abort(); }
}
struct Fixture {
    Dispatcher *dispatcher;
    std::atomic<NvU64> thread{0};
    std::atomic<NvU32> executions{0}, unstable{0};
    std::mutex lock;
    std::condition_variable changed;
    bool blocked = false, release = false;
    NV_STATUS recursive = NV_OK, selfStop = NV_OK;
    static NV_STATUS action(void *owner, NvU32 command) {
        auto &self = *static_cast<Fixture *>(owner);
        NvU64 tid = 0;
        if (s540Darwin_os_get_current_thread(&tid) != NV_OK || !tid ||
            !s540Darwin_os_semaphore_may_sleep()) ++self.unstable;
        NvU64 expected = 0;
        if (!self.thread.compare_exchange_strong(expected, tid) && expected != tid) ++self.unstable;
        ++self.executions;
        if (command == 2) return NV_ERR_NOT_SUPPORTED;
        if (command == 3) {
            std::unique_lock<std::mutex> guard(self.lock);
            self.blocked = true;
            self.changed.notify_all();
            self.changed.wait(guard, [&] { return self.release; });
        }
        if (command == 4) {
            self.recursive = self.dispatcher->invoke(1);
            self.selfStop = self.dispatcher->stop();
        }
        return NV_OK;
    }
};
}
int main() {
    using namespace S540NvidiaDarwinServicesNative;
    expect(s540DarwinLiveObjects() == 0, "clean entry");
    {
        Dispatcher dispatcher;
        Fixture fixture;
        fixture.dispatcher = &dispatcher;
        expect(dispatcher.invoke(1) == NV_ERR_INVALID_STATE, "unstarted sync refused");
        expect(dispatcher.post(1) == NV_ERR_NOT_READY, "unstarted async refused");
        expect(dispatcher.stop() == NV_OK, "empty stop idempotent");
        expect(dispatcher.start(nullptr, &fixture) == NV_ERR_INVALID_ARGUMENT, "callback required");
        expect(dispatcher.start(Fixture::action, nullptr) == NV_ERR_INVALID_ARGUMENT, "owner required");
        for (const auto fault : {Failure::Storage, Failure::Guard, Failure::Worker}) {
            failNext(fault);
            expect(dispatcher.start(Fixture::action, &fixture) != NV_OK, "startup acquisition failure");
            expect(s540DarwinLiveObjects() == 0, "failed start releases acquired storage");
        }
        setContext(true, false);
        expect(dispatcher.start(Fixture::action, &fixture) == NV_ERR_INVALID_STATE,
               "start requires sleeping context");
        setContext(false, true);
        expect(dispatcher.start(Fixture::action, &fixture) == NV_OK, "worker starts");
        expect(dispatcher.start(Fixture::action, &fixture) == NV_ERR_STATE_IN_USE, "duplicate start refused");
        NvU64 caller = 0;
        expect(s540Darwin_os_get_current_thread(&caller) == NV_OK, "caller thread captured");
        const auto started = dispatcher.snapshot();
        expect(started.started && started.accepting && started.workerThread &&
               started.workerThread != caller, "persistent ordinary worker is a separate thread");
        std::atomic<NvU32> failures{0};
        std::vector<std::thread> clients;
        for (NvU32 i = 0; i != 4; ++i) clients.emplace_back([&] {
            for (NvU32 n = 0; n != 100; ++n)
                if (dispatcher.invoke(1) != NV_OK) ++failures;
        });
        for (auto &client : clients) client.join();
        expect(failures == 0 && fixture.executions == 400, "concurrent synchronous results all delivered");
        expect(fixture.unstable == 0 && fixture.thread == started.workerThread,
               "all commands retain exact thread identity");
        expect(dispatcher.invoke(2) == NV_ERR_NOT_SUPPORTED, "actual action failure propagated");
        expect(dispatcher.invoke(4) == NV_OK && fixture.recursive == NV_ERR_ILLEGAL_ACTION &&
               fixture.selfStop == NV_ERR_ILLEGAL_ACTION, "worker cannot synchronously wait for itself");
        expect(dispatcher.post(2) == NV_OK && dispatcher.invoke(1) == NV_OK,
               "async command ordered before synchronous completion barrier");
        const auto failedPost = dispatcher.snapshot();
        expect(failedPost.postedFailures == 1 && failedPost.lastPostedStatus == NV_ERR_NOT_SUPPORTED,
               "async failure is retained as evidence");
        setContext(true, false);
        expect(dispatcher.invoke(1) == NV_ERR_INVALID_STATE, "sync call from IRQ refused");
        expect(dispatcher.stop() == NV_ERR_INVALID_STATE, "stop from IRQ retains resources");
        expect(dispatcher.post(3) == NV_OK, "preallocated async post accepted from IRQ fixture");
        setContext(false, true);
        {
            std::unique_lock<std::mutex> guard(fixture.lock);
            fixture.changed.wait(guard, [&] { return fixture.blocked; });
        }
        for (NvU32 i = 0; i != 16; ++i)
            expect(dispatcher.post(1) == NV_OK, "bounded pending command accepted");
        expect(dispatcher.post(1) == NV_ERR_INSUFFICIENT_RESOURCES, "full async ring refuses without losing work");
        expect(dispatcher.invoke(1) == NV_ERR_INSUFFICIENT_RESOURCES, "full synchronous ring refuses before publication");
        NV_STATUS stopStatus = NV_ERR_NOT_READY;
        std::thread stopper([&] { stopStatus = dispatcher.stop(); });
        while (dispatcher.snapshot().accepting) std::this_thread::yield();
        expect(dispatcher.post(1) == NV_ERR_NOT_READY, "shutdown closes async admission");
        expect(dispatcher.invoke(1) == NV_ERR_NOT_READY, "shutdown closes sync admission");
        expect(!dispatcher.snapshot().workerFinished, "shutdown waits for callback completion");
        {
            std::lock_guard<std::mutex> guard(fixture.lock);
            fixture.release = true;
            fixture.changed.notify_all();
        }
        stopper.join();
        expect(stopStatus == NV_OK, "blocked callback and queue drained before stop returns");
        const auto stopped = dispatcher.snapshot();
        expect(stopped.stopped && stopped.workerFinished && !stopped.accepting &&
               stopped.pending == 0 && stopped.accepted == stopped.completed,
               "every accepted action completes exactly once");
        expect(stopped.completed == fixture.executions && fixture.unstable == 0,
               "all command paths execute on the same worker");
        expect(dispatcher.stop() == NV_OK, "successful stop retry is idempotent");
        expect(dispatcher.start(Fixture::action, &fixture) == NV_ERR_STATE_IN_USE,
               "terminal dispatcher cannot silently replace its owner thread");
    }
    expect(s540DarwinLiveObjects() == 0, "all dispatcher ownership released");
    std::printf("{\"format\":1,\"component\":\"nvidia-gsp-dispatcher\","
        "\"status\":\"passed\",\"checks\":%u,\"failures\":0,"
        "\"execution\":\"native-user-space\",\"kernel_execution\":\"not_tested\","
        "\"gpu_access\":false,\"stable_owner_thread\":true,"
        "\"concurrent_sync_calls\":400,\"queue_capacity\":16,"
        "\"shutdown_drain_verified\":true,\"cleanup\":true}\n", checks);
}
