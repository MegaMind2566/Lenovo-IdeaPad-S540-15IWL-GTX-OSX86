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

Targeted allocation failures reproduced three upstream cleanup problems:

| Path | Adaptation | Development result |
| --- | --- | --- |
| Debug logging lock allocation | Balance the nested portable-runtime reference before returning failure | Fault 9 releases all allocations |
| Assertion during GPU manager construction | Refuse GPU-presence probing before the manager exists | Fault 20 returns an error and releases all allocations |
| Partial global thread-state allocation | Own the TLS reference explicitly and unwind through one idempotent cleanup path | Faults 100–105 release all allocations |

The focused patches are in [upstream/adapted](upstream/adapted). They do not
change device initialization or hardware operations. The first portable memory
tracking-lock allocation still lacks a checked upstream initialization path;
fault 1 can dereference a null lock. This is a **production-entry blocker**.
A development sweep of all 148 allocation ordinals passed 140 cases. Eight
remain failing: 1, 124, 128 and 144–148. Besides the early tracking-lock failure,
the remaining failures include Resource Server destruction and client/TLS
cleanup. The matrix has **not passed** and must not be treated as a safe kernel
lifecycle.

The separate host-allocator test passes 24 assertions in plain and fatal
ASan/UBSan builds. It covers 2,048 concurrent allocations/frees with simultaneous
snapshots and lock-free service observations, interrupt-context refusals, and
foreign/duplicate free rejection. This evidence applies to the host facade,
not to the original full-RM failure paths that remain blocked.

The native harness currently enters `coreInitializeRm` on a user-space stack.
An enabled kernel implementation must instead preserve the original
`rm_init_rm(nvidia_stack_t *)` runtime-stack contract, with correctly aligned,
separately owned stack storage and complete unwind. A 4 KiB limit on individual
compiler frames does not prove that the aggregate call chain fits a Darwin
kernel stack. No kernel readiness is inferred from the development control.

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

The facade, complete typed closure, exhaustive failure cleanup, original stack
contract and authoritative Darwin build/execution must all be ready before
kernel entry can be enabled. This module is not an installable GPU driver and
does not request another laptop test.
