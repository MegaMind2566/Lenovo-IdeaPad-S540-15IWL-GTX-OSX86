# Original GSP and adapter bootstrap integration

Development sources for the combined global RM, device transport and GSP
initialization milestone on the S540 TU117 (`10DE:1F91`, `17AA:3806`). The
target is a completed original `rm_init_adapter` with a decoded GSP response,
followed by controlled shutdown. The first GPU command is a later milestone.

**This component is not enabled in the distributed EFI or v9 extension. No
v10 installation package is available from this development work.** Native
macOS validation and the complete operational OS callback profile remain
requirements, alongside correct global RM allocation-failure cleanup.

## Implemented components

| Component | Behavior |
|---|---|
| Firmware store | Verifies the actual approved firmware bytes, container and microcode directory; exposes bounded, generation-tagged leases to the exact original firmware ABI |
| Original adapter context | Uses the pinned `nv_state_t`, independent aligned original RM stacks, real work queues, event locks and original adapter lifecycle calls |
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
   lease. Retain the actual PCI provider, power reference and device session.
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
   remain available. Stop timer producers and drain interrupt callbacks before
   original adapter shutdown. Release original users before unbinding their
   firmware, DMA, ACPI and timer resources.
7. Stop work queues, release private/event state, shut down global RM and
   verify every ownership registry. A failed drain retains the context and its
   resources; it does not free potentially addressable storage.

`S540NvidiaGspContext` is a typed integration component, not an independently
complete driver entry point. Its caller must enforce these prerequisites,
validate the full callback closure and retain failed cleanup owners. A failed
create can return a quarantined owner for that purpose. An original adapter
initialization failure uses the original initialization unwind; it does not
pretend that a never-initialized device completed normal shutdown.

## Validation and remaining gates

The firmware-store native harness uses the actual approved pair and covers
corruption, owner/thread mismatches, unchanged outputs, lease exhaustion,
stale handles and shutdown refusal. Fatal sanitizers are required. Typed C
bridges are compiled against the pinned original headers for x86-64 Darwin;
platform, timers and transport have separate CPU/resource tests.

The complete original RM compiles in the local Darwin cross-target audit.
That is compilation evidence, not execution in the Tahoe kernel. A private
native development control constructs and destroys the real global RM with
explicit platform and privileged-CPU fixtures. Its allocation-failure tests
exposed original cleanup defects that must be resolved before enabling kernel
entry. Scalar or void OS callbacks cannot be filled with fabricated successful
defaults to make the adapter link.

The development workflow emits validation records only. It cannot create an
installable candidate or change the working EFI. Actual GSP execution,
device DMA completion, interrupt delivery and the first GPU job remain
unconfirmed. One combined laptop checkpoint will follow a complete compiled
and validated integration; the existing v9 checkpoint requires no repeat.
