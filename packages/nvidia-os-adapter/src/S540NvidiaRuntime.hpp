// SPDX-License-Identifier: MIT
#ifndef S540_NVIDIA_RUNTIME_HPP
#define S540_NVIDIA_RUNTIME_HPP

namespace S540NvidiaRuntime {
struct Result {
    unsigned checks;
    bool timer;
    bool memory;
    bool atomics;
    bool allocation;
    bool mutex;
    bool passed() const { return timer && memory && atomics && allocation && mutex; }
};

// Execute once from a sleepable thread with no driver locks held. Bounded
// ordinary-RAM operations only. No worker threads, GPU access or global state.
Result check();
}
#endif
