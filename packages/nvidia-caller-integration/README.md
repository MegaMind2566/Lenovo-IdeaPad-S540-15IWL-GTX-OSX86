# NVIDIA NVPort caller integration

This development component connects three original NVIDIA allocation callers and five original mutex callers to candidate Darwin backends. Function bodies come from NVIDIA release `615.78.08`, commit `1a82fbfda8f321b056eb3568850f9316c5e465c5`; includes and interface profiles are explicitly adapted. This is not the complete NVPort library or NVIDIA resource manager.

[The earlier targeted Intel macOS CI passed](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/actions/runs/38722294509), including original-caller execution, sanitizers, mandatory assertion failure and kernel compile/link/import checks. The component is now included in the [v0.5.0 transport candidate](../nvidia-transport/README.md), whose exact build results accompany the package. One combined laptop result remains required. Version 0.4.0 remains the confirmed laptop checkpoint. Kernel and interrupt execution of the new backends remain untested.

## Allocation without sleeping

The earlier `IOMalloc` adapter establishes ordinary-thread allocation, while NVIDIA's nonpaged caller contract requires no sleeping. The candidate [reserve backend](src/S540NvidiaReserve.cpp) allocates its backing storage during ordinary-thread initialization, then serves allocations and frees through a lock-free bitmap. Steady-state hooks make no kernel allocator calls and use no sleepable locks.

| Limit | Value |
|---|---|
| Reserve size | 4 MiB |
| Slot count | 32 |
| Maximum request | 128 KiB |
| Payload alignment | 16 bytes |
| Allocation scan | At most 32 atomic slot attempts |
| Allocation failure | Explicit failure for unavailable reserve, oversize, exhaustion or contention |

The reserve is a bounded backend, not a complete RM heap. Larger ordinary-thread RM allocations require later work. Initialization and shutdown require externally serialized lifecycle calls, complete hook quiescence, ordinary thread context and no held spin lock. Shutdown refuses live allocations. Free requires the exact live allocation pointer; stale or duplicate frees violate the caller contract. Native stress does not establish interrupt execution on the laptop.

## Mutex caller contract

The [candidate mutex backend](src/S540NvidiaMutex.cpp) supports the ordinary-thread NVPort mutex profile. Same-owner release, no recursion and quiescent destruction are caller preconditions; they are not inferred from the token state.

The kernel branch protects a binary token with an interrupt-disabled simple lock. Blocking acquire registers an uninterruptible wait while holding that guard, releases it before blocking, and rechecks availability after waking. Conditional acquisition and release use the spin guard and wake primitive without a sleepable mutex. The native pthread branch tests functional semantics, contention and publication; it does not prove the kernel branch's non-sleeping behavior.

The original mandatory acquisition assertion stays active. A failed OS acquisition reaches a real `panic`/`abort` backend and cannot return as a successful unlocked operation. The adapted caller supports caller-owned initialized mutex objects. Tracked allocator ownership, `portSyncMutexCreate`, semaphores, spinlock callers and rwlocks are excluded; an unexpected tracked mutex is an explicit fatal unsupported-contract error.

## Evidence and deployment boundary

The [successful CI run](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/actions/runs/38722294509) used source `df3738eb8a3ab08f3f0668735a42def18c821cd3`. The [provenance records](upstream/README.md) verified exact upstream bytes, function bodies, ABI widths and mutex layout. All 16 hook/caller/assertion symbols resolved in the relocatable kernel object, with exactly 15 platform imports and no static initializers. Native reserve/caller/mutex harnesses passed both plain and under AddressSanitizer/UndefinedBehaviorSanitizer with fatal diagnostics. The failed original acquisition assertion terminated its separate subprocess with SIGABRT. The downloaded report and all 40 source checksums were verified.

The v0.5.0 candidate records its exact source revision and native validation results in the transport package's `BUILD.json`. The shared startup entry point uses a nonblocking singleton lease, runs 35 caller/reserve checks and 23 foundation checks, and releases its resources before the transport's two read-only TU117 identification loads. The startup creates no workers and does not intentionally enter a blocking mutex wait. The deliberate mandatory-assertion failure is exercised only by a separate native CI process.

No new GPU access, firmware, DMA, GPU commands, HAL objects or RM objects are added. The v4 laptop result remains the confirmed hardware checkpoint. The v5 result is pending; kernel contention, interrupt-context allocation, suspend/wake and full RM compatibility remain unvalidated.

## Primary references

- [Pinned NVIDIA memory contract](https://github.com/NVIDIA/open-gpu-kernel-modules/blob/1a82fbfda8f321b056eb3568850f9316c5e465c5/src/nvidia/inc/libraries/nvport/memory.h).
- [Pinned NVIDIA mutex contract](https://github.com/NVIDIA/open-gpu-kernel-modules/blob/1a82fbfda8f321b056eb3568850f9316c5e465c5/src/nvidia/inc/libraries/nvport/sync.h).
- [Pinned Darwin allocator declarations](https://github.com/acidanthera/MacKernelSDK/blob/3f750085caa17ec3a7880f11c11bf4f48cd6a164/Headers/IOKit/IOLib.h) and [lock declarations](https://github.com/acidanthera/MacKernelSDK/blob/3f750085caa17ec3a7880f11c11bf4f48cd6a164/Headers/IOKit/IOLocks.h).
- [Pinned wait/wake declarations](https://github.com/acidanthera/MacKernelSDK/blob/3f750085caa17ec3a7880f11c11bf4f48cd6a164/Headers/kern/sched_prim.h).
