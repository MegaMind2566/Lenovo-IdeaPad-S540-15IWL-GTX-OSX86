// SPDX-License-Identifier: MIT
#ifndef S540_NVIDIA_MUTEX_HPP
#define S540_NVIDIA_MUTEX_HPP

#include "../../nvidia-os-adapter/upstream/include/nvtypes.h"
#include "../../nvidia-os-adapter/upstream/include/nvstatus.h"
#include "../../nvidia-os-adapter/upstream/include/nv-kernel-interface-api.h"

// Restricted to the actual NVPort PORT_MUTEX owner-thread contract: ordinary
// schedulable threads, interrupts enabled, no spin lock held. Nonrecursive;
// acquire and release must be balanced by the same thread. Destroy only after
// all users and waiters have finished, with the token released.
// A failed startup check may instead abort-destroy its exclusively owned
// backing object after every hook has returned and with no owner or waiter;
// an unexpectedly unavailable token is never recovered or reused in that case.
// Raw Linux ownerless semaphore use, interrupt callers, timed waits and rwlocks are not
// implemented by this component. Context guards cannot detect every held lock.
extern "C" {
NV_STATUS NV_API_CALL os_alloc_mutex(void **);
void NV_API_CALL os_free_mutex(void *);
NV_STATUS NV_API_CALL os_acquire_mutex(void *);
NV_STATUS NV_API_CALL os_cond_acquire_mutex(void *);
void NV_API_CALL os_release_mutex(void *);
}

namespace S540NvidiaMutex {
// Component-owned OS backing objects, counted only after successful creation
// and after complete quiescent destruction. This is not a lifetime lock.
NvU32 liveObjects();
}

#if !defined(KERNEL)
namespace S540NvidiaMutexNative {
// Faults enter the real native allocation/unwind paths. They are excluded
// from the kernel build and do not simulate kernel allocator behavior.
enum class Failure : NvU32 { Storage = 1, Guard = 2, Condition = 3 };
void failNextAllocation(Failure failure);
}
#endif

#endif
