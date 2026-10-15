// SPDX-License-Identifier: MIT
// Native-only fault/recovery and mixed-entry lease checks. No kernel linkage.
#include "../src/S540NvidiaSupportRuntime.hpp"
#include "../upstream/nvport_runtime.h"
#include "../../nvidia-caller-integration/src/S540NvidiaReserve.hpp"
#include "../../nvidia-caller-integration/src/S540NvidiaMutex.hpp"
#include "../../nvidia-nvport-lifecycle/src/S540NvidiaSpinlock.hpp"

#include <cstdio>
#include <cstdlib>
#include <pthread.h>
#include <sched.h>

namespace {

NvU32 gChecks;
constexpr NvU32 kWorkers = 4;
constexpr NvU32 kIterations = 12;
NvU32 gStart;
NvU32 gErrors;
NvU32 gCompleted;
NvU32 gRefused;

void require(bool condition, const char *message)
{
    ++gChecks;
    if (!condition) {
        std::fprintf(stderr, "CPU support contract failed: %s\n", message);
        std::exit(1);
    }
}

bool cold()
{
    return s540NvportRuntimeIsCold() == NV_TRUE &&
        !S540NvidiaReserve::ready() && S540NvidiaReserve::liveSlots() == 0 &&
        S540NvidiaMutex::liveObjects() == 0 &&
        S540NvidiaSpinlock::liveObjects() == 0;
}

bool foundationsPassed(const S540NvidiaRuntime::Result &result)
{
    return result.timer && result.memory && result.atomics &&
        result.allocation && result.mutex;
}

bool previousPassed(const S540NvidiaLifecycleRuntime::IntegratedResult &result)
{
    return result.acquired && result.v5.acquired &&
        foundationsPassed(result.v5.foundations) && result.v5.callers.passed() &&
        result.lifecycle.passed();
}

void bootstrapFaults()
{
    require(cold(), "initial components cold");
    require(s540NvportRuntimeInitialize() == NV_ERR_NO_MEMORY && cold(),
            "missing reserve does not publish a CPU core");
    require(S540NvidiaReserve::initialize(), "reserve for core faults");
    using namespace S540NvidiaSpinlockNative;
    setContext(true, true);
    require(s540NvportRuntimeInitialize() == NV_ERR_INVALID_STATE &&
            s540NvportRuntimeIsCold() == NV_TRUE &&
            S540NvidiaReserve::liveSlots() == 0,
            "interrupt-context core startup is refused before publication");
    setContext(false, false);
    require(s540NvportRuntimeInitialize() == NV_ERR_INVALID_STATE &&
            s540NvportRuntimeIsCold() == NV_TRUE &&
            S540NvidiaReserve::liveSlots() == 0,
            "interrupt-disabled core startup is refused before publication");
    setContext(false, true);
    const Failure faults[] = {Failure::Storage, Failure::Initialization};
    for (Failure fault : faults) {
        failNextAllocation(fault);
        require(s540NvportRuntimeInitialize() == NV_ERR_NO_MEMORY &&
                s540NvportRuntimeIsCold() == NV_TRUE &&
                S540NvidiaReserve::liveSlots() == 0 &&
                S540NvidiaSpinlock::liveObjects() == 0,
                "core bootstrap backing failure releases partial resources");
    }
    void *slots[S540NvidiaReserve::kSlotCount - 1] = {};
    for (NvU32 index = 0; index < S540NvidiaReserve::kSlotCount - 1; ++index)
        require(os_alloc_mem(&slots[index], 1) == NV_OK && slots[index] != nullptr,
                "occupy reserve for post-memory PRNG allocation failure");
    require(s540NvportRuntimeInitialize() == NV_ERR_NO_MEMORY &&
            s540NvportRuntimeIsCold() == NV_TRUE &&
            S540NvidiaReserve::liveSlots() == S540NvidiaReserve::kSlotCount - 1 &&
            S540NvidiaSpinlock::liveObjects() == 0,
            "PRNG allocation failure unwinds initialized memory in reverse");
    for (void *slot : slots)
        os_free_mem(slot);
    require(S540NvidiaReserve::shutdown() && cold(),
            "fault occupancy and reserve released");
}

void shutdownOwnership()
{
    require(S540NvidiaReserve::initialize(), "reserve for core ownership");
    require(s540NvportRuntimeInitialize() == NV_OK &&
            s540NvportRuntimeIsInitialized() == NV_TRUE,
            "core initializes after failures");
    const NvU32 slots = S540NvidiaReserve::liveSlots();
    const NvU32 spinlocks = S540NvidiaSpinlock::liveObjects();
    require(s540NvportRuntimeInitialize() == NV_ERR_INVALID_STATE &&
            s540NvportRuntimeIsInitialized() == NV_TRUE &&
            S540NvidiaReserve::liveSlots() == slots &&
            S540NvidiaSpinlock::liveObjects() == spinlocks,
            "duplicate core startup preserves original session ownership");
    void *allocation = portMemAllocNonPaged(32);
    require(allocation != nullptr, "live allocation for shutdown refusal");
    require(s540NvportRuntimeShutdown() == NV_ERR_INVALID_STATE &&
            s540NvportRuntimeIsInitialized() == NV_TRUE &&
            S540NvidiaReserve::liveSlots() == slots + 1,
            "live consumer allocation refuses shutdown without partial teardown");
    portMemFree(allocation);
    PORT_MEM_ALLOCATOR *allocator = portMemAllocatorCreateNonPaged();
    require(allocator != nullptr, "owned allocator for shutdown refusal");
    require(s540NvportRuntimeShutdown() == NV_ERR_INVALID_STATE &&
            s540NvportRuntimeIsInitialized() == NV_TRUE,
            "live owned allocator refuses shutdown without freeing PRNG");
    portMemAllocatorRelease(allocator);
    require(s540NvportRuntimeShutdown() == NV_OK &&
            s540NvportRuntimeIsCold() == NV_TRUE &&
            S540NvidiaReserve::liveSlots() == 0 &&
            S540NvidiaSpinlock::liveObjects() == 0,
            "quiescent owner cleanup permits complete reverse shutdown");
    require(S540NvidiaReserve::shutdown() && cold(),
            "core ownership session returns completely cold");
}

void tryNestedEntry(void *context)
{
    auto &refused = *static_cast<bool *>(context);
    const auto nested = S540NvidiaSupportRuntime::checkIntegrated();
    refused = !nested.acquired && !nested.v6.acquired &&
        !nested.v6.v5.acquired && !nested.support.passed() &&
        nested.support.checks != 0 && nested.support.failures != 0 &&
        nested.support.core == false && nested.support.utilities == false &&
        nested.support.consumer == false && nested.support.cleanup == false;
}

void nestedLease()
{
    bool refused = false;
    const auto parent = S540NvidiaLifecycleRuntime::checkIntegrated(
        tryNestedEntry, &refused);
    require(previousPassed(parent) && refused && cold(),
            "v7 entry is refused while the unchanged v6 lease is owned");
}

void *worker(void *argument)
{
    const NvU32 token = *static_cast<const NvU32 *>(argument);
    while (__atomic_load_n(&gStart, __ATOMIC_ACQUIRE) == 0)
        sched_yield();
    for (NvU32 iteration = 0; iteration < kIterations; ++iteration) {
        bool acquired = false;
        bool passed = false;
        const NvU32 entry = (iteration + token) % 3;
        if (entry == 0) {
            const auto result = S540NvidiaCallerRuntime::checkIntegrated();
            acquired = result.acquired;
            passed = acquired && foundationsPassed(result.foundations) &&
                result.callers.passed();
        } else if (entry == 1) {
            const auto result = S540NvidiaLifecycleRuntime::checkIntegrated();
            acquired = result.acquired;
            passed = previousPassed(result);
        } else {
            const auto result = S540NvidiaSupportRuntime::checkIntegrated();
            acquired = result.acquired;
            passed = acquired && previousPassed(result.v6) && result.support.passed();
        }
        if (!acquired)
            __atomic_fetch_add(&gRefused, NvU32{1}, __ATOMIC_RELAXED);
        else if (passed)
            __atomic_fetch_add(&gCompleted, NvU32{1}, __ATOMIC_RELAXED);
        else
            __atomic_fetch_add(&gErrors, NvU32{1}, __ATOMIC_RELAXED);
        sched_yield();
    }
    return nullptr;
}

void mixedLease()
{
    pthread_t threads[kWorkers]{};
    NvU32 tokens[kWorkers]{};
    for (NvU32 index = 0; index < kWorkers; ++index) {
        tokens[index] = index;
        require(pthread_create(&threads[index], nullptr, worker, &tokens[index]) == 0,
                "start mixed-entry native lease worker");
    }
    __atomic_store_n(&gStart, NvU32{1}, __ATOMIC_RELEASE);
    for (pthread_t thread : threads)
        require(pthread_join(thread, nullptr) == 0,
                "join mixed-entry native lease worker");
    require(gErrors == 0 && gCompleted != 0 &&
            gCompleted + gRefused == kWorkers * kIterations && cold(),
            "mixed v5/v6/v7 lease admits complete runs or immediate refusals");
    const auto final = S540NvidiaSupportRuntime::checkIntegrated();
    require(final.acquired && previousPassed(final.v6) && final.support.passed() &&
            cold(), "aggregate startup recovers after mixed-entry contention");
}

} // namespace

int main()
{
    bootstrapFaults();
    shutdownOwnership();
    nestedLease();
    mixedLease();
    std::printf("{\"format\":1,\"component\":\"nvport-support-faults\","
                "\"status\":\"passed\",\"checks\":%u,\"failures\":0,\"workers\":%u,"
                "\"iterations_per_worker\":%u,\"completed_runs\":%u,"
                "\"lease_refusals\":%u,\"errors\":%u,"
                "\"cleanup\":true,\"reserve_cold_after\":true,"
                "\"core_cold_after\":true,\"os_objects_released\":true,"
                "\"execution\":\"native-user-space\","
                "\"kernel_runtime\":\"not_tested\","
                "\"kernel_contention\":\"not_tested\",\"gpu_access\":false}\n",
                gChecks, kWorkers, kIterations, gCompleted, gRefused, gErrors);
    return 0;
}
