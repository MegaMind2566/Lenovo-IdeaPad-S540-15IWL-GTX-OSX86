// SPDX-License-Identifier: MIT
// These are the actual transformed production KERNEL bodies, not a second
// implementation of work/timer lifecycle. Only exported IOKit is simulated.
#define KERNEL 1
#include "S540NvidiaDarwinWork.cpp"
#include "S540NvidiaDarwinTimer.cpp"
#include <future>
#include <iostream>

namespace {
int checks=0;
void check(bool result,const char *message) {
    ++checks;
    if (!result) throw std::runtime_error(message);
}
template<class Predicate> void until(Predicate predicate,const char *message) {
    const auto end=std::chrono::steady_clock::now()+std::chrono::seconds(4);
    while (!predicate()) {
        if (std::chrono::steady_clock::now()>end) throw std::runtime_error(message);
        std::this_thread::yield();
    }
}
void clean() { check(!mock::live && !mock::services,"resources leaked"); }
void noTimerAction(void *p) { ++*static_cast<std::atomic<int> *>(p); }
void noWorkAction(void *p,void *) { ++*static_cast<std::atomic<int> *>(p); }
struct Blocking {
    std::atomic<bool> entered{false}, release{false};
    std::atomic<int> calls{0};
};
void blockTimer(void *p) {
    auto &state=*static_cast<Blocking *>(p);
    ++state.calls; state.entered=true;
    until([&]{return state.release.load();},"blocked timer never released");
}
void blockWork(void *p,void *) { blockTimer(p); }
void allocationFailures() {
    for (int failure=1;failure<=5;++failure) {
        mock::step=0; mock::failAt=failure;
        S540DarwinTimer *timer=reinterpret_cast<S540DarwinTimer *>(1);
        check(s540DarwinTimerCreate(noTimerAction,nullptr,&timer)==NV_ERR_NO_MEMORY,"timer allocation failure");
        check(timer==nullptr,"timer failure published output"); clean();
        mock::step=0;
        os_work_queue *queue=reinterpret_cast<os_work_queue *>(1);
        check(s540DarwinWorkQueueCreate(noWorkAction,nullptr,&queue)==NV_ERR_NO_MEMORY,"work allocation failure");
        check(queue==nullptr,"work failure published output"); clean();
    }
    mock::failAt=0;
}
void pendingAndDequeuedCancellation() {
    std::atomic<int> calls{0}; S540DarwinTimer *timer=nullptr;
    check(s540DarwinTimerCreate(noTimerAction,&calls,&timer)==NV_OK,"create timer");
    check(s540DarwinTimerArm(timer,1000000000)==NV_OK,"arm future timer");
    check(s540DarwinTimerCancel(timer)==NV_OK,"cancel pending timer");
    check(calls==0,"pending cancellation invoked action");
    auto *event=IOTimerEventSource::latest;
    event->pauseAfterDequeue(true);
    check(s540DarwinTimerArm(timer,0)==NV_OK,"arm dequeued timer");
    until([&]{return event->hasDequeued();},"timer did not dequeue");
    check(s540DarwinTimerCancel(timer)==NV_OK,"cancel dequeued timer");
    event->pauseAfterDequeue(false);
    check(s540DarwinTimerArm(timer,0)==NV_OK,"reuse cancelled timer");
    until([&]{return calls==1;},"reused timer did not run");
    check(s540DarwinTimerCancel(timer)==NV_OK,"drain reused timer");
    const int before=mock::delivered;
    s540DarwinTimerDestroy(timer);
    check(mock::delivered==before,"action after timer destruction"); clean();
}
void runningCancellation() {
    Blocking state; S540DarwinTimer *timer=nullptr;
    check(s540DarwinTimerCreate(blockTimer,&state,&timer)==NV_OK,"create blocking timer");
    check(s540DarwinTimerArm(timer,0)==NV_OK,"arm blocking timer");
    until([&]{return state.entered.load();},"timer action did not enter");
    auto cancellation=std::async(std::launch::async,[&]{return s540DarwinTimerCancel(timer);});
    until([&]{ auto t=timer->guard.lock(); bool c=timer->cancelling; timer->guard.unlock(t); return c; },"cancel did not latch");
    check(cancellation.wait_for(std::chrono::milliseconds(20))==std::future_status::timeout,"cancel returned during callback");
    check(s540DarwinTimerArm(timer,0)==NV_ERR_IN_USE,"rearm during cancel admitted");
    state.release=true;
    check(cancellation.get()==NV_OK,"running cancellation failed");
    check(state.calls==1,"running cancellation duplicated action");
    s540DarwinTimerDestroy(timer); clean();
}
void replacementAndSelfCancellation() {
    struct State { S540DarwinTimer *timer=nullptr; std::atomic<int> calls{0},self{0}; } state;
    auto action=+[](void *p) {
        auto &s=*static_cast<State *>(p);
        if (++s.calls==1) {
            s.self=s540DarwinTimerCancel(s.timer);
            if (s540DarwinTimerArm(s.timer,0)!=NV_OK) throw std::runtime_error("callback rearm failed");
        }
    };
    check(s540DarwinTimerCreate(action,&state,&state.timer)==NV_OK,"create rearm timer");
    check(s540DarwinTimerArm(state.timer,1000000000)==NV_OK,"arm replaced timer");
    check(s540DarwinTimerArm(state.timer,0)==NV_OK,"replace timer");
    until([&]{return state.calls==2;},"callback did not rearm");
    check(state.self==NV_ERR_ILLEGAL_ACTION,"self cancel admitted");
    s540DarwinTimerDestroy(state.timer); clean();
}
void workDrain() {
    Blocking state; os_work_queue *queue=nullptr;
    check(s540DarwinWorkQueueCreate(blockWork,&state,&queue)==NV_OK,"create blocking queue");
    check(s540Darwin_os_queue_work_item(queue,nullptr)==NV_OK,"queue blocking item");
    until([&]{return state.entered.load();},"worker did not enter");
    auto stop=std::async(std::launch::async,[&]{return s540DarwinWorkQueueStop(queue);});
    until([&]{auto t=queue->guard.lock(); bool c=!queue->accepting; queue->guard.unlock(t); return c;},"stop did not close admission");
    check(stop.wait_for(std::chrono::milliseconds(20))==std::future_status::timeout,"stop returned during callback");
    check(s540Darwin_os_queue_work_item(queue,nullptr)==NV_ERR_NOT_READY,"stopped queue accepted work");
    state.release=true;
    check(stop.get()==NV_OK,"worker stop failed");
    check(state.calls==1,"worker callback lost or duplicated");
    s540DarwinWorkQueueDestroy(queue); clean();
}
void concurrentInterruptProducers() {
    std::atomic<int> calls{0}; os_work_queue *queue=nullptr;
    check(s540DarwinWorkQueueCreate(noWorkAction,&calls,&queue)==NV_OK,"create producer queue");
    std::vector<std::thread> producers;
    for (int p=0;p<4;++p) producers.emplace_back([&] {
        mock::interrupt=true;
        for (int i=0;i<500;++i) {
            NV_STATUS status;
            while ((status=s540Darwin_os_queue_work_item(queue,nullptr))==NV_ERR_NO_MEMORY) std::this_thread::yield();
            if (status!=NV_OK) throw std::runtime_error("producer admission failed");
        }
        mock::interrupt=false;
    });
    for (auto &thread:producers) thread.join();
    check(s540Darwin_os_flush_work_queue(queue,NV_TRUE)==NV_OK,"concurrent flush failed");
    check(calls==2000,"concurrent work lost or duplicated");
    s540DarwinWorkQueueDestroy(queue); clean();
}
void callbackReturnBoundary() {
    os_work_queue *queue=nullptr;
    auto action=+[](void *,void *) {
        mock::blockUnlockThread=S540DarwinInternal::identity();
    };
    check(s540DarwinWorkQueueCreate(action,nullptr,&queue)==NV_OK,"create callback-boundary queue");
    mock::unlockPaused=false; mock::releaseUnlock=false;
    check(s540Darwin_os_queue_work_item(queue,nullptr)==NV_OK,"queue callback-boundary item");
    until([&]{return mock::unlockPaused.load();},"callback did not reach published-idle gap");
    {
        auto token=queue->guard.lock();
        check(queue->completed==queue->accepted && !queue->workerThread && !queue->scheduled,
            "fixture did not expose actual logical-idle/return gap");
        queue->guard.unlock(token);
    }
    auto stop=std::async(std::launch::async,[&]{return s540DarwinWorkQueueStop(queue);});
    check(stop.wait_for(std::chrono::milliseconds(20))==std::future_status::timeout,
        "stop trusted idle flags before production callback returned");
    mock::releaseUnlock=true;
    check(stop.get()==NV_OK,"callback-boundary drain failed");
    s540DarwinWorkQueueDestroy(queue); clean();
}
void schedulingDoesNotAcquireGate() {
    std::atomic<int> calls{0}; os_work_queue *queue=nullptr;
    check(s540DarwinWorkQueueCreate(noWorkAction,&calls,&queue)==NV_OK,"create gate-order queue");
    auto *event=IOTimerEventSource::latest;
    event->loop->gate.lock();
    auto enqueue=std::async(std::launch::async,[&] {
        mock::interrupt=true;
        return s540Darwin_os_queue_work_item(queue,nullptr);
    });
    const bool ready=enqueue.wait_for(std::chrono::milliseconds(100))==std::future_status::ready;
    event->loop->gate.unlock();
    check(ready,"interrupt enqueue acquired sleeping workloop gate");
    check(enqueue.get()==NV_OK,"enqueue while gate held failed");
    s540DarwinWorkQueueDestroy(queue); clean();
    S540DarwinTimer *timer=nullptr;
    check(s540DarwinTimerCreate(noTimerAction,&calls,&timer)==NV_OK,"create gate-order timer");
    event=IOTimerEventSource::latest;
    event->loop->gate.lock();
    auto arm=std::async(std::launch::async,[&] { mock::interrupt=true; return s540DarwinTimerArm(timer,0); });
    const bool armed=arm.wait_for(std::chrono::milliseconds(100))==std::future_status::ready;
    event->loop->gate.unlock();
    check(armed,"interrupt arm acquired sleeping workloop gate");
    check(arm.get()==NV_OK,"arm while gate held failed");
    s540DarwinTimerDestroy(timer); clean();
}
void selfStop() {
    struct State { os_work_queue *queue=nullptr; std::atomic<int> status{0}; } state;
    auto action=+[](void *p,void *) {
        auto &s=*static_cast<State *>(p);
        s.status=s540DarwinWorkQueueStop(s.queue);
    };
    check(s540DarwinWorkQueueCreate(action,&state,&state.queue)==NV_OK,"create self-stop queue");
    check(s540Darwin_os_queue_work_item(state.queue,nullptr)==NV_OK,"queue self-stop work");
    check(s540Darwin_os_flush_work_queue(state.queue,NV_TRUE)==NV_OK,"flush self-stop work");
    check(state.status==NV_ERR_ILLEGAL_ACTION,"self stop admitted");
    s540DarwinWorkQueueDestroy(state.queue); clean();
}
void failuresRetainAndRetry() {
    std::atomic<int> calls{0}; S540DarwinTimer *timer=nullptr;
    check(s540DarwinTimerCreate(noTimerAction,&calls,&timer)==NV_OK,"create retry timer");
    const int live=mock::live;
    mock::failDrain=true;
    check(s540DarwinTimerCancel(timer)==NV_ERR_OPERATING_SYSTEM,"drain failure hidden");
    check(mock::live==live && mock::services==1,"drain failure freed timer");
    check(s540DarwinTimerCancel(timer)==NV_OK,"retry cancellation failed");
    mock::failRemove=true;
    check(!timer->call.retire(),"retirement failure hidden");
    check(mock::live==live,"retirement failure freed callback owner");
    s540DarwinTimerDestroy(timer); clean();
    os_work_queue *queue=nullptr;
    check(s540DarwinWorkQueueCreate(noWorkAction,&calls,&queue)==NV_OK,"create retry queue");
    mock::failDrain=true;
    check(s540DarwinWorkQueueStop(queue)==NV_ERR_OPERATING_SYSTEM,"stop failure hidden");
    check(s540Darwin_os_queue_work_item(queue,nullptr)==NV_ERR_NOT_READY,"failed stop reopened queue");
    check(s540DarwinWorkQueueStop(queue)==NV_OK,"retry stop failed");
    s540DarwinWorkQueueDestroy(queue); clean();
}
#if S540_TEST_COMPOSED_SERVICES
void composedPolicyRefusals() {
    std::atomic<int> calls{0}; S540DarwinTimer *timer=nullptr; os_work_queue *queue=nullptr;
    mock::backendConstructAllowed=false;
    check(s540DarwinTimerCreate(noTimerAction,&calls,&timer)==NV_ERR_NOT_READY && !timer,
        "composed timer constructor bypassed backend policy");
    check(s540DarwinWorkQueueCreate(noWorkAction,&calls,&queue)==NV_ERR_NOT_READY && !queue,
        "composed work constructor bypassed backend policy");
    clean(); mock::backendConstructAllowed=true;
    check(s540DarwinTimerCreate(noTimerAction,&calls,&timer)==NV_OK,"composed retained timer create");
    const int timerOwners=mock::live;
    mock::backendFinalizeAllowed=false;
    s540DarwinTimerDestroy(timer);
    check(mock::live==timerOwners && mock::services==1,"composed timer retention bypassed");
    mock::backendFinalizeAllowed=true;
    s540DarwinTimerDestroy(timer); clean();
    check(s540DarwinWorkQueueCreate(noWorkAction,&calls,&queue)==NV_OK,"composed retained queue create");
    const int queueOwners=mock::live;
    mock::backendFinalizeAllowed=false;
    s540DarwinWorkQueueDestroy(queue);
    check(mock::live==queueOwners && mock::services==1,"composed queue retention bypassed");
    mock::backendFinalizeAllowed=true;
    s540DarwinWorkQueueDestroy(queue); clean();
    check(mock::timerReturnedHooks>0,"composed timer returned hook removed");
}
#endif
}
int main() {
    try {
        allocationFailures(); pendingAndDequeuedCancellation(); runningCancellation();
        replacementAndSelfCancellation(); workDrain(); concurrentInterruptProducers();
        callbackReturnBoundary(); schedulingDoesNotAcquireGate(); selfStop(); failuresRetainAndRetry();
#if S540_TEST_COMPOSED_SERVICES
        composedPolicyRefusals();
#endif
        check(mock::gateUnderGuard==0,"Guard held across workloop gate acquisition");
        std::cout << "{\"checks\":" << checks << ",\"kernel_path\":true,\"hardware_test\":false}\n";
        return 0;
    } catch (const std::exception &error) { std::cerr << error.what() << '\n'; return 1; }
}
