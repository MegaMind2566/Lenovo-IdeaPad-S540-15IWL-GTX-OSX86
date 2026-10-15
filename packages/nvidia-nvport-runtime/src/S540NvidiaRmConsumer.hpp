// SPDX-License-Identifier: MIT
#ifndef S540_NVIDIA_RM_CONSUMER_HPP
#define S540_NVIDIA_RM_CONSUMER_HPP
#include "../../nvidia-nvport-lifecycle/upstream/nvport_lifecycle.h"

namespace S540NvidiaRmConsumer {
struct Result {
    NvU32 checks;
    NvU32 failures;
    bool vector;
    bool list;
    bool allocationFailure;
    bool cleanup;
    bool passed() const {
        return checks != 0 && failures == 0 && vector && list &&
            allocationFailure && cleanup;
    }
};

// Runs under the caller's ordinary-thread lifecycle lease, with an initialized
// reserve and memory subsystem. Does not initialize or shut down either one.
// This is an original RM-library container consumer, not a live RM instance.
Result check(PORT_MEM_ALLOCATOR *allocator);
}
#endif
