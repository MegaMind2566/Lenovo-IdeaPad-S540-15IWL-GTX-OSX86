// SPDX-License-Identifier: MIT
// Execute the production startup sequence. This is not kernel execution.
#include "../src/S540NvidiaCallerRuntime.hpp"
#include "../src/S540NvidiaReserve.hpp"

#include <cstdio>

int main()
{
    const S540NvidiaCallerRuntime::IntegratedResult integrated =
        S540NvidiaCallerRuntime::checkIntegrated();
    const S540NvidiaCallerRuntime::Result &result = integrated.callers;
    const S540NvidiaRuntime::Result &foundations = integrated.foundations;
    const bool foundationsPassed = foundations.timer && foundations.memory &&
        foundations.atomics && foundations.allocation && foundations.mutex;
    const bool cleaned = !S540NvidiaReserve::ready() &&
        S540NvidiaReserve::liveSlots() == 0;
    std::printf("{\"format\":1,\"component\":\"nvport-caller-runtime\","
                "\"entrypoint\":\"S540NvidiaCallerRuntime::checkIntegrated\","
                "\"status\":\"%s\",\"checks\":%u,\"failures\":%u,"
                "\"allocation_callers\":%s,\"mutex_callers\":%s,"
                "\"reserve\":%s,\"cleaned\":%s,"
                "\"acquired\":%s,\"foundation_checks\":%u,"
                "\"foundations_passed\":%s,\"reserve_cold_after\":%s,"
                "\"execution\":\"native-user-space\","
                "\"kernel_runtime\":\"not_tested\","
                "\"kernel_blocking_wait\":\"not_tested\",\"gpu_access\":false}\n",
                result.passed() && cleaned && integrated.acquired &&
                    foundationsPassed ? "passed" : "failed",
                result.checks, result.failures,
                result.allocationCallers ? "true" : "false",
                result.mutexCallers ? "true" : "false",
                result.reserve ? "true" : "false",
                cleaned ? "true" : "false",
                integrated.acquired ? "true" : "false", foundations.checks,
                foundationsPassed ? "true" : "false", cleaned ? "true" : "false");
    return result.passed() && cleaned && integrated.acquired &&
        foundationsPassed ? 0 : 1;
}
