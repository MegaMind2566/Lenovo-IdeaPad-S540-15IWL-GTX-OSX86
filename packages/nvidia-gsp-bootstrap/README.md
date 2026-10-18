# Original GSP and adapter bootstrap integration

Development sources for the combined global RM, device transport and GSP
initialization milestone on the S540 TU117 (`10DE:1F91`, `17AA:3806`). The
target is a completed original `rm_init_adapter` with a decoded GSP response,
followed by controlled shutdown. The first GPU command is a later milestone.

**This component is not enabled in the distributed EFI or v9 extension. No
v10 installation package is available from this development work.** Native
macOS CPU/compilation validation has passed. Complete operational callback
coverage, target-kernel resolution, a usable original kernel stack boundary,
sufficient full-adapter allocation capacity and the original-entry PM deadline
remain requirements.

## Implemented components

| Component | Behavior |
|---|---|
| [Bootstrap owner](src/S540NvidiaGspBootstrap.hpp) | Prepares and owns the real context, transport, copied firmware and timer bindings; cleanup failure preserves the heap owner for retry; initialization remains explicitly gated |
| [Persistent dispatcher](src/S540NvidiaGspDispatcher.hpp) | Creates a stable kernel thread, serializes every RM operation and accepts preallocated asynchronous power-revocation work; successful stop drains accepted commands and joins owner storage |
| [Power-domain lease](platform/S540NvidiaGspPower.hpp) | Registers a private real PM child below the exact endpoint, waits for its completed on transition and acknowledges revocation only after the owner has actually drained resources |
| Firmware store | Verifies the actual approved firmware bytes, container and microcode directory; exposes bounded, generation-tagged leases to the exact original firmware ABI |
| Original adapter context | Uses the pinned `nv_state_t`, independent aligned original RM stacks, real work queues, event locks and original adapter lifecycle calls; binds exact screen and stream-ID metadata callbacks |
| [Platform and ACPI](platform/README.md) | Collects explicit known platform facts, binds the published endpoint ACPI companion and implements bounded optional `_ROM` reads |
| [Timers](timers/README.md) | Dispatches the original recovery and nano-timer callbacks through separately owned original stacks and synchronously drains them |
| [GSP evidence](evidence/README.md) | Observes the original persistent success marker under original API and GPU locks, alongside complete adapter-state conditions |

The original source revision is
`NVIDIA/open-gpu-kernel-modules@1a82fbfda8f321b056eb3568850f9316c5e465c5`,
release `615.78.08`. Original-header C units receive the generated full-RM
namespace. They must not share globals or object layouts with the older
`RS_STANDALONE` runtime.

## Firmware identity and lifetime

The build embeds the unchanged approved `gsp_tu10x.bin` and
`ucodes_tu10x.bin` in aligned read-only Mach-O sections. It verifies both the
input files and emitted section bytes. The runtime store independently hashes
and parses those resident bytes before making them available to original RM.
The complete NVIDIA driver agreement accompanies any future distribution.

The exact original stack buffers are owned independently, but their presence
does not prove a CPU stack switch. The pinned profile leaves
`__use_altstack__` undefined; compiled runtime stack behavior and aggregate
kernel stack use remain a separate admission requirement.

TU117 selects original firmware family **TU11X**, enumeration value `2`.
The original filename selector maps that family to these `tu10x` filenames.
The store supports original GSP type `0` and UCODES type `2`; firmware-log
decoding is disabled in this initial profile.

Images remain immutable and resident throughout adapter use. Every successful
request receives a unique opaque handle. Wrong owners, threads, types and
families are refused without changing caller outputs. Outstanding leases
prevent shutdown; stale and duplicate releases are recorded. Delivery flags
mean only that original RM received bytes. They never mean the GPU booted.

## Runtime ordering required before enabling a candidate

1. Finish the older standalone checks and acquire the single outer startup
   lease. Start the persistent owner thread, establish the exact power-child
   connection and wait for its on completion. Retain the PCI/device owners.
2. Collect platform and device facts, initialize tracked host allocation,
   construct the exact original context and bind its transport identities.
3. Initialize and validate the actual global RM, then original per-device
   private state. Bind immutable firmware delivery, timers and real callbacks.
4. Register the IOKit interrupt controller in its source-defined disabled
   state. Arm it only after the original dispatch context and stacks are
   ready; record the actual interrupt mode selected by the framework.
5. Call original `rm_init_adapter`. On success, observe both
   `gspRmInitialized` and the completed original adapter state. A firmware
   request, submitted bootstrap or expired timeout cannot satisfy this step.
6. Disable the original adapter while interrupts, queues, MMIO, DMA and power
   remain available. Drain interrupt callbacks and retired temporary allocations before
   original adapter shutdown. Release original users before unbinding their
   firmware, DMA, ACPI and timer resources.
7. Stop work queues and release original private/event state through
   `s540GspContextReleaseOriginalState`, retaining the original `nv_state`,
   metadata and global-queue binding. The registered operational detacher then
   unbinds timers, firmware, device transport and platform state. Retired
   allocations must also finish their real backend unmap/release before device
   unbinding. Final destroy
   verifies that the actual timer service is detached before freeing storage.
   Shut down global RM and verify every ownership registry. A failed drain or
   detach retains the context and resources; retry never frees addressable
   storage or invokes an original destructor twice.
8. Stop the transport, release copied host owners and close the host context.
   Only after these operations succeed may a pending PM down request be
   acknowledged. Require every external revocation hook to return before
   closing the PM service, then close the persistent worker. Failed cleanup
   retains the power lease and worker for retry and submits no false power
   acknowledgement.

`S540NvidiaGspContext` is a typed integration component, not an independently
complete driver entry point. Its caller must enforce these prerequisites,
validate the full callback closure and retain failed cleanup owners. A failed
create can return a quarantined owner for that purpose. An original adapter
initialization failure uses the original initialization unwind; it does not
pretend that a never-initialized device completed normal shutdown.

## Validation and remaining gates


The preparation owner copies bounded OS fact strings and both approved firmware
images into its own lifetime before publishing them to borrowers. Every RM,
transport, firmware and timer operation runs on the same persistent worker,
including shutdown requested by the separate PM callback thread. Snapshots are
published under a guard. A successful
`prepare()` means resources/bindings are prepared, never an initialized GPU.
`initialize()` has no caller-supplied readiness Boolean and refuses before
original RM while complete ABI closure, original aggregate stack policy,
full-adapter allocation capacity and the original-entry power deadline remain
unresolved. Actual completed PM-child and revocation observations are reported
separately; they do not clear the `PowerLifetime` gate.

The original GSP paths can unmap/free temporary buffers while interrupts are
active. The transport now removes their caller visibility while retaining their
device mappings and host backing until successful interrupt quiescence and real
retirement drain. Callback tests cover partial enable, original-order disable,
backend failure and retry. The bounded allocation registry has not yet been
shown sufficient for the complete original adapter; successful fixture
retirement is not evidence of that capacity.

The power lease does not substitute a D0 sample for a lifetime request. It uses
Apple's PM child protocol, completed transition, delayed acknowledgement and
an independent external-hook lifetime count. Apple's bounded `PMstop` wait is
not proof that the revocation owner can be freed. The original FWSEC/Booter
waits can allow at least 60 seconds during initialization, exceeding the lease's
30-second acknowledgement budget. Queued cleanup cannot interrupt an original
entry already running on that worker. Normal sleep can therefore expire the
budget, independently of emergency power loss. On the pinned macOS source,
ordinary drivers' `kIOPMPreventIdleSleep` state-table flags are ignored. The
[deadline audit](platform/POWER-DEADLINE-AUDIT.md) records the required
cooperative cancellation and bounded unwind proof before original entry can
be admitted. Native PM events verify owner/acknowledgement ordering; they do
not establish an acquired power domain on the Lenovo.

The firmware-store native harness uses the actual approved pair and covers
corruption, owner/thread mismatches, unchanged outputs, lease exhaustion,
stale handles and shutdown refusal. Fatal sanitizers are required. Typed C
bridges are compiled against the pinned original headers for x86-64 Darwin;
platform, timers and transport have separate CPU/resource tests.

The context metadata harness exercises the exact original callback declarations
with explicit provider facts. It uses the real tracked host allocator and Darwin
service objects, verifies four refusal cases and complete normal cleanup, and
traps any unexpected original RM callback. The screen callback returns the
original non-console values only after a complete console-ownership query
proves an Intel console and excludes the bound NVIDIA endpoint. The stream-ID
callback copies the initialized original `nv_state_t` fields. Unknown owners or
missing outputs preserve caller values and invalidate admission. This harness
does not execute original adapter initialization or access the GPU.

The complete ten-patch original profile passes native Intel macOS development
controls: 134 checks across the real original global lifecycle, memory retry,
registry, allocation domains and ABI controls, plus all 156 allocation-failure positions in
each plain/fatal-sanitized variant. Each variant rebuilt the 1,100-unit RM profile: 1,098 original units,
one generated identification unit and one explicit privileged-CPU replacement,
with platform fixtures. The historical seven-overlay
148-position evidence remains separate. See the [validation record](../nvidia-global-rm/NATIVE-INTEGRATION-VALIDATION.json);
original kernel/GSP execution and operational runtime integration remain unproved.
Scalar or void OS callbacks cannot be filled with fabricated successful
defaults to make the adapter link.

The lifecycle harness uses real context, allocator, work queues and timers,
with typed original callback fixtures. Its 26 checks include successful timer
execution, private-state cleanup with metadata still available, detach refusal,
retry and rejection of a detacher that reports success while timers remain
bound. Two subprocesses also prove that genuine lifetime crypto refusals block
a later context and invalidate an apparent original adapter success even when
host counters remain clean. Both crypto masks, the lifetime call count and
overflow must stay zero; a zero delta is insufficient. The bootstrap-owner harness uses those real components, the Session and
Store, actual approved firmware bytes and explicit platform observations.

| Current native CPU control | Checks | Evidence |
|---|---:|---|
| Bootstrap owner | 83 | Stable worker ownership, initialization refusal, copied firmware and OS-text lifetime, retained cleanup owners, PM revocation, in-flight hook retention, failed acknowledgement and retry |
| Power callback protocol | 15 | Request versus completed transition, monotonic revocation, failed post and separate acknowledgement; explicit native PM events |
| Persistent dispatcher | 53 | Stable thread identity, synchronous commands, accepted asynchronous work, bounded queue, startup failure and drained shutdown |

These controls passed plain and fatal address, undefined-behavior and
function-type sanitizers in the [current native Intel macOS run](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/actions/runs/39175620059),
as part of 2,008 component checks per variant. All 34 production bridges and the
complete linked metaclass reference comparison passed. Native PM event fixtures
do not test Apple power-domain execution on the laptop.
The older 43-check bootstrap version and the 24-check context lifecycle passed
the [native Intel macOS build](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/actions/runs/39169319480)
from `d81b198`. That historical snapshot also compiled 25 production units with
matched SDK imports and passed 1,594 combined CPU/contract checks per variant;
it predates the current dispatcher and PM lease. Current native development
results are recorded separately in the [validation record](../nvidia-global-rm/NATIVE-INTEGRATION-VALIDATION.json).
Original kernel/GSP execution remains unconfirmed.

The development workflow emits validation records only. It cannot create an
installable candidate or change the working EFI. Actual GSP execution,
device DMA completion, interrupt delivery and the first GPU job remain
unconfirmed. One combined laptop checkpoint will follow a complete compiled
and validated integration; the existing v9 checkpoint requires no repeat.
