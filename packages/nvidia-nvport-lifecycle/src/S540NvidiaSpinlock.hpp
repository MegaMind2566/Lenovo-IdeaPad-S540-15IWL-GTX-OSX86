// SPDX-License-Identifier: MIT
#ifndef S540_NVIDIA_SPINLOCK_HPP
#define S540_NVIDIA_SPINLOCK_HPP

#include "../../nvidia-os-adapter/upstream/include/nvtypes.h"
#include "../../nvidia-os-adapter/upstream/include/nvstatus.h"
#include "../../nvidia-os-adapter/upstream/include/nv-kernel-interface-api.h"

// Creation and destruction require an ordinary schedulable thread, interrupts
// enabled, no held spin lock, and externally serialized lifetime management.
// Acquisitions are nonrecursive and releases must be balanced on the acquiring
// thread with the exact saved interrupt-state token. Destroy only after every
// user has finished and the lock is released. These are caller preconditions;
// the kernel adapter does not infer ownership or lifetime from lock storage.
// The guarded kernel path makes no heap, sleep, wait, or logging calls.
extern "C" {
NV_STATUS NV_API_CALL os_alloc_spinlock(void **);
void NV_API_CALL os_free_spinlock(void *);
NvU64 NV_API_CALL os_acquire_spinlock(void *);
void NV_API_CALL os_release_spinlock(void *, NvU64);
}

namespace S540NvidiaSpinlock {
// Fully created backing objects; quiescent lifetime checks may compare a
// baseline with this count after the owning lifecycle has finished.
NvU32 liveObjects();
} // namespace S540NvidiaSpinlock

#if !defined(KERNEL)
// Native functional-test controls. Simulated TLS interrupt state is not an
// actual CPU interrupt mask and pthread execution proves no kernel IRQ timing.
namespace S540NvidiaSpinlockNative {
enum class Failure : NvU32 { None, Storage, Initialization };
void failNextAllocation(Failure failure);
void setContext(bool interruptContext, bool interruptsEnabled);
bool interruptsEnabled();
bool contextAllowed();
NvU32 liveObjects();
} // namespace S540NvidiaSpinlockNative
#endif

#endif
