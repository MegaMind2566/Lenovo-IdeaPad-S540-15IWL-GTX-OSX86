// SPDX-License-Identifier: MIT
// Native userspace verification of the exact mutex OS-hook ABI.
#include "../src/S540NvidiaSync.hpp"

#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <pthread.h>
#include <sched.h>
#include <unistd.h>

static unsigned checks;

static void require(bool condition, const char *message) {
    ++checks;
    if (!condition) {
        std::fprintf(stderr, "Mutex adapter check failed: %s\n", message);
        std::exit(1);
    }
}

static void basicSemantics() {
    require(os_alloc_mutex(nullptr) == NV_ERR_INVALID_ARGUMENT,
            "null output rejected");
    require(os_acquire_mutex(nullptr) == NV_ERR_INVALID_ARGUMENT,
            "null acquire rejected");
    require(os_cond_acquire_mutex(nullptr) == NV_ERR_INVALID_ARGUMENT,
            "null conditional acquire rejected");
    os_free_mutex(nullptr);
    os_release_mutex(nullptr);

    void *mutex = nullptr;
    require(os_alloc_mutex(&mutex) == NV_OK && mutex != nullptr,
            "allocation returns a usable opaque mutex");
    require(os_acquire_mutex(mutex) == NV_OK, "ordinary acquire");
    require(os_cond_acquire_mutex(mutex) == NV_ERR_TIMEOUT_RETRY,
            "conditional acquire cannot recurse");
    os_release_mutex(mutex);
    require(os_cond_acquire_mutex(mutex) == NV_OK,
            "conditional acquire succeeds after release");
    os_release_mutex(mutex);
    require(os_acquire_mutex(mutex) == NV_OK, "acquire after conditional release");
    os_release_mutex(mutex);
    os_free_mutex(mutex);
}

struct Handoff {
    void *mutex;
    std::atomic<bool> tried{false};
    std::atomic<NV_STATUS> tryStatus{NV_ERR_GENERIC};
    NV_STATUS acquireStatus{NV_ERR_GENERIC};
    unsigned payload{0};
    unsigned observed{0};
};

static void *contendedWaiter(void *argument) {
    auto &state = *static_cast<Handoff *>(argument);
    const NV_STATUS attempted = os_cond_acquire_mutex(state.mutex);
    state.tryStatus.store(attempted, std::memory_order_relaxed);
    if (attempted == NV_OK)
        os_release_mutex(state.mutex);
    state.tried.store(true, std::memory_order_release);
    state.acquireStatus = os_acquire_mutex(state.mutex);
    if (state.acquireStatus == NV_OK) {
        state.observed = state.payload;
        os_release_mutex(state.mutex);
    }
    return nullptr;
}

static void contentionAndPublication() {
    Handoff state{};
    require(os_alloc_mutex(&state.mutex) == NV_OK, "handoff mutex allocation");
    require(os_acquire_mutex(state.mutex) == NV_OK, "main thread owns mutex");
    pthread_t waiter{};
    require(pthread_create(&waiter, nullptr, contendedWaiter, &state) == 0,
            "create blocked contender");
    while (!state.tried.load(std::memory_order_acquire))
        sched_yield();
    require(state.tryStatus.load(std::memory_order_relaxed) == NV_ERR_TIMEOUT_RETRY,
            "another thread's try-lock reports contention without blocking");
    // Written after the atomic handshake: the following read needs the mutex
    // acquire/release to publish data, rather than relying on the handshake.
    state.payload = 0x73a519U;
    os_release_mutex(state.mutex);
    require(pthread_join(waiter, nullptr) == 0, "join blocking contender");
    require(state.acquireStatus == NV_OK, "blocking acquire proceeds after release");
    require(state.observed == state.payload,
            "mutex release/acquire publishes ordinary protected memory");
    os_free_mutex(state.mutex);
}

struct Counter {
    void *mutex;
    std::atomic<unsigned> failures{0};
    unsigned value{0};
    unsigned mirror{~0U};
};

static constexpr unsigned kThreads = 4;
static constexpr unsigned kIterations = 6000;

static void *incrementCounter(void *argument) {
    auto &state = *static_cast<Counter *>(argument);
    for (unsigned i = 0; i < kIterations; ++i) {
        if (os_acquire_mutex(state.mutex) != NV_OK) {
            state.failures.fetch_add(1, std::memory_order_relaxed);
            return nullptr;
        }
        if (state.mirror != ~state.value)
            state.failures.fetch_add(1, std::memory_order_relaxed);
        ++state.value;
        state.mirror = ~state.value;
        os_release_mutex(state.mutex);
    }
    return nullptr;
}

static void multiThreadContention() {
    Counter state{};
    require(os_alloc_mutex(&state.mutex) == NV_OK, "counter mutex allocation");
    pthread_t threads[kThreads]{};
    for (auto &thread : threads)
        require(pthread_create(&thread, nullptr, incrementCounter, &state) == 0,
                "create counter contender");
    for (auto &thread : threads)
        require(pthread_join(thread, nullptr) == 0, "join counter contender");
    require(state.failures.load(std::memory_order_relaxed) == 0,
            "mutex protects multi-field invariant under contention");
    require(state.value == kThreads * kIterations && state.mirror == ~state.value,
            "all contended increments retained");
    os_free_mutex(state.mutex);
}

int main() {
    // A broken blocking/try-lock implementation fails instead of hanging CI.
    alarm(20);
    basicSemantics();
    contentionAndPublication();
    multiThreadContention();
    alarm(0);
    std::printf("{\"format\":1,\"status\":\"passed\",\"checks\":%u,"
        "\"component\":\"ordinary-thread-mutex\",\"execution\":\"native-user-space\","
        "\"backend\":\"pthread\",\"threads\":%u,\"increments\":%u,"
        "\"kernel_runtime\":\"not_tested\",\"gpu_access\":false}\n",
        checks, kThreads, kThreads * kIterations);
    return 0;
}
