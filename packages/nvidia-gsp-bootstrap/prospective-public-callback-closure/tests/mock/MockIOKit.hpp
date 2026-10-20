// SPDX-License-Identifier: MIT
#pragma once
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <cstring>
#include <mutex>
#include <stdexcept>
#include <thread>
#include <vector>

using AbsoluteTime = uint64_t;
using IOReturn = int;
constexpr IOReturn kIOReturnSuccess = 0, kIOReturnError = -1;
constexpr uint32_t kIOTimerEventSourceOptionsPriorityWorkLoop = 0xff;
namespace mock {
inline std::atomic<int> live{0}, services{0}, step{0}, failAt{0};
inline std::atomic<int> gateUnderGuard{0}, delivered{0};
inline std::atomic<bool> failDrain{false}, failRemove{false};
inline std::atomic<uint64_t> blockUnlockThread{0};
inline std::atomic<bool> unlockPaused{false}, releaseUnlock{false};
inline std::atomic<bool> backendConstructAllowed{true},backendFinalizeAllowed{true};
inline std::atomic<int> timerReturnedHooks{0};
inline thread_local int guardDepth = 0;
inline thread_local bool interrupt = false;
inline bool allocation() { return ++step != failAt; }
inline uint64_t now() {
    return std::chrono::duration_cast<std::chrono::nanoseconds>(
        std::chrono::steady_clock::now().time_since_epoch()).count();
}
}
class OSObject {
    std::atomic<int> refs{1};
public:
    OSObject() { ++mock::live; }
    virtual ~OSObject() { --mock::live; }
    void retain() { ++refs; }
    void release() { if (--refs == 0) delete this; }
};
class OSData : public OSObject {
    std::vector<unsigned char> bytes;
public:
    static OSData *withBytes(const void *source, unsigned length) {
        if (!mock::allocation()) return nullptr;
        auto *value = new OSData;
        value->bytes.resize(length);
        std::memcpy(value->bytes.data(), source, length);
        return value;
    }
    void *getBytesNoCopy() { return bytes.data(); }
};
class IOTimerEventSource;
class IOWorkLoop : public OSObject {
public:
    using Action = IOReturn (*)(OSObject *, void *, void *, void *, void *);
    std::recursive_mutex gate;
    static IOWorkLoop *workLoop() {
        return mock::allocation() ? new IOWorkLoop : nullptr;
    }
    IOReturn addEventSource(IOTimerEventSource *);
    IOReturn removeEventSource(IOTimerEventSource *);
    IOReturn runAction(Action action, OSObject *owner, void *a=nullptr,
        void *b=nullptr, void *c=nullptr, void *d=nullptr) {
        if (mock::guardDepth) ++mock::gateUnderGuard;
        if (mock::failDrain.exchange(false)) return kIOReturnError;
        std::lock_guard<std::recursive_mutex> lock(gate);
        return action(owner,a,b,c,d);
    }
};
class IOTimerEventSource : public OSObject {
public:
    using Action = void (*)(OSObject *, IOTimerEventSource *);
    OSObject *owner;
    IOWorkLoop *loop = nullptr;
    Action action;
    std::mutex state;
    std::condition_variable changed;
    bool exit=false, pending=false, pauseDequeued=false, dequeued=false;
    uint64_t deadline=0, generation=0;
    std::thread worker;
    inline static IOTimerEventSource *latest=nullptr;
    IOTimerEventSource(OSObject *o, Action a) : owner(o), action(a) {
        // IOEventSource keeps an unretained owner. The production helper must
        // own its binding until the event source is completely removed.
        latest=this;
        worker=std::thread([this] { dispatch(); });
    }
    ~IOTimerEventSource() override {
        { std::lock_guard<std::mutex> lock(state); exit=true; changed.notify_all(); }
        worker.join();
    }
    static IOTimerEventSource *timerEventSource(uint32_t options, OSObject *owner, Action action) {
        if (options != kIOTimerEventSourceOptionsPriorityWorkLoop)
            throw std::runtime_error("wrong delivery context");
        return mock::allocation() ? new IOTimerEventSource(owner,action) : nullptr;
    }
    IOReturn wakeAtTime(AbsoluteTime at) {
        // Deliberately does not take the workloop gate, allocate or sleep.
        std::lock_guard<std::mutex> lock(state);
        ++generation; deadline=at; pending=true; changed.notify_all();
        return kIOReturnSuccess;
    }
    void cancelTimeout() {
        std::lock_guard<std::mutex> lock(state);
        ++generation; pending=false; changed.notify_all();
    }
    void pauseAfterDequeue(bool value) {
        std::lock_guard<std::mutex> lock(state);
        pauseDequeued=value; changed.notify_all();
    }
    bool hasDequeued() {
        std::lock_guard<std::mutex> lock(state); return dequeued;
    }
    void dispatch() {
        std::unique_lock<std::mutex> lock(state);
        while (!exit) {
            changed.wait(lock,[&] { return exit || pending; });
            if (exit) break;
            const uint64_t now=mock::now();
            if (deadline > now) {
                changed.wait_for(lock,std::chrono::nanoseconds(deadline-now));
                continue;
            }
            const uint64_t submitted=generation;
            pending=false; dequeued=true; changed.notify_all();
            changed.wait(lock,[&] { return exit || !pauseDequeued; });
            if (exit) break;
            IOWorkLoop *workLoop=loop;
            if (!workLoop) { dequeued=false; continue; }
            lock.unlock();
            {
                // Models an Apple-delivered workloop event, including the
                // race where it has dequeued but has not acquired the gate.
                std::lock_guard<std::recursive_mutex> gate(workLoop->gate);
                lock.lock();
                const bool valid=submitted==generation && loop==workLoop;
                lock.unlock();
                if (valid) { ++mock::delivered; action(owner,this); }
            }
            lock.lock(); dequeued=false; changed.notify_all();
        }
    }
};
inline IOReturn IOWorkLoop::addEventSource(IOTimerEventSource *source) {
    if (!mock::allocation()) return kIOReturnError;
    std::lock_guard<std::recursive_mutex> lock(gate);
    source->loop=this; source->retain(); return kIOReturnSuccess;
}
inline IOReturn IOWorkLoop::removeEventSource(IOTimerEventSource *source) {
    if (mock::failRemove.exchange(false)) return kIOReturnError;
    std::lock_guard<std::recursive_mutex> lock(gate);
    { std::lock_guard<std::mutex> state(source->state); source->loop=nullptr; }
    source->release(); return kIOReturnSuccess;
}
inline void clock_get_uptime(AbsoluteTime *value) { *value=mock::now(); }
inline void nanoseconds_to_absolutetime(uint64_t value,uint64_t *result) { *result=value; }
