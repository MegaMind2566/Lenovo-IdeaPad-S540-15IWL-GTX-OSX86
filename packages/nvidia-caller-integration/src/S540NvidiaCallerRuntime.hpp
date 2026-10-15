// SPDX-License-Identifier: MIT
#ifndef S540_NVIDIA_CALLER_RUNTIME_HPP
#define S540_NVIDIA_CALLER_RUNTIME_HPP

#include "../../nvidia-os-adapter/upstream/include/nvtypes.h"
#include "../../nvidia-os-adapter/src/S540NvidiaRuntime.hpp"

namespace S540NvidiaCallerRuntime {

constexpr NvU32 kFormatVersion = 1;

struct Result {
    NvU32 checks;
    NvU32 failures;
    bool allocationCallers;
    bool mutexCallers;
    bool reserve;

    bool passed() const {
        return checks != 0 && failures == 0 && allocationCallers &&
               mutexCallers && reserve;
    }
};

// Call once from an ordinary thread with interrupts enabled, no spin lock held,
// and exclusive access to an initially uninitialized S540NvidiaReserve. All
// reserve hooks must remain quiescent outside this call. The finite startup
// sequence creates no workers and never intentionally enters a mutex wait.
// The same production sequence is executed by the native CI harness.
Result run();

struct IntegratedResult {
    S540NvidiaRuntime::Result foundations;
    Result callers;
    bool acquired;
};

// The probe and native harness use this shared entry point. A lock-free,
// nonblocking singleton lease serializes every reserve lifecycle operation.
// A competing invocation is refused immediately, never waited upon. Run the
// new caller sequence first, then the existing foundation sequence with the
// same new OS backends. Return only after quiescent reserve cleanup.
IntegratedResult checkIntegrated();

} // namespace S540NvidiaCallerRuntime

#endif
