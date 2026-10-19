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
- `nv_pci_read_gpu_pdi_from_dvsec` traverses the real bound provider's extended
  configuration space with the pinned NVIDIA DVSEC3 rules and 480-iteration
  limit. It distinguishes absence from malformed offsets, short capabilities,
  cycles and read errors. Only actual absence or an original invalid PDI value
  returns `NV_ERR_NOT_SUPPORTED`, permitting RM's original PCI PBI UUID fallback.
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
- Device mappings use a retained published device `IOMapper`, or a Direct route
  positively accepted by a real IOKit `kBypassed` command. Direct admission
  retains the actual published, live Platform Expert, requires no platform
  mapper-present property and no `iommu-parent` on the exact opened provider,
  creates the real probe, then repeats those observations. Every Direct DMA
  allocation also uses `kBypassed`. Raw null metadata never attests a route.
  Unknown, required, unresolved and conflicting states are refused before a
  potentially waiting factory. Admission is rechecked around preparation.
- DMA page addresses respect the original RM's requested address width. Initial
  width is 32 bits, matching the original OS device setup. A mapping must resolve
  to the original physical pages: bounce buffers are refused because continually
  shared GSP queues cannot use a one-time copy as coherent shared memory.
- Exact `s540Global_` ABI callbacks preserve allocation/PTE ownership on failure.
  Successful DMA mapping publishes a separate opaque mapping token; successful
  unmapping restores the original allocation token. Raw Linux private layouts
  are never fabricated.
- Bound-RM unmap/free operations retire each allocation separately while an IRQ
  enable attempt remains undrained or hardware DMA lacks its independent stop
  proof. Logical unmap revokes the DMA token and
  returns the allocation identity; the same backend mapping, IOVA and pages
  remain owned and cannot be recycled. Logical free revokes new CPU/DMA access.
  Existing CPU aliases retain their exact ownership until their final close.
  A remap of still-owned backing reuses its retained IOVA only after the real
  provider, mapper and no-bounce translation pass revalidation. Generic Session
  free/unmap operations retain both lifetime guards.
- `nv_get_num_phys_pages` reads the bound allocation's actual page count.
  Foreign, DMA-only, logically freed and stale allocation identities are refused
  without changing the output. `nv_get_phys_pages` remains unavailable: its
  original output is a Linux `struct page *` array, not physical addresses.
- Forty additional memory callbacks have exact original-header boundaries in
  [MEMORY-CONTRACTS.json](MEMORY-CONTRACTS.json). Four expected disabled platform
  branches and four official empty releases are recorded separately from 23
  unavailable memory operations. Nine unavailable lifetime/scalar callbacks
  terminate on a missed gate. Definitions do not implement Linux pages, SGT,
  GEM, DMA-BUF, user mappings, peer DMA or NUMA hotplug. The owner must check
  lifetime-monotonic `unavailableOperationsEver` and `lifetimeViolationsEver`
  so an ignored refusal cannot become adapter success. Production has no reset
  API; native telemetry reset cannot clear either sticky error count.
- `nv_requires_dma_remap(nv_state_t *)` has the exact original scalar ABI.
  In NVIDIA `nv.c:5412`, its result is the inverse of the device's SWIOTLB
  bounce policy, not an IOMMU-presence test. `NV_TRUE` selects physical PTEs
  followed by explicit DMA mapping. This package implements that route and
  rejects mappings which do not resolve to the original physical backing.
  `Session::requiresDmaRemap(NvBool &)` is the status-bearing admission query
  before RM state exists. `queryRmDmaRemap(nv_state_t *, NvBool &)` additionally
  requires the exact active RM binding. Both preserve output on failure.
  Darwin attests the supported policy through this opened provider's retained
  published device mapper, or the actual framework-accepted Direct route.
  Both implement explicit no-bounce DMA mapping and return `NV_TRUE`; there is
  no NVIDIA bypass-PTE implementation for `NV_FALSE`. Unknown, unresolved,
  unattested and revoked routes return a status failure, never an inferred
  Boolean. Each query repeats the real provider/platform attestation. The scalar
  callback terminates on a missed gate; it cannot return a fallback `NV_FALSE`.
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

Before any original adapter entry that can start DMA, the exact bound owner
calls `beginRmHardwareDma(&session)`. This conservatively retains the Session's
pages and mappings under a unique generation. IRQ drain cannot clear that hold.

Disable adapter hardware interrupts; drain deferred work and unregister the
controller; complete status-preserving original adapter shutdown and late GSP
unload while descriptor frees remain logical retirements. Only an opaque receipt
accepted by `confirmRmHardwareDmaStopped(&session, receipt)` can clear the matching
hardware lifetime. Then complete `drainRmRetirements(&session)`, final CPU alias
completion and Context destruction before unbinding the empty callback registry
and stopping the Session. Capture allocation/interrupt observations before
unbinding resets them. The [DMA lifetime contract](DMA-LIFETIME-CONTRACT.json)
records the strong original verifier and exact identities. The active ten-overlay
profile has no receipt issuer and remains blocked for this operational sequence.

`drainRmRetirements` performs the actual backend unmap, descriptor completion and
free only after both actual IRQ drain and accepted original hardware stop proof
for any begun lifetime. Progress is recorded per allocation;
a failed completion keeps the remaining binding and storage for a retry or
quarantine. This also covers resources released inside the original adapter
disable operation. An error from the void final CPU-unmap callback becomes a
tracked retirement owner, rather than losing the backing after a reported free.
Neither logical retirement nor `interruptArmed()==false` proves hardware DMA has
stopped. Failed initialization with a never-armed IRQ still requires the matching
positive original receipt once its DMA lifetime began.

A failed DMA completion, descriptor completion, clear, interrupt quiescence or
provider restoration preserves ownership and fails the checkpoint. Kernel
completion errors permanently quarantine the associated allocation. The caller
must retain the **session object and the actual callback context**, not only
heap backing, after failed teardown. A stack destructor is not a quarantine
owner and must not be used for a failed operational adapter session.

## Explicit remaining limits

- Direct admission supports the normal single published Platform Expert boot
  lifecycle recorded in [DIRECT-ROUTE-CONTRACT.json](DIRECT-ROUTE-CONTRACT.json).
  Pinned XNU makes its mapper-required decision before publishing the Platform
  Expert. After settled None, its remaining normal writer can only publish a
  live mapper, which `kBypassed` rejects. An atomic null read is only the guard
  against entering the sentinel wait; the accepted factory is positive proof.
  Concurrent Platform Expert restart/replacement or external mapper-policy
  writers fall outside this source argument. XNU's factory has no general
  timeout, so this is not a deadline guarantee for arbitrary boot mutations.

- Active allocations and retirements share the bounded pool of 32 ownership
  records, 8,192 pages per allocation and 128 MiB of retained backend storage.
  The 33rd outstanding allocation fails without reusing a retired resource.
  This capacity is tested, but its sufficiency for full NVIDIA initialization
  is unproved: firmware/log configuration, GPU properties and bootstrap retry
  paths change the allocation peak. The bounded retirement implementation does
  not establish complete original-RM execution or an unlimited release service.
  [CAPACITY-AUDIT.json](CAPACITY-AUDIT.json) records the source trace and exact
  pinned firmware measurement: its image radix needs 5,601 pages (22,941,696
  bytes), which fits one allocation. No global 32-record peak is established.
  `AbiStatistics` reports attempts, failures, the largest page request, peak
  registered records/bytes and the exact last failed demand/status. Capture it
  before unbinding. Retired records remain part of the peak; failed-constructor
  backend quarantines are reported as failures and are outside that registered
  storage observation.

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

The shared state-machine/ABI native harness currently passes 466 assertions and
128 complete allocation/map/unmap/cleanup cycles. It includes ownership refusal,
constructor and completion quarantine, mapper admission, bounce/address-mask
policy, CPU-map deferred free, contiguous output width, scoped PCI access and
interrupt prerequisites. Its mapped exercise has 21 checks; the explicit
unavailable-mapper refusal exercise has 19 checks. All native reports label GPU
access, kernel execution, physical interrupt delivery and GPU initialization as
unverified or false.

DMA-remap admission additionally checks the exact ABI type, real callback
delegation, missing/unknown/invalid policy, provider revocation, foreign and
stale state, context failure and output preservation. Seven subprocess checks
confirm that scalar callback violations terminate without a fabricated result.

Retirement tests exercise init-order temporary releases, releases inside the
hardware-mask callback, failed/partial enable, failed source/controller drain,
per-allocation completion failures and retry, mapper revocation, safe remapping,
CPU-alias lifetime and exact pool exhaustion. These are functional native
ownership models; they do not execute the original GPU initialization body.
Thirty-eight independent DMA-lifetime checks cover post-IRQ engine frees, final
CPU aliases, unpublished command failure, retained IOVA revalidation and matching,
foreign, failed or stale receipt authority. IRQ and hardware proofs must both
complete, in either order. The receipt authority fixture is native-only and
rejects compilation with `KERNEL` defined.

Direct-route tests cover real-factory delegation, missing/changed platform and
provider facts, refusal before a possible wait, partial probe cleanup, output
preservation, physical-identity DMA output and retained-map reactivation after
IRQ retirement. Three provenance checks verify the pinned Apple copies, boot
publication ordering, mapper writers and actual `kBypassed` rejection behavior.

The separate memory-boundary harness passes 63 checks, including nine subprocess
lifetime/scalar guards, output preservation and independent unavailable/disabled
branch counters. The PCI PDI harness passes 40 checks for actual reader delegation,
valid values, original fallback conditions, malformed data, every read failure
and bounded cycle detection. Forty new ABI comparisons use pinned original
`nv.h` and `os-interface.h`; the transport ABI check also compares the PDI type.

Local Linux execution passed plain and fatal AddressSanitizer/UndefinedBehaviorSanitizer
runs. LeakSanitizer could not run in the local container because process/task
inspection was unavailable. The earlier isolated component cross-probe matched its 32-operation SDK
reference. The earlier [native Apple build](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/actions/runs/39169319480) from `d81b198` compiled the actual transport inside all 25 execution
units and matched the complete reviewed platform-import set; the DMA-policy
violation path reuses the already reviewed panic import. That baseline's 307
checks passed with fatal sanitizers. The current transport changes pass
466 local Linux checks, plus the memory63 and PCI40 cases, including address,
undefined-behavior and function-type sanitizers. The callbacks compile against
the pinned original NVIDIA headers. The four production C++ units and the new
original-header C bridge also cross-compile to
x86_64 Darwin Mach-O with the pinned kernel SDK, warnings as errors and the
4 KiB frame bound. The backend's 32 platform imports are contained in the
33-operation independent SDK reference. Direct adds `IOService::getPlatform`;
the five production units together have 34 platform imports, including the
already reviewed `panic` outside that reference.
The independent lifetime guard also requires the strong project symbol
`s540GspContextValidateDmaStopReceipt`; production resolves it through the actual
original Context bridge, which currently refuses proof. It adds no platform API.
The [prior native Intel macOS run](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/actions/runs/39175620059), at `76e0f43`, passed the
421 transport checks in both plain and fatal address/undefined/function-sanitized
variants and compiled this transport within all 34 production bridges. The
[validation record](../nvidia-global-rm/NATIVE-INTEGRATION-VALIDATION.json) records
the reviewed import comparison separately from actual target-kernel resolution.
Physical DMA, interrupt delivery, full-adapter capacity and kernel execution
remain unproved.

Compile `src/S540NvidiaUnsupportedMemory.c` and
`tests/check_memory_callback_abi.c` with the same `original_bridge_flags` and
forced `S540GlobalRmNamespace.h` as the other original-header C bridges. Link
the resulting memory object, `S540NvidiaDeviceTransport.cpp` and
`S540NvidiaDeviceServices.cpp` into `check_memory_callbacks_native.cpp`. The PCI
harness uses the same two C++ units with `check_pci_pdi_native.cpp`. Standalone
native cases also link `tests/dma_stop_receipt_fixture.cpp`; production must link
the actual Context verifier and cannot include the fixture. These tests invoke
no GPU or original kernel initialization code.
