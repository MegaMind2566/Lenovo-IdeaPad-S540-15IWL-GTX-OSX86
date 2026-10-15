# NVIDIA Darwin OS adapter

A CPU-only component for the S540 NVIDIA port. It connects NVIDIA's uptime caller to Darwin monotonic clocks. The clock implementation passed [GitHub validation](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/actions/runs/38694368596); kernel runtime remains unvalidated. The confirmed v0.3.0 PCI identification probe is unchanged.

This component has no laptop installer or standalone kext package. Build and CPU behavior checks run in GitHub Actions. The next laptop test will combine adapter components into a meaningful integration milestone.

## Source and interface

The [adapted uptime excerpt](upstream/nvport_time_uptime.c) retains the signatures and bodies of four functions from NVIDIA release `615.78.08`, commit `1a82fbfda8f321b056eb3568850f9316c5e465c5`: uptime microseconds, ordinary nanoseconds, high-precision nanoseconds and resolution. Includes and build guards are narrowed for this component; this is not the unchanged complete upstream time module. The three NVIDIA ABI headers are retained unchanged, with [source provenance](upstream/PROVENANCE.json) and MIT notices. Wall-clock functions and their separate OS dependency are excluded explicitly.

The [Darwin backend](src/S540NvidiaClock.cpp) implements the exact C hook declarations. Kernel code uses `clock_get_uptime` and `absolutetime_to_nanoseconds`; the native userspace harness uses `mach_absolute_time` and its timebase. Uptime excludes sleep and is independent of wall-clock adjustments.

| Hook | Contract |
|---|---|
| `os_get_monotonic_time_ns` | Nanoseconds rounded down to a logical 1 ms quantum |
| `os_get_monotonic_time_ns_hr` | Raw uptime converted to nanoseconds |
| `os_get_monotonic_tick_resolution_ns` | `1,000,000` ns, the adapter's ordinary-clock quantum |

The 1 ms value is a software policy, not measured hardware or scheduler precision. Timebase numerator and denominator define conversion units, not resolution. The NVIDIA hook ABI has no error channel; backend preflight must succeed before any future runtime binding.

## GitHub validation boundary

The GitHub run passed provenance checks, compiled the adapted C caller and kernel backend, produced a relocatable link and verified the exact three Apple clock imports. The native userspace harness exercised the real caller and backend, with targeted checks for conversion, monotonicity, quantization and deadline behavior. These results establish compile/link compatibility and the tested userspace behavior. Kernel runtime, suspend behavior and GPU deadline operation remain unvalidated.

The adapter performs no GPU access, register reads or writes, power operations, DMA or firmware loading. It does not instantiate a HAL, integrate NVIDIA's resource manager or initialize the GPU. Clock-based deadlines cannot make a stalled MMIO load recoverable.

## Primary references

- [Pinned NVIDIA uptime functions](https://github.com/NVIDIA/open-gpu-kernel-modules/blob/1a82fbfda8f321b056eb3568850f9316c5e465c5/src/nvidia/src/libraries/nvport/time/time_unix_kernel_os.c#L63-L81) and [clock-hook ABI](https://github.com/NVIDIA/open-gpu-kernel-modules/blob/1a82fbfda8f321b056eb3568850f9316c5e465c5/src/nvidia/arch/nvalloc/unix/include/os-interface.h#L81-L83).
- [NVIDIA deadline consumer](https://github.com/NVIDIA/open-gpu-kernel-modules/blob/1a82fbfda8f321b056eb3568850f9316c5e465c5/src/nvidia/src/kernel/gpu/gpu_timeout.c#L282-L302).
- [Pinned Darwin clock declarations](https://github.com/acidanthera/MacKernelSDK/blob/3f750085caa17ec3a7880f11c11bf4f48cd6a164/Headers/kern/clock.h#L86-L115).
