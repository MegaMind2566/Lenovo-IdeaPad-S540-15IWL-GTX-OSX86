// SPDX-License-Identifier: MIT
#ifndef S540_NVIDIA_SYNC_HPP
#define S540_NVIDIA_SYNC_HPP

#include "../upstream/include/nvtypes.h"
#include "../upstream/include/nvstatus.h"
#include "../upstream/include/nv-kernel-interface-api.h"

// This is the exact NVIDIA OS-hook ABI declared in reference/os-interface.h.
// Supported callers run in ordinary schedulable thread context, with interrupts
// enabled and no spin lock held. Mutexes are nonrecursive; only their owner may
// release them. Destroy only unlocked mutexes with no waiters or future users.
// Interrupt/spin locks, timed waits, ownership handoff and rwlocks are excluded.
extern "C" {
NV_STATUS NV_API_CALL os_alloc_mutex(void **);
void NV_API_CALL os_free_mutex(void *);
NV_STATUS NV_API_CALL os_acquire_mutex(void *);
NV_STATUS NV_API_CALL os_cond_acquire_mutex(void *);
void NV_API_CALL os_release_mutex(void *);
}

#endif
