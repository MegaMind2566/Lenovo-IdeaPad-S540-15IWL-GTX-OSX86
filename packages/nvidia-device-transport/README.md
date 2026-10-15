# Darwin NVIDIA device transport

Development transport for the pinned NVIDIA 615.78.08 Resource Manager and the
Lenovo S540 TU117 (`10de:1f91`, revision `a1`, subsystem `17aa:3806`). This package
provides real Darwin resource ownership and link-isolated OS callbacks. It is
not an initialized GPU driver or a replacement for the released v9 package.

## Implemented boundaries

- `Session` retains and opens the exact PCI provider, confirms D0 and existing
  memory decoding, and retains an uncached BAR0 mapping. It exposes a PCI handle
  before an RM `nv_state_t` exists, removing the context-construction cycle.
- Configuration reads support aligned byte, word and dword accesses throughout
  the 4 KiB configuration space. Lookup needs the actual provider BDF and an
  independently verified PCI segment; no registry `domain-id` guess is used.
- Configuration writes admit only a command byte/word bus-master change and
  the exact original `osInitMapping` ROM-disable and latency-setup requests.
  The previous values are restored after RM teardown. BAR relocation, general
  vendor controls, MSI/MSI-X programming and power-state writes remain refused.
- Register views are bounded subranges of the retained BAR0 aperture. The RM
  may keep these views through its original shutdown and register teardown.
  The finite transport exercise performs no additional GPU register loads,
  preserving the older probe's two identification reads.
- Owned wired host pages support cached, uncached and write-combined storage,
  physical contiguity when requested, bounded CPU mappings and deferred free
  until the last CPU mapping closes. Limits are 8,192 pages per allocation,
  32 allocations and 128 MiB of total Darwin-owned page storage.
- Device mappings use a retained published device `IOMapper`, or an explicit
  direct command only when the provider has no `iommu-parent` property and
  the atomically observed system mapper is null. The latter is XNU's settled
  no-system-mapper state. Unknown, required, unresolved and conflicting mapper
  states are refused without waiting. Admission is rechecked around preparation.
- DMA page addresses respect the original RM's requested address width. Initial
  width is 32 bits, matching the original OS device setup. A mapping must resolve
  to the original physical pages: bounce buffers are refused because continually
  shared GSP queues cannot use a one-time copy as coherent shared memory.
- Exact `s540Global_` ABI callbacks preserve allocation/PTE ownership on failure.
  Successful DMA mapping publishes a separate opaque mapping token; successful
  unmapping restores the original allocation token. Raw Linux private layouts
  are never fabricated.
- Interrupt installation requires actual RM top-half/fault, locked and unlocked
  bottom-half, hardware-mask and dispatch-readiness callbacks. Public IOKit
  controller registration initially leaves the vector disabled. Controller
  enable is gated on real private RM state readiness. Deferred work uses a
  single `THREAD_CALL_OPTIONS_ONCE` call, with serialized bottom halves and
  bounded cancellation/drain. Controller callbacks and actual RM-handled
  callbacks are recorded separately; registration does not prove delivery.
  Provider interrupt type and actual MSI/MSI-X enable observations are separate
  facts; a message-signaled type alone does not identify MSI versus MSI-X.

## Lifetime and teardown

All public owner/binding APIs run on an externally serialized ordinary thread.
The hard ISR only uses its preallocated context, spin lock, atomics and thread
call. The owner must keep the actual RM state, alternate stacks, transport
session, firmware bytes and power resources alive throughout initialization and
shutdown. Provider opening alone is not a dynamic platform power hold.

Use the original NVIDIA ordering: disable the adapter and its hardware
interrupts; drain deferred work and unregister the controller; run original
adapter shutdown, DMA teardown and register teardown; unbind the empty RM
callback registry; finally stop the session and release the provider/power
resources. `Session::stop()` refuses while its RM binding is still active.
Read interrupt statistics before stopping the session.

A failed DMA completion, descriptor completion, clear, interrupt quiescence or
provider restoration preserves ownership and fails the checkpoint. Kernel
completion errors permanently quarantine the associated allocation. The caller
must retain the **session object and the actual callback context**, not only
heap backing, after failed teardown. A stack destructor is not a quarantine
owner and must not be used for a failed operational adapter session.

## Explicit remaining limits

- Complete global RM and real `rm_init_adapter` integration must pass before
  any package is offered for a GPU boot attempt. Native models and Mach-O
  compilation are not kernel execution or device-transfer evidence.
- Dynamic ACPI/D3 transitions, platform power ownership and immutable kernel
  firmware delivery belong to the bootstrap coordinator and its platform/broker
  components. The old placeholder `deliverFirmware` and `transitionPower`
  methods explicitly refuse; they never report successful no-ops.
- There is no userspace NVIDIA client or rendering API. The original file-based
  authorization callbacks therefore deny access, independently of PCI liveness.
- Read-only device mappings, imported/user pages, large OS pages, cache policies
  other than NVIDIA 0/1/2, peer/MMIO DMA and unresolved provider mapper identifiers
  are not implemented. Kernel virtual-to-physical lookup is restricted to this
  package's tracked allocations.
- The independent SDK import reference covers only this package. The full RM,
  its additional platform APIs and the final linked kext require their own
  compilation, closure, lifetime and runtime checks.

## Validation

The shared state-machine/ABI native harness currently passes 242 assertions and
128 complete allocation/map/unmap/cleanup cycles. It includes ownership refusal,
constructor and completion quarantine, mapper admission, bounce/address-mask
policy, CPU-map deferred free, contiguous output width, scoped PCI access and
interrupt prerequisites. Its mapped exercise has 21 checks; the explicit
unavailable-mapper refusal exercise has 19 checks. All native reports label GPU
access, kernel execution, physical interrupt delivery and GPU initialization as
unverified or false.

Local Linux execution passed plain and fatal AddressSanitizer/UndefinedBehaviorSanitizer
runs. LeakSanitizer could not run in the local container because process/task
inspection was unavailable. The four production C++ files and independent SDK
reference cross-compile to x86_64 Mach-O with the 4 KiB kernel frame bound and
warnings treated as errors. Their 32 SDK imports match exactly. Native Apple
compiler/linker validation and physical adapter execution remain separate gates.
