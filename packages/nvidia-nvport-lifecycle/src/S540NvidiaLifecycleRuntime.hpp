// SPDX-License-Identifier: MIT
#ifndef S540_NVIDIA_LIFECYCLE_RUNTIME_HPP
#define S540_NVIDIA_LIFECYCLE_RUNTIME_HPP

#include "../../nvidia-caller-integration/src/S540NvidiaCallerRuntime.hpp"

namespace S540NvidiaLifecycleRuntime {

constexpr NvU32 kFormatVersion = 1;

struct Result {
    NvU32 checks;
    NvU32 failures;
    bool lifecycle;
    bool trackedAllocation;
    bool ownedMutex;
    bool spinlocks;
    bool cleanup;

    bool passed() const {
        return checks != 0 && failures == 0 && lifecycle &&
               trackedAllocation && ownedMutex && spinlocks && cleanup;
    }
};

struct IntegratedResult {
    S540NvidiaCallerRuntime::IntegratedResult v5;
    Result lifecycle;
    bool acquired;
};

// Run the existing foundation/caller checkpoint and the original NvPort memory
// and owned synchronization lifecycle under the same nonblocking startup
// lease. The finite production sequence runs only in an ordinary thread with
// interrupts enabled. It creates no workers, never intentionally waits on a
// mutex, and does not access GPU registers or initialize hardware. All NvPort
// objects and reserve allocations are released before returning.
IntegratedResult checkIntegrated();

} // namespace S540NvidiaLifecycleRuntime

#endif
