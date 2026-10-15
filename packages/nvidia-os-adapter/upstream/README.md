# Pinned NVIDIA OS-adapter sources

Baseline: NVIDIA open-gpu-kernel-modules **615.78.08**, commit **1a82fbfda8f321b056eb3568850f9316c5e465c5**. The manifests record source paths, original Git blob identities and the exact changes made to adapted callers.

| Manifest | Coverage |
|---|---|
| [PROVENANCE.json](PROVENANCE.json) | Original time/ABI inputs and adapted uptime excerpt |
| [MEMORY-PROVENANCE.json](MEMORY-PROVENANCE.json) | Original memory/interface inputs, adapted RAM callers and length bridge |
| [ATOMIC-PROVENANCE.json](ATOMIC-PROVENANCE.json) | Unchanged nvport atomic-header closure, compiler selection and LLVM license |

## Time caller

`nvport_time_uptime.c` is an **adapted extraction**, not the complete upstream time module. It retains the original MIT notice and four contiguous uptime function signatures and bodies from lines 63–81. Includes and platform guards are replaced by `nvport_time_uptime.h`. The three monotonic hooks retain NVIDIA's exact types and calling convention with C linkage.

The complete original module in `reference/time_unix_kernel_os.c` also calls `os_get_system_time` through its wall-clock functions. That dependency is excluded explicitly. No fake wall-clock hook or removal of unresolved code is used to claim full-module integration.

NVIDIA's pinned [GPU timeout implementation](https://github.com/NVIDIA/open-gpu-kernel-modules/blob/1a82fbfda8f321b056eb3568850f9316c5e465c5/src/nvidia/src/kernel/gpu/gpu_timeout.c#L282-L302) consumes uptime and resolution to construct and check deadlines. Exercising this excerpt checks that narrow OS boundary, not the resource manager itself.

## Memory callers

`nvport_memory_primitives.c` adapts four contiguous functions from lines 79–156 of `reference/memory_unix_kernel_os.c`: `portMemCopy`, `portMemCopyAligned`, `portMemSet` and `portMemCmp`. Their three OS call names are replaced by private adapter bridges. This explicit change preserves 64-bit `NvLength` by splitting ordinary-RAM operations into lengths accepted by the unchanged 32-bit `os_mem_copy`, `os_mem_set` and `os_mem_cmp` ABI.

The excerpt uses the original release assertion profile; checked-build assertions and diagnostics are unsupported. Overlapping copies remain undefined under the original memory contract. Complete source, public memory declarations and release assertion definitions are retained in `reference/` for comparison, not compiled as complete modules. Allocation, user-copy, MMIO, DMA and generic memory-move/pattern helpers are excluded.

## Atomic headers

The nvport atomic headers and their required type/status/header closure are unmodified. The adapter wrapper selects the original implementation through real compiler/language conditions: GNU C11 uses C11 atomics with the pinned freestanding header; C++17 uses Clang intrinsics. Both target Intel x86_64 and NVIDIA's kernel-build interface. The wrapper checks the selected implementation explicitly.

The bundled `include/nvport/clang/stdatomic.h` carries LLVM licensing. [LLVM-LICENSE.txt](LLVM-LICENSE.txt) is pinned to `llvmorg-18.1.8`; the other included NVIDIA inputs retain their MIT notices.

## Integrity and test scope

The [combined GitHub run passed](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/actions/runs/38696607911) provenance checks for original blob identities, exact adapted caller ranges, declared ABI and the unchanged atomic-header closure. It compiled/linked the real callers and both header implementations into kernel objects, audited imports and executed native userspace harnesses. Atomic checks include semantics, four-thread contention and publication; the real memory backend also passed AddressSanitizer and UndefinedBehaviorSanitizer execution. These results distinguish native userspace execution from kernel-object compilation/linking; neither establishes kernel runtime or GPU support.

Memory checks execute small ordinary-RAM buffers and inspect the chunk plan at large length boundaries. No buffer operation larger than 4 GB is executed. These CPU-only components have no laptop installation package; a later hardware test will combine components into an integration milestone.
