// SPDX-License-Identifier: MIT
#pragma once
#include "MockIOKit.hpp"
using NvU32=uint32_t;
using NvU64=uint64_t;
using NvBool=int;
using NV_STATUS=int;
#define NV_API_CALL
constexpr int NV_OK=0, NV_ERR_INVALID_ARGUMENT=1, NV_ERR_NO_MEMORY=2,
    NV_ERR_INVALID_REQUEST=3, NV_ERR_IN_USE=4, NV_ERR_INVALID_STATE=5,
    NV_ERR_NOT_READY=6, NV_ERR_ILLEGAL_ACTION=7, NV_ERR_OPERATING_SYSTEM=8;
constexpr NvBool NV_TRUE=1, NV_FALSE=0;
struct os_work_queue;
struct S540DarwinTimer;
using S540DarwinWorkAction=void (*)(void *,void *);
using S540DarwinTimerAction=void (*)(void *);
namespace S540DarwinInternal {
struct Guard {
    std::mutex mutex;
    std::condition_variable condition;
    using Token=int;
    Token lock() { mutex.lock(); ++mock::guardDepth; return 0; }
    void unlock(Token) {
        --mock::guardDepth; mutex.unlock();
        uint64_t thread=std::hash<std::thread::id>{}(std::this_thread::get_id()) | 1;
        if (mock::blockUnlockThread.compare_exchange_strong(thread,0)) {
            // Stop after publishing all idle flags and releasing the Guard,
            // but before the production callback returns to Apple IOKit.
            mock::unlockPaused=true;
            while (!mock::releaseUnlock) std::this_thread::yield();
        }
    }
    void wake(void *) { condition.notify_all(); }
    bool wait(void *,Token &,bool) {
        std::unique_lock<std::mutex> lock(mutex,std::adopt_lock);
        --mock::guardDepth; condition.wait(lock); ++mock::guardDepth;
        lock.release(); return true;
    }
};
// Explicit fixtures for the independent retained-backend policy. Composed
// service source executes its real refusal branches against these controls.
struct BackendConstruction { bool allowed() { return mock::backendConstructAllowed; } };
struct BackendFinalizer {
    BackendFinalizer(Guard &,size_t) {}
    bool allowed() { return mock::backendFinalizeAllowed; }
};
inline bool ordinary() { return !mock::interrupt; }
inline NvU64 monotonic() { return mock::now(); }
inline NvU64 identity() { return std::hash<std::thread::id>{}(std::this_thread::get_id()) | 1; }
inline void violation(const char *message) { throw std::runtime_error(message); }
template<class T> T *create() {
    if (!mock::allocation()) return nullptr;
    ++mock::services; return new T{};
}
template<class T> void destroy(T *value) { delete value; --mock::services; }
}
extern "C" inline NV_STATUS s540FirstTxnTimerActionReturned(S540DarwinTimer *) {
    ++mock::timerReturnedHooks; return NV_OK;
}
