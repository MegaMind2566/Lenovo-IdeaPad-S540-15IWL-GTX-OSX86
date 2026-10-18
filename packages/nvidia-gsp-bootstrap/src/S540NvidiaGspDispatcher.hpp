// SPDX-License-Identifier: MIT
#ifndef S540_NVIDIA_GSP_DISPATCHER_HPP
#define S540_NVIDIA_GSP_DISPATCHER_HPP
#include "../../nvidia-os-adapter/upstream/include/nvtypes.h"
#include "../../nvidia-os-adapter/upstream/include/nvstatus.h"

namespace S540NvidiaGspBootstrap {
// A persistent ordinary thread, unlike a thread_call pool whose thread identity
// can change between operations. It does not enlarge or switch kernel stacks.
class Dispatcher {
public:
    using Action = NV_STATUS (*)(void *, NvU32);
    struct Snapshot {
        bool started, accepting, workerFinished, stopped;
        NvU32 pending;
        NvU64 workerThread, accepted, completed, postedFailures;
        NV_STATUS lastPostedStatus;
    };
    Dispatcher();
    ~Dispatcher();
    // start/stop/destruction are externally serialized. invoke/post may have
    // concurrent callers after start returns, until the destruction barrier.
    NV_STATUS start(Action, void *);
    NV_STATUS invoke(NvU32 command);
    // Preallocated queue, no sleep or allocation. Acceptance is not completion;
    // the action performs its own asynchronous completion (for example PM ack).
    NV_STATUS post(NvU32 command);
    // Closes admission and drains every accepted action. Call outside worker.
    // Callers must prevent new calls before destroying the facade. A failed
    // stop retains its storage; it must be retried on an ordinary thread.
    NV_STATUS stop();
    Snapshot snapshot() const;
private:
    struct Impl;
    Impl *impl_;
    Dispatcher(const Dispatcher &) = delete;
    Dispatcher &operator=(const Dispatcher &) = delete;
};
}
#endif
