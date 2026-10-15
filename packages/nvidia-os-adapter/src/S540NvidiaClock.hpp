// SPDX-License-Identifier: MIT
#ifndef S540_NVIDIA_CLOCK_HPP
#define S540_NVIDIA_CLOCK_HPP

#include "S540NvidiaClockPolicy.hpp"
#include "../upstream/nvport_time_uptime.h"

namespace S540NvidiaClock {

// The NVIDIA ABI has no error return for these hooks. Timestamp hooks return
// zero if the native backend cannot supply a valid value. The resolution hook
// declares the fixed software quantum. A caller must require a successful
// preflight before binding this adapter to future NVIDIA runtime consumers.
bool backendReady();

} // namespace S540NvidiaClock

#endif
