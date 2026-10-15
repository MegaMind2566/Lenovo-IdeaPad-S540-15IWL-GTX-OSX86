// SPDX-License-Identifier: MIT
#include "S540NvidiaClock.hpp"

#if defined(KERNEL)
#include <kern/clock.h>
#else
#include <mach/kern_return.h>
#include <mach/mach_time.h>
#endif

static_assert(sizeof(NvU64) == 8 && alignof(NvU64) == 8,
              "The clock adapter requires NVIDIA's 64-bit unsigned ABI.");

namespace {

bool highPrecisionNanoseconds(NvU64 &result) {
    result = 0;
#if defined(KERNEL)
    // These are read-only Darwin uptime APIs. Absolute uptime excludes sleep;
    // no wall clock, timer, delay, allocation, or GPU operation is involved.
    uint64_t ticks = 0;
    uint64_t nanoseconds = 0;
    clock_get_uptime(&ticks);
    absolutetime_to_nanoseconds(ticks, &nanoseconds);
    result = static_cast<NvU64>(nanoseconds);
    return true;
#else
    mach_timebase_info_data_t timebase = {};
    if (mach_timebase_info(&timebase) != KERN_SUCCESS)
        return false;
    const NvU64 ticks = static_cast<NvU64>(mach_absolute_time());
    return S540NvidiaClock::ticksToNanoseconds(ticks, timebase.numer,
                                              timebase.denom, result);
#endif
}

} // namespace

bool S540NvidiaClock::backendReady() {
#if defined(KERNEL)
    mach_timebase_info_data_t timebase = {};
    clock_timebase_info(&timebase);
    uint64_t ticks = 0;
    uint64_t nanoseconds = 0;
    clock_get_uptime(&ticks);
    absolutetime_to_nanoseconds(ticks, &nanoseconds);
    NvU64 checked = 0;
    return ticksToNanoseconds(static_cast<NvU64>(ticks), timebase.numer,
                              timebase.denom, checked)
        && checked == static_cast<NvU64>(nanoseconds);
#else
    NvU64 result = 0;
    return highPrecisionNanoseconds(result);
#endif
}

extern "C" NvU64 NV_API_CALL os_get_monotonic_time_ns(void) {
    NvU64 nanoseconds = 0;
    if (!highPrecisionNanoseconds(nanoseconds))
        return 0;
    return S540NvidiaClock::coarseNanoseconds(nanoseconds);
}

extern "C" NvU64 NV_API_CALL os_get_monotonic_time_ns_hr(void) {
    NvU64 nanoseconds = 0;
    return highPrecisionNanoseconds(nanoseconds) ? nanoseconds : 0;
}

extern "C" NvU64 NV_API_CALL os_get_monotonic_tick_resolution_ns(void) {
    return S540NvidiaClock::kCoarseQuantumNS;
}
