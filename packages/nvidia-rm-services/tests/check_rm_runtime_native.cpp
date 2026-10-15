// SPDX-License-Identifier: MIT
// Executes the production aggregate through explicit native host backends.
#include "../src/S540NvidiaRmRuntime.hpp"
#include "../memory/S540NvidiaRmMemory.hpp"
#include "../../nvidia-caller-integration/src/S540NvidiaReserve.hpp"
#include "../../nvidia-caller-integration/src/S540NvidiaMutex.hpp"
#include "../../nvidia-nvport-lifecycle/src/S540NvidiaSpinlock.hpp"
#include "../../nvidia-nvport-runtime/upstream/nvport_runtime.h"
#include <cstdio>

int main()
{
    const auto integrated = S540NvidiaRmRuntime::checkIntegrated(nullptr);
    const auto &result = integrated.services;
    const auto &v8 = integrated.v8;
    const auto &v7 = v8.v7;
    const bool previous = integrated.acquired && v8.acquired && v7.acquired &&
        v7.v6.acquired && v7.v6.v5.acquired &&
        v7.v6.v5.foundations.passed() && v7.v6.v5.callers.passed() &&
        v7.v6.lifecycle.passed() && v7.support.passed() && v8.preparation.passed();
    const auto memory = S540NvidiaRmMemory::statistics();
    const bool cold = !S540NvidiaReserve::ready() &&
        S540NvidiaReserve::liveSlots() == 0 &&
        s540NvportRuntimeIsCold() == NV_TRUE &&
        !S540NvidiaRmMemory::ready() && memory.allocations == 0 &&
        memory.mappings == 0 && memory.deferred == 0 && memory.bytes == 0;
    const bool objects = S540NvidiaMutex::liveObjects() == 0 &&
        S540NvidiaSpinlock::liveObjects() == 0 &&
        S540NvidiaRmMemory::nativeLiveResources() == 0 &&
        S540NvidiaRmMemory::nativeIllegalOperations() == 0;
    const bool passed = previous && result.passed() && cold && objects;
    std::printf("{\"format\":1,\"component\":\"nvidia-rm-services-runtime\","
        "\"entrypoint\":\"S540NvidiaRmRuntime::checkIntegrated\","
        "\"status\":\"%s\",\"checks\":%u,\"failures\":%u,"
        "\"previous_cpu_checks\":258,\"preparation_checks\":%u,"
        "\"previous_blocks_passed\":%s,\"acquired\":%s,"
        "\"resource_server\":%s,\"host_memory\":%s,\"pci_session\":%s,"
        "\"clients\":%s,\"resources\":%s,\"sharing\":%s,\"control\":%s,"
        "\"cleanup\":%s,\"resource_server_checks\":%u,"
        "\"host_memory_checks\":%u,\"pci_session_checks\":%u,"
        "\"profile\":\"%s\",\"cold_after\":%s,\"os_objects_released\":%s,"
        "\"full_rm_initialized\":false,\"firmware_loaded\":false,"
        "\"gpu_initialized\":false,\"device_dma_verified\":false,"
        "\"interrupts_enabled\":false,\"execution\":\"native-user-space\","
        "\"kernel_runtime\":\"not_tested\",\"gpu_access\":false}\n",
        passed ? "passed" : "failed", result.checks, result.failures,
        v8.preparation.checks, previous ? "true" : "false",
        integrated.acquired ? "true" : "false",
        result.resourceServer ? "true" : "false",
        result.hostMemory ? "true" : "false", result.pciSession ? "true" : "false",
        result.clients ? "true" : "false", result.resources ? "true" : "false",
        result.sharing ? "true" : "false", result.control ? "true" : "false",
        result.cleanup ? "true" : "false", result.resourceServerChecks,
        result.hostMemoryChecks, result.pciSessionChecks, result.profile,
        cold ? "true" : "false", objects ? "true" : "false");
    return passed ? 0 : 1;
}
