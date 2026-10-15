// SPDX-License-Identifier: MIT
// Native user-space execution of the real backend and adapted upstream caller.
#include "../src/S540NvidiaClock.hpp"
#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <ctime>

static unsigned int checks = 0;
static void require(bool condition, const char *message) {
    ++checks;
    if (!condition) {
        std::fprintf(stderr, "Clock check failed: %s\n", message);
        std::exit(1);
    }
}

int main() {
    static_assert(sizeof(NvU64) == 8, "NVIDIA uptime ABI must be 64-bit.");
    require(S540NvidiaClock::backendReady(), "native backend preflight");
    const NvU64 quantum = portTimeGetUptimeResolution();
    require(quantum == 1000000ULL, "declared 1 ms software quantum");
    require(os_get_monotonic_tick_resolution_ns() == quantum, "caller resolution ABI");
    NvU64 previousCoarse = 0, previousHR = 0;
    for (unsigned int index = 0; index < 16; ++index) {
        const NvU64 before = portTimeGetUptimeNanosecondsHighPrecision();
        const NvU64 coarse = portTimeGetUptimeNanoseconds();
        const NvU64 after = portTimeGetUptimeNanosecondsHighPrecision();
        require(before <= after && before >= previousHR, "nondecreasing high-precision uptime");
        require(coarse >= previousCoarse && coarse % quantum == 0, "coarse uptime and declared quantum");
        require(coarse >= S540NvidiaClock::coarseNanoseconds(before) &&
                coarse <= S540NvidiaClock::coarseNanoseconds(after), "coarse clock lies inside HR bounds");
        const NvU64 microseconds = portTimeGetUptimeMicroseconds();
        const NvU64 end = portTimeGetUptimeNanoseconds();
        require(microseconds >= coarse / 1000 && microseconds <= end / 1000,
                "upstream microsecond conversion");
        previousCoarse = end;
        previousHR = after;
    }
    const NvU64 start = portTimeGetUptimeNanoseconds();
    require(start <= ~NvU64(0) - 2 * quantum, "deadline does not wrap");
    const NvU64 deadline = start + 2 * quantum;
    timespec remaining = {0, 5000000};
    bool slept = false;
    for (unsigned int attempt = 0; attempt < 3; ++attempt) {
        timespec next = {};
        if (nanosleep(&remaining, &next) == 0) { slept = true; break; }
        if (errno != EINTR) break;
        remaining = next;
    }
    require(slept, "bounded native wait completed");
    require(portTimeGetUptimeNanoseconds() >= deadline, "native clock deadline expired");
    require(S540NvidiaClock::backendReady(), "native backend remains valid");
    std::printf("{\"format\":1,\"status\":\"passed\",\"checks\":%u,"
                "\"coarse_quantum_ns\":1000000,\"uptime_callers\":4,"
                "\"execution\":\"native-user-space\",\"kernel_runtime\":\"not_tested\","
                "\"gpu_access\":false}\n", checks);
    return 0;
}
