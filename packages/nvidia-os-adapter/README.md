# NVIDIA Darwin OS adapter

CPU-only foundations for the S540 NVIDIA port: monotonic clocks, ordinary-RAM primitives and the original NVIDIA atomic headers. [Combined GitHub validation passed](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/actions/runs/38696607911) for kernel-object compilation/linking, import auditing and native userspace execution. The confirmed v0.3.0 PCI identification probe is unchanged.

There is no laptop installer or standalone kext package for these components. Build and CPU behavior checks run in GitHub Actions. Laptop tests will combine components into meaningful integration milestones; full validation follows the implementation stages.

## Source boundary

Sources are pinned to NVIDIA release `615.78.08`, commit `1a82fbfda8f321b056eb3568850f9316c5e465c5`. The [upstream directory](upstream/README.md) records original blob identities, adapted caller ranges and licensing. ABI and atomic headers are retained unchanged. The time and memory callers are explicitly adapted excerpts, not complete upstream modules or resource-manager integration.

## Monotonic clocks

The [uptime excerpt](upstream/nvport_time_uptime.c) retains four upstream function signatures and bodies: microseconds, ordinary nanoseconds, high-precision nanoseconds and resolution. Includes and build guards are narrowed; wall-clock functions and their separate OS dependency are excluded.

The [Darwin backend](src/S540NvidiaClock.cpp) preserves NVIDIA's exact C hook ABI. Kernel code uses `clock_get_uptime` and `absolutetime_to_nanoseconds`; the native userspace harness uses `mach_absolute_time` and its timebase. Uptime excludes sleep and is independent of wall-clock adjustments.

| Hook | Contract |
|---|---|
| `os_get_monotonic_time_ns` | Nanoseconds rounded down to a logical 1 ms quantum |
| `os_get_monotonic_time_ns_hr` | Raw uptime converted to nanoseconds |
| `os_get_monotonic_tick_resolution_ns` | `1,000,000` ns, the adapter's ordinary-clock quantum |

The quantum is software policy, not measured hardware or scheduler precision. Timebase numerator and denominator define conversion units, not resolution. The hook ABI has no error channel; backend preflight must succeed before future runtime binding.

## Ordinary-RAM primitives

The [memory backend](src/S540NvidiaMemory.cpp) implements the exact `os_mem_copy`, `os_mem_set` and `os_mem_cmp` declarations using Darwin's `memcpy`, `memset` and `memcmp`. The hooks retain their 32-bit length ABI. Four [adapted nvport callers](upstream/nvport_memory_primitives.c)—`portMemCopy`, `portMemCopyAligned`, `portMemSet` and `portMemCmp`—use private bridges to preserve the 64-bit `NvLength` through bounded 32-bit chunks.

The caller uses the upstream **release assertion profile only**. Checked-build diagnostics are not implemented. Copy buffers must not overlap, and every nonzero range must be valid ordinary CPU-accessible RAM. This component adds no allocator, user-copy, generic move, mapping, DMA or MMIO support.

Targeted checks cover real small-buffer behavior and chunk planning at 32/64-bit edges. They do not execute copies, fills or comparisons over buffers larger than 4 GiB.

## Atomic header integration

[S540NvidiaAtomic.h](src/S540NvidiaAtomic.h) configures the unmodified nvport atomic-header closure for Intel x86_64 Clang. GNU C11 uses the original C11 implementation and pinned freestanding `stdatomic.h`; C++17 uses the original Clang intrinsics. Compiler selection is checked directly, rather than forcing one implementation for both languages.

The consumers exercise the original CPU atomic operations and fences. This header integration adds no resource-manager objects, GPU synchronization or kernel runtime validation. NVIDIA MIT notices and the LLVM license for the bundled atomic header are retained.

## Validation boundary

The [successful combined run](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/actions/runs/38696607911) used source commit `83d3ae7b2ce19215c73f8c89437257a3e7ac960c`. It passed provenance and targeted policy checks, compiled clock and memory backends with the adapted callers and produced two relocatable kernel-object links, one for each atomic language consumer. The import audit found exactly the three Apple clock functions plus `memcpy`, `memset` and `memcmp`, with no atomic runtime helpers.

Native userspace execution passed for the actual clock and memory callers and both original atomic implementations. Atomic checks cover semantics, four-thread contention and publication. The real memory backend also passed AddressSanitizer and UndefinedBehaviorSanitizer execution. Kernel runtime, suspend behavior, buffers larger than 4 GiB and GPU deadlines remain unvalidated.

No component accesses GPU registers, changes power, performs DMA or loads firmware. NVIDIA HAL instantiation, resource-manager integration and GPU initialization remain unimplemented. Software deadlines cannot make a stalled MMIO load recoverable.

## Primary references

- [Pinned NVIDIA source](https://github.com/NVIDIA/open-gpu-kernel-modules/tree/1a82fbfda8f321b056eb3568850f9316c5e465c5), with local [provenance manifests](upstream/README.md).
- [NVIDIA deadline consumer](https://github.com/NVIDIA/open-gpu-kernel-modules/blob/1a82fbfda8f321b056eb3568850f9316c5e465c5/src/nvidia/src/kernel/gpu/gpu_timeout.c#L282-L302).
- [Pinned Darwin clock declarations](https://github.com/acidanthera/MacKernelSDK/blob/3f750085caa17ec3a7880f11c11bf4f48cd6a164/Headers/kern/clock.h#L86-L115).
