// SPDX-License-Identifier: MIT
// Failure propagation and lease exclusion across the complete v7/v8/v9 paths.
#include "../src/S540NvidiaRmRuntime.hpp"
#include "../memory/S540NvidiaRmMemory.hpp"
#include "../../nvidia-hardware-transport/src/S540NvidiaDma.hpp"
#include "../../nvidia-caller-integration/src/S540NvidiaReserve.hpp"
#include "../../nvidia-caller-integration/src/S540NvidiaMutex.hpp"
#include "../../nvidia-nvport-lifecycle/src/S540NvidiaSpinlock.hpp"
#include "../../nvidia-nvport-runtime/upstream/nvport_runtime.h"
#include <cstdio>
#include <cstdlib>
#include <pthread.h>
#include <sched.h>

namespace {
NvU32 checks;
NvU32 workerStart, workerErrors, completedRuns, leaseRefusals;
constexpr NvU32 kWorkers = 4, kIterations = 6;

void require(bool condition, const char *message)
{
    ++checks;
    if (!condition) {
        std::fprintf(stderr, "RM service aggregate failed: %s\n", message);
        std::exit(1);
    }
}

bool cold()
{
    const auto memory = S540NvidiaRmMemory::statistics();
    return s540NvportRuntimeIsCold() == NV_TRUE &&
        !S540NvidiaReserve::ready() && S540NvidiaReserve::liveSlots() == 0 &&
        S540NvidiaMutex::liveObjects() == 0 &&
        S540NvidiaSpinlock::liveObjects() == 0 &&
        !S540NvidiaRmMemory::ready() && memory.allocations == 0 &&
        memory.mappings == 0 && memory.deferred == 0 && memory.bytes == 0 &&
        S540NvidiaRmMemory::nativeLiveResources() == 0 &&
        S540NvidiaRmMemory::nativeIllegalOperations() == 0 &&
        S540NvidiaDma::nativeLiveResources() == 0 &&
        S540NvidiaDma::nativeIllegalOperations() == 0;
}

bool cpuPassed(const S540NvidiaSupportRuntime::IntegratedResult &result)
{
    return result.acquired && result.v6.acquired && result.v6.v5.acquired &&
        result.v6.v5.foundations.passed() && result.v6.v5.callers.passed() &&
        result.v6.lifecycle.passed() && result.support.passed();
}

bool hardwarePassed(const S540NvidiaHardwareRuntime::IntegratedResult &result)
{
    return result.acquired && cpuPassed(result.v7) && result.preparation.passed();
}

void nested(void *opaque)
{
    auto &refused = *static_cast<bool *>(opaque);
    const auto result = S540NvidiaRmRuntime::checkIntegrated(nullptr);
    refused = !result.acquired && !result.v8.acquired &&
        !result.services.passed() && result.services.checks == 1 &&
        result.services.failures == 1 && !result.services.resourceServer &&
        !result.services.hostMemory && !result.services.pciSession;
}

void *worker(void *opaque)
{
    const NvU32 id = static_cast<NvU32>(reinterpret_cast<NvUPtr>(opaque));
    while (__atomic_load_n(&workerStart, __ATOMIC_ACQUIRE) == 0)
        sched_yield();
    for (NvU32 index = 0; index < kIterations; ++index) {
        bool acquired = false, passed = false;
        switch ((index + id) % 3U) {
        case 0: {
            const auto result = S540NvidiaRmRuntime::checkIntegrated(nullptr);
            acquired = result.acquired;
            passed = hardwarePassed(result.v8) && result.services.passed();
            break;
        }
        case 1: {
            const auto result = S540NvidiaHardwareRuntime::checkIntegrated(nullptr);
            acquired = result.acquired;
            passed = hardwarePassed(result);
            break;
        }
        default: {
            const auto result = S540NvidiaSupportRuntime::checkIntegrated();
            acquired = result.acquired;
            passed = cpuPassed(result);
            break;
        }
        }
        if (acquired) {
            __atomic_add_fetch(&completedRuns, NvU32{1}, __ATOMIC_RELAXED);
            if (!passed)
                __atomic_add_fetch(&workerErrors, NvU32{1}, __ATOMIC_RELAXED);
        } else {
            __atomic_add_fetch(&leaseRefusals, NvU32{1}, __ATOMIC_RELAXED);
            if (passed)
                __atomic_add_fetch(&workerErrors, NvU32{1}, __ATOMIC_RELAXED);
        }
    }
    return nullptr;
}
}

int main()
{
    require(cold(), "initial cold state");
    const auto first = S540NvidiaRmRuntime::checkIntegrated(nullptr);
    require(first.acquired && hardwarePassed(first.v8) &&
            first.services.passed() && cold(), "complete production startup");

    bool refused = false;
    const auto parent = S540NvidiaHardwareRuntime::checkIntegrated(
        nullptr, nested, &refused);
    require(hardwarePassed(parent) && refused && cold(),
            "v9 cannot reenter the shared v8 lease");

    S540NvidiaDma::setNativeFault(S540NvidiaDma::Fault::BufferAllocation);
    const auto preceding = S540NvidiaRmRuntime::checkIntegrated(nullptr);
    require(preceding.acquired && cpuPassed(preceding.v8.v7) &&
            !preceding.v8.preparation.passed() &&
            !preceding.services.passed() && preceding.services.checks == 1 &&
            preceding.services.resourceServerChecks == 0 && cold(),
            "a failed v8 prerequisite never enters the Resource Server");
    S540NvidiaDma::setNativeFault(S540NvidiaDma::Fault::None);

    using Fault = S540NvidiaRmMemory::Fault;
    struct Failure { Fault fault; bool cleanup; };
    const Failure failures[] = {
        {Fault::BufferAllocation, true},
        {Fault::BufferPrepare, true},
        {Fault::MappingAllocation, true},
        {Fault::MappingAddress, true},
        {Fault::BufferComplete, false}
    };
    for (const auto &failure : failures) {
        S540NvidiaRmMemory::setNativeFault(failure.fault);
        const auto result = S540NvidiaRmRuntime::checkIntegrated(nullptr);
        require(result.acquired && hardwarePassed(result.v8),
                "previous startup evidence survives a host-service failure");
        require(result.services.resourceServer && result.services.clients &&
                result.services.resources && result.services.sharing &&
                result.services.control && !result.services.hostMemory &&
                !result.services.passed() && result.services.failures > 0 &&
                result.services.cleanup == failure.cleanup,
                "host-service failure remains separate from real server evidence");
        require(cold(), "all backing resources released after failure");
        S540NvidiaRmMemory::setNativeFault(Fault::None);
        const auto recovered = S540NvidiaRmRuntime::checkIntegrated(nullptr);
        require(recovered.acquired && hardwarePassed(recovered.v8) &&
                recovered.services.passed() && cold(),
                "complete retry after a quiesced failure");
    }

    pthread_t threads[kWorkers];
    for (NvU32 index = 0; index < kWorkers; ++index)
        require(pthread_create(&threads[index], nullptr, worker,
                    reinterpret_cast<void *>(static_cast<NvUPtr>(index))) == 0,
                "create mixed-generation native worker");
    __atomic_store_n(&workerStart, NvU32{1}, __ATOMIC_RELEASE);
    for (auto &thread : threads)
        require(pthread_join(thread, nullptr) == 0, "join each worker");
    require(workerErrors == 0 && completedRuns > 0 &&
            completedRuns + leaseRefusals == kWorkers * kIterations && cold(),
            "one lease serializes all three complete entry points");

    std::printf("{\"format\":1,\"component\":\"nvidia-rm-services-faults\","
        "\"status\":\"passed\",\"checks\":%u,\"failures\":0,\"cross_stage_faults\":6,"
        "\"nested_lease_refusal\":true,\"recovery\":true,\"cleanup\":true,"
        "\"workers\":%u,\"iterations_per_worker\":%u,"
        "\"completed_runs\":%u,\"lease_refusals\":%u,\"worker_errors\":%u,"
        "\"cold_after\":true,\"full_rm_initialized\":false,"
        "\"firmware_loaded\":false,\"gpu_initialized\":false,"
        "\"interrupts_enabled\":false,\"device_dma_verified\":false,"
        "\"execution\":\"native-user-space\",\"kernel_runtime\":\"not_tested\","
        "\"gpu_access\":false}\n", checks, kWorkers, kIterations,
        completedRuns, leaseRefusals, workerErrors);
    return 0;
}
