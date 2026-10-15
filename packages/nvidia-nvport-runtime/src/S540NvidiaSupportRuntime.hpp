// SPDX-License-Identifier: MIT
#ifndef S540_NVIDIA_SUPPORT_RUNTIME_HPP
#define S540_NVIDIA_SUPPORT_RUNTIME_HPP

#include "../../nvidia-nvport-lifecycle/src/S540NvidiaLifecycleRuntime.hpp"

namespace S540NvidiaSupportRuntime {

constexpr NvU32 kFormatVersion = 1;

struct Result {
    NvU32 checks;
    NvU32 failures;
    bool core;
    bool utilities;
    bool consumer;
    bool cleanup;

    bool passed() const {
        return checks != 0 && failures == 0 && core && utilities && consumer &&
               cleanup;
    }
};

struct IntegratedResult {
    S540NvidiaLifecycleRuntime::IntegratedResult v6;
    Result support;
    bool acquired;
};

// Execute the confirmed foundation/caller/lifecycle sequences and the checked
// CPU support profile with real NVIDIA container consumers under one shared
// nonblocking lease. This finite ordinary-thread startup creates no workers,
// performs no GPU access and returns all owned resources cold on success.
IntegratedResult checkIntegrated();

} // namespace S540NvidiaSupportRuntime

#endif
