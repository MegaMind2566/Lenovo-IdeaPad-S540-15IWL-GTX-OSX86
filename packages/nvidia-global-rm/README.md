# Original NVIDIA global Resource Manager

This is development code for the complete original `RS_STANDALONE=0` global
Resource Manager lifecycle. It is separate from the working v9 standalone
Resource Server checkpoint. **Production kernel entry is disabled.**

## Implemented

The lifecycle wrapper calls the original `coreInitializeRm` → `OBJSYS` →
`sysConstruct` path. It requires all 15 original system children, a constructed
global Resource Server, and the actual system-memory export client handle in
that server. A child constructor returning `NV_ERR_NOT_SUPPORTED` cannot turn a
missing required child into a successful checkpoint. Shutdown uses the original
`RmShutdownRm`, including registry cleanup and portable-runtime teardown.

The host facade provides a separately tracked allocator and forwards real
synchronization, thread, process, clock, wait, work-queue, random and scheduling
services to [the Darwin services backend](../nvidia-darwin-services/README.md).
Platform facts must come from completed provider/ACPI/OS queries; unknown facts
refuse initialization. Service observations and refusal counters use lock-free
atomics, including paths called with interrupts disabled.

The allocator has 8,192 ownership records, a 256 MiB single-allocation ceiling
and a 512 MiB total ceiling. These are declared limits, not preallocated memory
or a guarantee that every request can succeed. The original global `GpuDb`
allocation alone is 24,604,904 bytes, so the small v9 reserve is not reused.
Foreign and duplicate frees are rejected and counted.

The original source namespace is generated during the build. The small pinned
[source contract](upstream/adapted/SOURCE-CONTRACT.json) records its counts and
hash. Original full-RM objects cannot share v9 standalone NVOC/Resource Server
symbols or layouts. The generated namespace header is a build artifact.

## Validation and current limits

A development ELF control executed the original global lifecycle through the
new host facade and backend. Its 22 assertions covered all 15 children, the
real export client, 148 balanced host allocations/frees, zero unimplemented
service calls and complete teardown. It observed 141 simultaneous allocations,
25,372,862 peak host bytes and a 24,604,904-byte largest allocation. The test
uses explicit platform and privileged-CPU fixtures. It does **not** establish
Apple compiler execution, a kernel-stack budget, physical CPU register reads,
adapter initialization, GSP initialization or GPU operation.

Allocation failures reproduced upstream cleanup problems addressed by seven focused overlays:

| Path | Adaptation | Development result |
| --- | --- | --- |
| Debug logging lock allocation | Balance the nested portable-runtime reference before returning failure | Fault 9 releases all allocations |
| Assertion during GPU manager construction | Refuse GPU-presence probing before the manager exists | Fault 20 returns an error and releases all allocations |
| Partial global thread-state allocation | Own the TLS reference explicitly and unwind through one idempotent cleanup path | Faults 100–105 release all allocations |
| Portable-memory tracking lock | Propagate raw-storage and backing-lock failures through a checked internal initialization ABI | Fault 1 and both lock failure modes unwind; a same-process full startup retry succeeds |
| Resource Server construction | Check acquisitions, publish construction last and release only acquired resources | Faults 124 and 128 release all allocations |
| System construction failure | Retain system, children and TLS until real Resource Server cleanup completes | Faults 144–146 release all allocations |
| RMAPI lock/TLS acquisition | Release the acquired RW lock after TLS refusal; never free a client through an unowned lock | Faults 147–148 complete genuine shutdown cleanup |

The [combined audit](upstream/adapted/COMBINED-ALLOCATION-AUDIT.json) records
all seven overlays in one original-RM development image. All **148 allocation
failure positions pass**, with zero live allocations, invalid frees or
unavailable service calls after cleanup. The normal 22-check lifecycle and the
29-check memory failure/retry control also pass. Original failure diagnostics
remain visible. These are user-space controls with explicit platform/CPU
fixtures; they do not establish safe execution in a Darwin kernel.

The five newly adapted C translation units compile as x86-64 Darwin Mach-O
with warnings treated as errors. The portable-memory overlay changes an
internal declaration from `void` to `NV_STATUS`: all affected callers must be
rebuilt against its checked header. The two `system.c` overlays are composed
into one source unit. The unchanged baseline source audit does not
implicitly apply these adaptations. No device initialization or hardware
operation is added by the cleanup corrections.

The separate host-allocator test passes 24 assertions in plain and fatal
ASan/UBSan builds. It covers 2,048 concurrent allocations/frees with simultaneous
snapshots and lock-free service observations, interrupt-context refusals, and
foreign/duplicate free rejection. This evidence applies to the host facade,
and does not substitute for the separate original-RM failure controls.

The native harness currently enters `coreInitializeRm` on a user-space stack.
Kernel entry requires a verified compiled stack policy and aggregate stack
budget. The pinned make profile does not define `__use_altstack__`; in that
profile `NV_ENTER_RM_RUNTIME` is a no-op and the original
`rm_init_rm(nvidia_stack_t *)` wrapper does not switch stacks. Passing an aligned
heap stack buffer alone cannot establish alternate-stack execution. Enabling
the conditional legacy mechanism also requires a separately reviewed compiler
and runtime contract. A 4 KiB limit on individual frames does not prove that
the aggregate call chain fits a Darwin kernel stack. No kernel readiness is
inferred from the development control.

The first native Intel macOS workflow compiled all 1,100 unchanged source
units, repeated compilation with the verified private namespace, and reached
the dependency-control link. That link failed; the original subprocess wrapper
did not surface its diagnostic. This is native source-compilation evidence,
not a passing workflow or validation of the cleanup overlays. No original RM
entry point ran in that job.

## External ABI boundary

[EXTERNAL-CONTRACTS.json](EXTERNAL-CONTRACTS.json) records 244 exact non-crypto
external declarations retained by the complete startup/adapter/ISR root set.
The separately reviewed [crypto boundary](../nvidia-global-rm-crypto/README.md)
covers its 64 additional imports. Source inventories are not implementation or
runtime evidence.

`generate_refusals.py` accepts an explicit set of implemented original symbol
names. It can generate only typed `NV_ERR_NOT_SUPPORTED` and `NULL` failure
bindings, preserving all caller-owned output arguments and recording every
invocation. Remaining scalar, void and data dependencies are reported as entry
blockers. It never supplies successful no-op services or guessed query values.
The successful native global lifecycle must have zero refusal calls, including
the lifetime-monotonic crypto counters.

The facade, complete typed closure, kernel validation of the adapted failure
cleanup, compiled stack policy and authoritative Darwin build/execution must
all be ready before
kernel entry can be enabled. This module is not an installable GPU driver and
does not request another laptop test.
