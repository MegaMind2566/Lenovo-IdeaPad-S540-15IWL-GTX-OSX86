# Pinned NVIDIA uptime caller

This directory contains the minimum NVIDIA source used by the Darwin monotonic-clock adapter. The baseline is NVIDIA open-gpu-kernel-modules **615.78.08**, commit **1a82fbfda8f321b056eb3568850f9316c5e465c5**. `PROVENANCE.json` records the original repository paths, Git blob identities, SHA256 checksums, and the adapted caller's exact source range.

## Included source

The three headers in `include/` are unmodified. They supply NVIDIA's actual `NvU64` type, CPU/platform definitions, and `NV_API_CALL` calling-convention macro. The complete original time module and OS interface header are kept in `reference/` for provenance. Those reference files are not compiled.

`nvport_time_uptime.c` is an **adapted extraction**, not the complete unmodified time module. It retains the full original MIT copyright and license notice and the four contiguous uptime function signatures and bodies from lines 63–81. Its includes and platform guards are replaced by `nvport_time_uptime.h`.

The complete original time module also calls `os_get_system_time` through its wall-clock functions. That separate interface is outside this adapter. The extraction avoids introducing a fake wall-clock implementation or discarding unresolved symbols to claim full-module integration.

`nvport_time_uptime.h` declares the three monotonic hooks using NVIDIA's exact types and calling convention. It also declares the four extracted uptime caller functions with C linkage. It does not copy the rest of NVIDIA's operating-system interface or claim to implement it.

## Actual resource-manager dependency

NVIDIA's pinned [GPU timeout implementation](https://github.com/NVIDIA/open-gpu-kernel-modules/blob/1a82fbfda8f321b056eb3568850f9316c5e465c5/src/nvidia/src/kernel/gpu/gpu_timeout.c#L282-L302) uses `portTimeGetUptimeNanoseconds` and `portTimeGetUptimeResolution` to create a deadline. Its timeout check reads the same uptime interface to detect expiry. These callers make this a real operating-system boundary required by the resource manager.

Compiling and exercising the extracted uptime caller checks this narrow software dependency. It does not initialize RM objects, execute GPU commands, or establish GSP firmware or graphics support.

## Integrity and licensing

All included NVIDIA files carry MIT license notices. The adapted source preserves the original notice. Run `python3 tests/test_nvidia_clock_provenance.py` from the repository root to verify the pinned input blobs, checksums, exact extracted function body block, and interface declarations. This check does not access GPU hardware.

The native Intel build must compile the actual caller and link all three hooks from the real Darwin backend. Test outcomes must distinguish native userspace execution, Darwin kernel compilation, and any later kernel runtime validation.
