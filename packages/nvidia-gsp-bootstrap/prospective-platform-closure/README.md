# Selected platform callback closure

Seven original-ABI callbacks provide actual identity and utility support:

- Open RM identity follows the official x86-64 branch.
- Runtime-PM availability follows the official disabled capability branch.
- The non-Tegra platform query returns `NV_ERR_NOT_SUPPORTED` without changing its output.
- NVLink string functions retain their original pointer, `NvLength` and unsigned comparison semantics.
- NVLink time uses the existing monotonic nanosecond provider.

The source requires `S540_NVIDIA_DARWIN_PLATFORM_CLOSURE=1`. An enabled runtime-PM or Tegra platform configuration fails compilation. Invalid Open RM output records an unavailable call; the other supported operations never clear that observation.

`check_platform_closure.py --upstream PATH --namespace PATH --output PATH` verifies the pinned declarations, three official bodies and three actual RM callers, runs ordinary and sanitized controls, and compiles the exact seven-symbol Mach-O object. Add `--host-control` only for explicit non-Apple development controls.

These callbacks do not implement runtime power, Tegra, NVLink hardware, NVSwitch, DMA or GPU initialization. They do not change the production default or authorize kernel entry.
