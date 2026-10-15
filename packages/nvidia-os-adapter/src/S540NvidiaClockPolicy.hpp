// SPDX-License-Identifier: MIT
#ifndef S540_NVIDIA_CLOCK_POLICY_HPP
#define S540_NVIDIA_CLOCK_POLICY_HPP

#include "../upstream/include/nvtypes.h"

namespace S540NvidiaClock {

// This is the adapter's explicit software quantum for the ordinary clock.
// It is not a measurement of the physical clock or scheduler timer precision.
static constexpr NvU64 kCoarseQuantumNS = 1000000ULL;

inline NvU64 coarseNanoseconds(NvU64 nanoseconds) {
    return nanoseconds - nanoseconds % kCoarseQuantumNS;
}

// Compute floor(ticks * numer / denom) without an overflowing intermediate or
// a 128-bit division runtime dependency. The remainder product fits in 64 bits
// because both the remainder and numerator are bounded by 32-bit values.
inline bool ticksToNanoseconds(NvU64 ticks, NvU32 numer, NvU32 denom,
                               NvU64 &result) {
    result = 0;
    if (numer == 0 || denom == 0)
        return false;
    const NvU64 maximum = ~NvU64(0);
    const NvU64 quotient = ticks / denom;
    const NvU64 remainder = ticks % denom;
    if (quotient > maximum / numer)
        return false;
    const NvU64 whole = quotient * numer;
    const NvU64 fraction = (remainder * numer) / denom;
    if (whole > maximum - fraction)
        return false;
    result = whole + fraction;
    return true;
}

} // namespace S540NvidiaClock

#endif
