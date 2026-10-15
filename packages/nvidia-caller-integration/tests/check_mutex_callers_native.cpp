// SPDX-License-Identifier: MIT
// Functional execution of the original NVIDIA NVPort mutex callers. This
// pthread backend does not establish the kernel try/release no-sleep property.
#include "../upstream/nvport_mutex_callers.h"
#include "../src/S540NvidiaMutex.hpp"

#include <atomic>
#include <cstdio>
#include <cstring>
#include <pthread.h>
#include <sched.h>

namespace {

unsigned int checks = 0;
unsigned int failures = 0;

void check(bool passed, const char *label) {
    ++checks;
    if (!passed) {
        ++failures;
        std::fprintf(stderr, "Mutex caller check failed: %s\n", label);
    }
}

constexpr unsigned int kWorkers = 4;
constexpr unsigned int kUpdatesPerWorker = 4000;
constexpr NvU64 kPublicationMask = 0x9e3779b97f4a7c15ULL;

struct Counter {
    PORT_MUTEX *mutex;
    std::atomic<unsigned int> ready{0};
    std::atomic<bool> start{false};
    std::atomic<bool> inconsistent{false};
    NvU64 value = 0;
    NvU64 publication = kPublicationMask;
};

void *incrementCounter(void *argument) {
    auto *state = static_cast<Counter *>(argument);
    state->ready.fetch_add(1, std::memory_order_release);
    while (!state->start.load(std::memory_order_acquire))
        sched_yield();
    for (unsigned int index = 0; index < kUpdatesPerWorker; ++index) {
        portSyncMutexAcquire(state->mutex);
        if (state->publication != (state->value ^ kPublicationMask))
            state->inconsistent.store(true, std::memory_order_relaxed);
        ++state->value;
        state->publication = state->value ^ kPublicationMask;
        portSyncMutexRelease(state->mutex);
    }
    return nullptr;
}

struct Publication {
    PORT_MUTEX *mutex;
    std::atomic<bool> attempted{false};
    bool conditionalBusy = false;
    unsigned int value = 0;
    unsigned int observed = 0;
};

void *readPublishedValue(void *argument) {
    auto *state = static_cast<Publication *>(argument);
    state->conditionalBusy = !portSyncMutexAcquireConditional(state->mutex);
    if (!state->conditionalBusy)
        portSyncMutexRelease(state->mutex);
    state->attempted.store(true, std::memory_order_release);
    portSyncMutexAcquire(state->mutex);
    state->observed = state->value;
    portSyncMutexRelease(state->mutex);
    return nullptr;
}

void checkPublication(PORT_MUTEX &mutex) {
    Publication state{&mutex};
    pthread_t worker;
    portSyncMutexAcquire(&mutex);
    const int created = pthread_create(&worker, nullptr, readPublishedValue, &state);
    check(created == 0, "publication worker created");
    if (created != 0) {
        portSyncMutexRelease(&mutex);
        return;
    }
    while (!state.attempted.load(std::memory_order_acquire))
        sched_yield();
    // Publish after the competing conditional call completed, while retaining
    // the token. The consumer observes this only after original Acquire returns.
    state.value = 0x4e564d58U;
    portSyncMutexRelease(&mutex);
    check(pthread_join(worker, nullptr) == 0, "publication worker joined");
    check(state.conditionalBusy, "original conditional acquire rejected busy token");
    check(state.observed == 0x4e564d58U, "original release/acquire published protected value");
}

void checkContention(PORT_MUTEX &mutex) {
    Counter state;
    state.mutex = &mutex;
    pthread_t workers[kWorkers];
    unsigned int created = 0;
    for (; created < kWorkers; ++created) {
        if (pthread_create(&workers[created], nullptr, incrementCounter, &state) != 0)
            break;
    }
    check(created == kWorkers, "four contention workers created");
    while (state.ready.load(std::memory_order_acquire) != created)
        sched_yield();
    state.start.store(true, std::memory_order_release);
    for (unsigned int index = 0; index < created; ++index)
        check(pthread_join(workers[index], nullptr) == 0, "contention worker joined");
    const NvU64 expected = static_cast<NvU64>(created) * kUpdatesPerWorker;
    check(state.value == expected, "original caller protected increment total");
    check(state.publication == (expected ^ kPublicationMask), "protected final publication");
    check(!state.inconsistent.load(std::memory_order_relaxed), "no inconsistent protected publication");
}

} // namespace

int main(int argc, char **argv) {
    if (argc == 2 && std::strcmp(argv[1], "--assert-fail") == 0) {
        PORT_MUTEX invalid{};
        // This invokes the real NVIDIA status assertion through the original
        // caller. Returning without the lock must abort through the fatal hook.
        portSyncMutexAcquire(&invalid);
        std::fputs("Original NVPort acquisition assertion unexpectedly returned.\n", stderr);
        return 90;
    }
    if (argc != 1) {
        std::fputs("Usage: check_mutex_callers_native [--assert-fail]\n", stderr);
        return 2;
    }

    check(os_alloc_mutex(nullptr) == NV_ERR_INVALID_ARGUMENT, "OS allocation rejects null output");
    check(os_acquire_mutex(nullptr) == NV_ERR_INVALID_ARGUMENT, "OS acquisition rejects null handle");
    check(os_cond_acquire_mutex(nullptr) == NV_ERR_INVALID_ARGUMENT, "OS conditional rejects null handle");
    check(portSyncMutexInitialize(nullptr) == NV_ERR_INVALID_POINTER, "original initialize rejects null object");
    os_free_mutex(nullptr);
    os_release_mutex(nullptr);

    PORT_MUTEX mutex{};
    const NV_STATUS initialized = portSyncMutexInitialize(&mutex);
    check(initialized == NV_OK && mutex.mutex != nullptr, "original initialize allocated token");
    check(mutex.pAllocator == nullptr, "original initialize preserved untracked allocator mode");
    if (initialized == NV_OK && mutex.mutex != nullptr) {
        const NvBool acquired = portSyncMutexAcquireConditional(&mutex);
        check(acquired == NV_TRUE, "original conditional acquired available token");
        if (acquired) {
            check(portSyncMutexAcquireConditional(&mutex) == NV_FALSE,
                  "original conditional rejects same-thread recursive acquisition");
            portSyncMutexRelease(&mutex);
        }
        portSyncMutexAcquire(&mutex);
        portSyncMutexRelease(&mutex);
        checkPublication(mutex);
        checkContention(mutex);
        portSyncMutexDestroy(&mutex);
    }

    std::printf("{\"format\":1,\"component\":\"nvport-mutex-callers\","
                "\"status\":\"%s\",\"checks\":%u,\"failures\":%u,"
                "\"callers\":5,\"workers\":%u,\"protected_updates\":%u,"
                "\"execution\":\"native-user-space\","
                "\"kernel_runtime\":\"not_tested\","
                "\"kernel_non_sleeping_paths\":\"not_proven_by_native_execution\","
                "\"gpu_access\":false}\n",
                failures == 0 ? "passed" : "failed", checks, failures,
                kWorkers, kWorkers * kUpdatesPerWorker);
    return failures == 0 ? 0 : 1;
}
