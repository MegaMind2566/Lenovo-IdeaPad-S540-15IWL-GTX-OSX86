// SPDX-License-Identifier: MIT
// Execute the exact finite production entry point in native user space.
#include "../src/S540NvidiaSupportRuntime.hpp"
#include "../upstream/nvport_runtime.h"
#include "../../nvidia-caller-integration/src/S540NvidiaReserve.hpp"
#include "../../nvidia-caller-integration/src/S540NvidiaMutex.hpp"
#include "../../nvidia-nvport-lifecycle/src/S540NvidiaSpinlock.hpp"

#include <cstdio>

int main()
{
    const NvU32 mutexBaseline = S540NvidiaMutex::liveObjects();
    const NvU32 spinlockBaseline = S540NvidiaSpinlock::liveObjects();
    const auto integrated = S540NvidiaSupportRuntime::checkIntegrated();
    const auto &result = integrated.support;
    const auto &foundations = integrated.v6.v5.foundations;
    const bool previousPassed = integrated.v6.acquired &&
        integrated.v6.v5.acquired && foundations.timer && foundations.memory &&
        foundations.atomics && foundations.allocation && foundations.mutex &&
        integrated.v6.v5.callers.passed() && integrated.v6.lifecycle.passed();
    const bool reserveCold = !S540NvidiaReserve::ready() &&
        S540NvidiaReserve::liveSlots() == 0;
    const bool coreCold = s540NvportRuntimeIsCold() == NV_TRUE;
    const bool objectsReleased = S540NvidiaMutex::liveObjects() == mutexBaseline &&
        S540NvidiaSpinlock::liveObjects() == spinlockBaseline;
    const bool passed = integrated.acquired && previousPassed && result.passed() &&
        reserveCold && coreCold && objectsReleased;
    std::printf("{\"format\":1,\"component\":\"nvport-support-runtime\","
                "\"entrypoint\":\"S540NvidiaSupportRuntime::checkIntegrated\","
                "\"status\":\"%s\",\"checks\":%u,\"failures\":%u,"
                "\"core\":%s,\"utilities\":%s,\"consumer\":%s,\"cleanup\":%s,"
                "\"acquired\":%s,\"foundation_checks\":%u,\"caller_checks\":%u,"
                "\"lifecycle_checks\":%u,\"previous_blocks_passed\":%s,"
                "\"reserve_cold_after\":%s,\"core_cold_after\":%s,"
                "\"os_objects_released\":%s,\"execution\":\"native-user-space\","
                "\"kernel_runtime\":\"not_tested\","
                "\"kernel_blocking_wait\":\"not_tested\",\"gpu_access\":false}\n",
                passed ? "passed" : "failed", result.checks, result.failures,
                result.core ? "true" : "false",
                result.utilities ? "true" : "false",
                result.consumer ? "true" : "false",
                result.cleanup ? "true" : "false",
                integrated.acquired ? "true" : "false", foundations.checks,
                integrated.v6.v5.callers.checks, integrated.v6.lifecycle.checks,
                previousPassed ? "true" : "false", reserveCold ? "true" : "false",
                coreCold ? "true" : "false", objectsReleased ? "true" : "false");
    return passed ? 0 : 1;
}
