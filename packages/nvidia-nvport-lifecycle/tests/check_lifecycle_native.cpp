// SPDX-License-Identifier: MIT
// Execute the same production sequence as the probe, in native user space.
#include "../src/S540NvidiaLifecycleRuntime.hpp"
#include "../../nvidia-caller-integration/src/S540NvidiaReserve.hpp"

#include <cstdio>

int main()
{
    const auto integrated = S540NvidiaLifecycleRuntime::checkIntegrated();
    const auto &result = integrated.lifecycle;
    const auto &foundations = integrated.v5.foundations;
    const bool foundationsPassed = foundations.timer && foundations.memory &&
        foundations.atomics && foundations.allocation && foundations.mutex;
    const bool cleaned = !S540NvidiaReserve::ready() &&
        S540NvidiaReserve::liveSlots() == 0;
    const bool passed = integrated.acquired && integrated.v5.acquired &&
        foundationsPassed && integrated.v5.callers.passed() &&
        result.passed() && cleaned;
    std::printf("{\"format\":1,\"component\":\"nvport-lifecycle-runtime\","
                "\"entrypoint\":\"S540NvidiaLifecycleRuntime::checkIntegrated\","
                "\"status\":\"%s\",\"checks\":%u,\"failures\":%u,"
                "\"lifecycle\":%s,\"tracked_allocation\":%s,"
                "\"owned_mutex\":%s,\"spinlocks\":%s,\"cleanup\":%s,"
                "\"acquired\":%s,\"foundation_checks\":%u,"
                "\"foundations_passed\":%s,\"caller_checks\":%u,"
                "\"callers_passed\":%s,\"reserve_cold_after\":%s,"
                "\"execution\":\"native-user-space\","
                "\"kernel_runtime\":\"not_tested\","
                "\"kernel_blocking_wait\":\"not_tested\","
                "\"gpu_access\":false}\n",
                passed ? "passed" : "failed", result.checks, result.failures,
                result.lifecycle ? "true" : "false",
                result.trackedAllocation ? "true" : "false",
                result.ownedMutex ? "true" : "false",
                result.spinlocks ? "true" : "false",
                result.cleanup ? "true" : "false",
                integrated.acquired ? "true" : "false", foundations.checks,
                foundationsPassed ? "true" : "false",
                integrated.v5.callers.checks,
                integrated.v5.callers.passed() ? "true" : "false",
                cleaned ? "true" : "false");
    return passed ? 0 : 1;
}
