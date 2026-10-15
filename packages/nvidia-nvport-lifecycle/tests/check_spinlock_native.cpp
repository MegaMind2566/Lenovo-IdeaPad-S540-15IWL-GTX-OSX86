// SPDX-License-Identifier: MIT
// Native functional checks and simulated TLS state; not kernel IRQ execution.
#include "../src/S540NvidiaSpinlock.hpp"

#include <atomic>
#include <cstdio>
#include <cstring>
#include <pthread.h>
#include <sched.h>

namespace {
unsigned int checks = 0;
unsigned int failures = 0;
constexpr unsigned int kWorkers = 4;
constexpr unsigned int kUpdatesPerWorker = 4000;
constexpr NvU64 kMask = 0x9e3779b97f4a7c15ULL;

void check(bool passed, const char *label) {
    ++checks;
    if (!passed) {
        ++failures;
        std::fprintf(stderr, "Spinlock check failed: %s\n", label);
    }
}

struct Counter {
    void *lock;
    std::atomic<unsigned int> ready{0};
    std::atomic<bool> start{false};
    std::atomic<bool> inconsistent{false};
    NvU64 count = 0;
    NvU64 published = kMask;
};

void *update(void *argument) {
    auto *counter = static_cast<Counter *>(argument);
    counter->ready.fetch_add(1, std::memory_order_release);
    while (!counter->start.load(std::memory_order_acquire))
        sched_yield();
    for (unsigned int index = 0; index != kUpdatesPerWorker; ++index) {
        const NvU64 prior = os_acquire_spinlock(counter->lock);
        if (prior != 1 || S540NvidiaSpinlockNative::interruptsEnabled() ||
            counter->published != (counter->count ^ kMask))
            counter->inconsistent.store(true, std::memory_order_relaxed);
        ++counter->count;
        counter->published = counter->count ^ kMask;
        os_release_spinlock(counter->lock, prior);
        if (!S540NvidiaSpinlockNative::interruptsEnabled())
            counter->inconsistent.store(true, std::memory_order_relaxed);
    }
    return nullptr;
}

void checkContention(void *lock) {
    Counter counter{lock};
    pthread_t workers[kWorkers];
    unsigned int created = 0;
    for (; created != kWorkers; ++created) {
        if (pthread_create(&workers[created], nullptr, update, &counter) != 0)
            break;
    }
    check(created == kWorkers, "four workers created");
    while (counter.ready.load(std::memory_order_acquire) != created)
        sched_yield();
    counter.start.store(true, std::memory_order_release);
    for (unsigned int index = 0; index != created; ++index)
        check(pthread_join(workers[index], nullptr) == 0, "worker joined");
    const NvU64 expected = static_cast<NvU64>(created) * kUpdatesPerWorker;
    check(counter.count == expected, "protected updates complete");
    check(counter.published == (expected ^ kMask), "protected final publication");
    check(!counter.inconsistent.load(std::memory_order_relaxed),
          "publication and simulated per-thread state consistent");
}

} // namespace

int main(int argc, char **argv) {
    if (argc == 2 && std::strcmp(argv[1], "--null-acquire") == 0) {
        (void)os_acquire_spinlock(nullptr);
        return 90;
    }
    if (argc != 1) {
        std::fputs("Usage: check_spinlock_native [--null-acquire]\n", stderr);
        return 2;
    }
    using namespace S540NvidiaSpinlockNative;
    check(liveObjects() == 0, "cold native backend");
    check(os_alloc_spinlock(nullptr) == NV_ERR_INVALID_ARGUMENT, "null output rejected");
    os_free_spinlock(nullptr);
    void *invalid = reinterpret_cast<void *>(static_cast<NvU64>(1));
    setContext(true, true);
    check(os_alloc_spinlock(&invalid) == NV_ERR_INVALID_REQUEST && invalid == nullptr,
          "simulated interrupt context refuses creation and clears output");
    setContext(false, false);
    invalid = reinterpret_cast<void *>(static_cast<NvU64>(1));
    check(os_alloc_spinlock(&invalid) == NV_ERR_INVALID_REQUEST && invalid == nullptr,
          "simulated disabled interrupts refuse creation and clear output");
    setContext(false, true);
    const Failure allocationFailures[] = {Failure::Storage, Failure::Initialization};
    for (Failure failure : allocationFailures) {
        failNextAllocation(failure);
        invalid = reinterpret_cast<void *>(static_cast<NvU64>(1));
        check(os_alloc_spinlock(&invalid) == NV_ERR_NO_MEMORY && invalid == nullptr,
              "injected native allocation failure clears output");
        check(liveObjects() == 0, "failed allocation leaves no live object");
    }

    void *outer = nullptr;
    void *inner = nullptr;
    check(os_alloc_spinlock(&outer) == NV_OK && outer != nullptr, "first lock allocated");
    check(os_alloc_spinlock(&inner) == NV_OK && inner != nullptr, "second lock allocated");
    check(liveObjects() == 2, "two live locks");
    if (outer != nullptr && inner != nullptr) {
        const NvU64 first = os_acquire_spinlock(outer);
        const bool firstDisabled = !interruptsEnabled();
        const NvU64 second = os_acquire_spinlock(inner);
        const bool secondDisabled = !interruptsEnabled();
        os_release_spinlock(inner, second);
        const bool innerKeptDisabled = !interruptsEnabled();
        os_release_spinlock(outer, first);
        check(first == 1 && second == 0, "nested distinct locks save prior TLS states");
        check(firstDisabled && secondDisabled && innerKeptDisabled && interruptsEnabled(),
              "nested releases restore exact simulated prior states");

        setContext(true, false);
        const NvU64 disabled = os_acquire_spinlock(outer);
        const bool heldDisabled = !interruptsEnabled();
        os_release_spinlock(outer, disabled);
        check(disabled == 0 && heldDisabled && !interruptsEnabled(),
              "simulated IRQ-disabled caller remains disabled after release");
        setContext(false, true);
        checkContention(outer);
    }
    os_free_spinlock(inner);
    os_free_spinlock(outer);
    check(liveObjects() == 0, "quiescent destruction releases all native objects");
    std::printf("{\"format\":1,\"component\":\"nvport-spinlock\",\"status\":\"%s\","
                "\"checks\":%u,\"failures\":%u,\"workers\":%u,\"protected_updates\":%u,"
                "\"execution\":\"native-user-space\",\"kernel_runtime\":\"not_tested\","
                "\"interrupt_state\":\"simulated_tls_only\","
                "\"kernel_non_sleeping_paths\":\"not_proven_by_native_execution\","
                "\"gpu_access\":false}\n",
                failures == 0 ? "passed" : "failed", checks, failures,
                kWorkers, kWorkers * kUpdatesPerWorker);
    return failures == 0 ? 0 : 1;
}
