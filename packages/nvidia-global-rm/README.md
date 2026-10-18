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

The [bootstrap owner](../nvidia-gsp-bootstrap/README.md) retains its context,
firmware and PM/worker objects across a future global lifecycle. Separate
original-RM and bootstrap allocation domains are being integrated and validated
so original shutdown can prove its own domain empty without freeing retained
bootstrap identities. Equal live-allocation counts are insufficient ownership
evidence. This work does not enable global entry.

The original source namespace is generated during the build. The small pinned
[source contract](upstream/adapted/SOURCE-CONTRACT.json) records its counts and
hash. Original full-RM objects cannot share v9 standalone NVOC/Resource Server
symbols or layouts. The generated namespace header is a build artifact.

## Validation and current limits

A historical seven-cleanup-overlay ELF control executed the original global lifecycle through the
new host facade and backend. Its 22 assertions covered all 15 children, the
real export client, 148 balanced host allocations/frees, zero unimplemented
service calls and complete teardown. It observed 141 simultaneous allocations,
25,372,862 peak host bytes and a 24,604,904-byte largest allocation. The test
uses explicit platform and privileged-CPU fixtures. It does **not** establish
Apple compiler execution, a kernel-stack budget, physical CPU register reads,
adapter initialization, GSP initialization or GPU operation.

The current [adaptation manifest](upstream/ADAPTATIONS.json) records **ten
approved patches**, composed into **twelve source/header files** by the
[checked integration audit](upstream/adapted/CHECKED-INTEGRATION-AUDIT.json).
The seven cleanup families below retain their historical fault evidence; the
complete expanded profile requires its own validation.

| Path | Adaptation | Development result |
| --- | --- | --- |
| Debug logging lock allocation | Balance the nested portable-runtime reference before returning failure | Fault 9 releases all allocations |
| Assertion during GPU manager construction | Refuse GPU-presence probing before the manager exists | Fault 20 returns an error and releases all allocations |
| Partial global thread-state allocation | Own the TLS reference explicitly and unwind through one idempotent cleanup path | Faults 100–105 release all allocations |
| Portable-memory tracking lock | Propagate raw-storage and backing-lock failures through a checked internal initialization ABI | Fault 1 and both lock failure modes unwind; a same-process full startup retry succeeds |
| Resource Server construction | Check acquisitions, publish construction last and release only acquired resources | Faults 124 and 128 release all allocations |
| System construction failure | Retain system, children and TLS until real Resource Server cleanup completes | Faults 144–146 release all allocations |
| RMAPI lock/TLS acquisition | Release the acquired RW lock after TLS refusal; never free a client through an unowned lock | Faults 147–148 complete genuine shutdown cleanup |
| Original registry/profile initialization | Propagate registry failure, verify policy writes/readback and preserve a preexisting unowned registry | Expanded original lifecycle/fault validation in progress |
| NVOC inherited-pointer casts | Evaluate the source once while retaining the original null guard and conversion | Expanded original plain/fatal-sanitized validation in progress |
| Typed iterator dispatch | Call the declared C iterator ABI, then assign the returned base iterator into the typed union | Expanded original plain/fatal function-sanitizer validation in progress |

The historical [combined allocation audit](upstream/adapted/COMBINED-ALLOCATION-AUDIT.json) records
the seven cleanup overlays in one original-RM development image. All **148 allocation
failure positions pass**, with zero live allocations, invalid frees or
unavailable service calls after cleanup. The normal 22-check lifecycle and the
29-check memory failure/retry control also pass. Original failure diagnostics
remain visible. These are user-space controls with explicit platform/CPU
fixtures; they do not validate the current ten-patch composition or establish
safe execution in a Darwin kernel. The complete expanded lifecycle, memory
retry and allocation-failure sweep are under plain and fatal address,
undefined-behavior and function-type sanitizer validation. A new native Intel
macOS CI run is pending; no current aggregate pass count is claimed.

The portable-memory overlay changes an
internal declaration from `void` to `NV_STATUS`: all affected callers must be
rebuilt against its checked header. The NVOC and iterator corrections likewise
require rebuilding the actual original consumers against the composed headers.
The two `system.c` patches compose into one unit. The unchanged baseline audit
does not implicitly apply these adaptations, and the exact composition audit
is not a runtime result. No device initialization is added by these fixes.

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

The [native Intel macOS development workflow](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/actions/runs/38811444683)
passed from source `ee8893d0d951b51de20ce722015e8d6bb9e0ddfa`. It compiled all
1,100 unchanged source units and their private-namespace rebuild, linked the
selected global and adapter controls as `MH_KEXT_BUNDLE` without dylib
dependencies, and passed 1,433 CPU/contract checks in each of the plain and
fatal-sanitized variants. All 24 project bridge units compiled with the audited
platform imports. Firmware files, licenses and embedded bytes were verified.
These results do not execute the adapted full-RM lifecycle or the GPU.

The subsequent [checked native build](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/actions/runs/38816440893) from `5413897` also passed its seven-overlay profile: all 1,100 units and their namespace rebuilt against the composed headers, original-header bridges used the same checked ABI, and the compiled-bridge dependency control passed. The later [native validation](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/actions/runs/39169319480) from `d81b198` compiled 25 project units and passed 1,594 CPU/contract checks per plain and fatal-sanitized variant. Both are historical snapshots, preceding the current ten-patch composition and PM/worker integration. Neither executed original RM in the kernel. Current native Intel macOS CI, kernel entry and candidate packaging remain pending or disabled.

The native dependency-control linker uses the kernel format required by the
original non-PIC objects and rejects dynamic library load commands. The
explicitly PIC cross-probe keeps its separate `MH_BUNDLE` diagnostic format;
it cannot establish a native kernel link. All diagnostic images remain unloaded.

## External ABI boundary

[EXTERNAL-CONTRACTS.json](EXTERNAL-CONTRACTS.json) records 244 exact non-crypto
external declarations retained by the selected startup/adapter/ISR root set.
The separately reviewed [crypto boundary](../nvidia-global-rm-crypto/README.md)
covers its 64 additional imports. Source inventories are not implementation or
runtime evidence. The selected root controls are not the complete coordinator
closure. The additional compiled-bridge audit derives those work-item,
private-state, event-lock, fault, timer and evidence roots from the actual
macOS objects. Its [supplemental contracts](COORDINATOR-CONTRACTS.json) pin the
two additional callback declarations without changing the selected 244-contract
inventory. The queue-flush query has a real guarded backend. DMA-remap policy now has
a checked exact-device query and original scalar bridge: only a positively
attested no-bounce mapping route is admitted. Unknown, revoked or unsupported
routes block entry rather than selecting a Boolean bypass. Hardware admission
for that policy remains unverified. The [TU117 ABI review](TU117-BOOTSTRAP-ABI.md)
and its [source inventory](upstream/adapted/TU117-BOOTSTRAP-ABI-AUDIT.json)
retain the historical callback families without treating lexical references as
runtime reachability exclusions. New diagnostics, build facts, registry/profile,
NVLink host allocation and user-copy boundaries have source-backed contracts,
including [diagnostic](DIAGNOSTICS-CONTRACTS.json) and
[profile](PROFILE-CONTRACTS.json) manifests. Unsupported RM ACPI method calls
remain unavailable operations and invalidate admission if reached.

Approximately 110 callbacks still lacked implementations in the latest review;
the count is provisional until a fresh prospective global/coordinator closure
includes the currently source-gated global roots. A successful link of a smaller
control is not closure of that enlarged runtime. Every report retains the
kernel/GSP and candidate blocks.

`generate_refusals.py` accepts an explicit set of implemented original symbol
names. It can generate only typed `NV_ERR_NOT_SUPPORTED` and `NULL` failure
bindings, preserving all caller-owned output arguments and recording every
invocation. Remaining scalar, void and data dependencies are reported as entry
blockers. It never supplies successful no-op services or guessed query values.
The successful native global lifecycle must have zero refusal calls, including
the lifetime-monotonic crypto counters.

The [persistent dispatcher](../nvidia-gsp-bootstrap/DISPATCHER.md) now owns
preparation and teardown on one stable thread. The
[Apple PM child](../nvidia-gsp-bootstrap/platform/POWER-PROVENANCE.json)
acknowledges revocation only after actual cleanup. Device temporary allocations
can retire during active IRQs while backing remains retained until drain.
These implemented, bounded components do not establish the original thread or
IRQ stack budget, executable-code lifetime, or sufficiency of the transport's
32 allocation records and 128 MiB retained-storage limit.

Complete callbacks, the enlarged closure, allocation-domain validation,
aggregate stack/capacity evidence and the original global/adapter kernel
lifecycle must all pass before entry is enabled. V9 remains the confirmed
laptop baseline. There is no v10 ZIP or new laptop test; one combined
checkpoint follows a validated integration.
