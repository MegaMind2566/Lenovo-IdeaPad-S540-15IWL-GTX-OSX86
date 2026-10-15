# NVIDIA NVPort caller integration

This development component connects three original NVIDIA allocation callers and five original mutex callers to candidate Darwin backends. Function bodies come from NVIDIA release `615.78.08`, commit `1a82fbfda8f321b056eb3568850f9316c5e465c5`; includes and interface profiles are explicitly adapted. This is not the complete NVPort library or NVIDIA resource manager.

Targeted Intel macOS CI is pending. The confirmed v0.4.0 laptop probe and its sources are unchanged. This component has no kext or laptop installation package. Kernel and interrupt execution of these candidate backends remain untested.

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

The [provenance records](upstream/README.md) verify exact upstream bytes, function bodies, ABI widths and mutex layout. CI compiles and relocatably links the candidate kernel backends with the actual C callers, audits the remaining imports and static initializers, and executes native reserve/caller/mutex harnesses. AddressSanitizer and UndefinedBehaviorSanitizer instrument the actual sources with fatal diagnostics. A separate subprocess must abort through the original failed-acquisition assertion.

No PCI or MMIO access, firmware, DMA, GPU commands, HAL objects or RM objects are added. The v4 laptop result remains the confirmed hardware checkpoint. A later combined kernel milestone is required before using these candidate backends on the laptop.

## Primary references

- [Pinned NVIDIA memory contract](https://github.com/NVIDIA/open-gpu-kernel-modules/blob/1a82fbfda8f321b056eb3568850f9316c5e465c5/src/nvidia/inc/libraries/nvport/memory.h).
- [Pinned NVIDIA mutex contract](https://github.com/NVIDIA/open-gpu-kernel-modules/blob/1a82fbfda8f321b056eb3568850f9316c5e465c5/src/nvidia/inc/libraries/nvport/sync.h).
- [Pinned Darwin allocator declarations](https://github.com/acidanthera/MacKernelSDK/blob/3f750085caa17ec3a7880f11c11bf4f48cd6a164/Headers/IOKit/IOLib.h) and [lock declarations](https://github.com/acidanthera/MacKernelSDK/blob/3f750085caa17ec3a7880f11c11bf4f48cd6a164/Headers/IOKit/IOLocks.h).
- [Pinned wait/wake declarations](https://github.com/acidanthera/MacKernelSDK/blob/3f750085caa17ec3a7880f11c11bf4f48cd6a164/Headers/kern/sched_prim.h).
