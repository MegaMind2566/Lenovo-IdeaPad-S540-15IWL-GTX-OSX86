// SPDX-License-Identifier: MIT
// Cross-stage failure propagation, cleanup, recovery and shared-lease checks.
#include "../src/S540NvidiaHardwareRuntime.hpp"
#include "../src/S540NvidiaDma.hpp"
#include "../src/S540NvidiaPci.hpp"
#include "../../nvidia-caller-integration/src/S540NvidiaReserve.hpp"
#include "../../nvidia-caller-integration/src/S540NvidiaMutex.hpp"
#include "../../nvidia-nvport-lifecycle/src/S540NvidiaSpinlock.hpp"
#include "../../nvidia-nvport-runtime/upstream/nvport_runtime.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <pthread.h>
#include <sched.h>

namespace {
NvU32 checks;
NvU32 workerStart, workerErrors, completedRuns, leaseRefusals;
constexpr NvU32 kWorkers = 4, kIterations = 8;
void require(bool passed, const char *message)
{
    ++checks;
    if (!passed) {
        std::fprintf(stderr, "Hardware aggregate contract failed: %s\n", message);
        std::exit(1);
    }
}
bool cold()
{
    return s540NvportRuntimeIsCold() == NV_TRUE &&
        !S540NvidiaReserve::ready() && S540NvidiaReserve::liveSlots() == 0 &&
        S540NvidiaMutex::liveObjects() == 0 &&
        S540NvidiaSpinlock::liveObjects() == 0 &&
        S540NvidiaDma::nativeLiveResources() == 0 &&
        S540NvidiaDma::nativeIllegalOperations() == 0;
}
bool previous(const S540NvidiaSupportRuntime::IntegratedResult &v7)
{
    return v7.acquired && v7.v6.acquired && v7.v6.v5.acquired &&
        v7.v6.v5.foundations.passed() && v7.v6.v5.callers.passed() &&
        v7.v6.lifecycle.passed() && v7.support.passed();
}
void nested(void *opaque)
{
    auto &refused = *static_cast<bool *>(opaque);
    const auto r = S540NvidiaHardwareRuntime::checkIntegrated(nullptr);
    refused = !r.acquired && !r.v7.acquired && !r.v7.v6.acquired &&
        !r.v7.v6.v5.acquired && !r.preparation.passed() &&
        r.preparation.checks > 0 && r.preparation.failures > 0 &&
        !r.preparation.hostDma && !r.preparation.cleanup;
}
void *worker(void *opaque)
{
    const NvU32 id = static_cast<NvU32>(reinterpret_cast<NvUPtr>(opaque));
    while (__atomic_load_n(&workerStart, __ATOMIC_ACQUIRE) == 0) sched_yield();
    for (NvU32 i = 0; i < kIterations; ++i) {
        bool acquired = false, passed = false;
        if ((i + id) & 1U) {
            const auto r = S540NvidiaHardwareRuntime::checkIntegrated(nullptr);
            acquired = r.acquired;
            passed = previous(r.v7) && r.preparation.passed();
        } else {
            const auto r = S540NvidiaSupportRuntime::checkIntegrated();
            acquired = r.acquired;
            passed = previous(r);
        }
        if (acquired) {
            __atomic_add_fetch(&completedRuns, NvU32{1}, __ATOMIC_RELAXED);
            if (!passed) __atomic_add_fetch(&workerErrors, NvU32{1}, __ATOMIC_RELAXED);
        } else {
            __atomic_add_fetch(&leaseRefusals, NvU32{1}, __ATOMIC_RELAXED);
            if (passed) __atomic_add_fetch(&workerErrors, NvU32{1}, __ATOMIC_RELAXED);
        }
    }
    return nullptr;
}
}

int main()
{
    require(cold(), "initial state cold");
    bool refused = false;
    const auto parent = S540NvidiaSupportRuntime::checkIntegrated(nested, &refused);
    require(previous(parent) && refused && cold(), "v8 cannot enter the active v7 lease");

    using namespace S540NvidiaDma;
    struct FailureCase { Fault fault; const char *reason; bool cleanup; };
    const FailureCase failures[] = {
        {Fault::BufferAllocation, "allocation_failed", true},
        {Fault::CommandPrepare, "command_prepare_failed", true},
        {Fault::PatternCorruption, "pattern_mismatch", true},
        {Fault::CommandComplete, "command_complete_failed", false},
        {Fault::Clear, "clear_failed", false},
        {Fault::BufferComplete, "descriptor_complete_failed", false},
        {Fault::MapperUnresolved, "mapper_unavailable", true}
    };
    for (const auto &failure : failures) {
        setNativeFault(failure.fault);
        const auto r = S540NvidiaHardwareRuntime::checkIntegrated(nullptr);
        require(r.acquired && previous(r.v7), "previous CPU evidence survives a later failure");
        require(!r.preparation.passed() && r.preparation.failures > 0 &&
                !r.preparation.hostDma && r.preparation.pciReadAdapter &&
                r.preparation.interruptInventory && r.preparation.firmwareParser &&
                r.preparation.firmwareRpc, "new failure cannot become transport success");
        require(std::strcmp(r.preparation.dmaReason, failure.reason) == 0 &&
                r.preparation.cleanup == failure.cleanup,
                "failure reason and cleanup evidence remain independent");
        require(cold(), "failure releases every backing object without illegal operations");
        setNativeFault(Fault::None);
        const auto recovered = S540NvidiaHardwareRuntime::checkIntegrated(nullptr);
        require(recovered.acquired && previous(recovered.v7) &&
                recovered.preparation.passed() && cold(), "complete retry after quiescent failure");
    }
    setNativeMapperMode(MapperMode::DirectUntranslated);
    const auto direct = S540NvidiaHardwareRuntime::checkIntegrated(nullptr);
    require(direct.acquired && direct.preparation.passed() &&
            std::strcmp(direct.preparation.dmaMode, "direct_untranslated") == 0 && cold(),
            "untranslated preparation is explicit and completely cleaned");
    setNativeMapperMode(MapperMode::Provider);
    pthread_t workers[kWorkers];
    for (NvU32 i = 0; i < kWorkers; ++i)
        require(pthread_create(&workers[i], nullptr, worker,
                reinterpret_cast<void *>(static_cast<NvUPtr>(i))) == 0,
                "create native-only mixed-entry worker");
    __atomic_store_n(&workerStart, NvU32{1}, __ATOMIC_RELEASE);
    for (auto &thread : workers)
        require(pthread_join(thread, nullptr) == 0, "join every native worker");
    require(workerErrors == 0 && completedRuns > 0 &&
            completedRuns + leaseRefusals == kWorkers * kIterations && cold(),
            "shared v7/v8 lease serializes the complete transport lifecycle");
    std::printf("{\"format\":1,\"component\":\"nvidia-hardware-faults\","
        "\"status\":\"passed\",\"checks\":%u,\"failures\":0,"
        "\"cross_stage_faults\":7,\"nested_lease_refusal\":true,"
        "\"recovery\":true,\"cleanup\":true,\"cold_after\":true,"
        "\"workers\":4,\"iterations_per_worker\":8,"
        "\"completed_runs\":%u,\"lease_refusals\":%u,\"worker_errors\":%u,"
        "\"device_dma_verified\":false,\"firmware_loaded\":false,"
        "\"firmware_image_verified\":false,\"interrupts_enabled\":false,"
        "\"gpu_initialized\":false,\"rm_initialized\":false,"
        "\"execution\":\"native-user-space\",\"kernel_runtime\":\"not_tested\","
        "\"gpu_access\":false}\n", checks, completedRuns, leaseRefusals, workerErrors);
    return 0;
}
