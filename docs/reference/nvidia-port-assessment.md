# NVIDIA port assessment

Reviewed on October 15, 2026. Target: Lenovo IdeaPad S540-15IWL GTX, Intel macOS Tahoe, NVIDIA GTX 1650 Max-Q, PCI `10DE:1F91`.

**Status:** PCI visibility, attachment, the two-read TU117 match and the integrated v0.7.0 sequential CPU startup are confirmed on the laptop. The [transport package](../../packages/nvidia-transport/README.md) combines foundations, original allocation/mutex callers, a bounded reserve and tracked memory/owned-object lifecycle. All 258 kernel startup checks passed, including checked support-core initialization, utilities, vector/list consumers and cleanup, with no warnings. Concurrent kernel execution, interrupt behavior and full NVIDIA caller compatibility remain unvalidated. HAL instantiation, resource-manager integration, GPU initialization, DMA, firmware loading, execution and graphics acceleration remain unimplemented. Runtime stop/unload is untested. Intel graphics remains the operating display configuration.

**V6 confirmed:** The combined [NVPort lifecycle block](../../packages/nvidia-nvport-lifecycle/README.md), source `a6f6555624b4395454045bbce710c08cf7b6309e`, passed [native Intel CI and package verification](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/actions/runs/38732985934). The format-6 laptop report confirms all 130 kernel startup checks (72 lifecycle, 35 caller/reserve, 23 foundations), cleanup complete, verified provider identity, the two-read TU117 variant-41 match and no warnings. No repeat laptop test is required. Full RM operation and GPU initialization remain unimplemented.

**V7 confirmed:** The [combined CPU support runtime](../../packages/nvidia-nvport-runtime/README.md) now links checked memory/PRNG initialization, original string/unsigned utilities and real vector/list consumers. An explicit vector reallocation correction prevents old-buffer loss for an empty container. [Native CI](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/actions/runs/38740433010) passed 258 combined startup checks, container/fault coverage, fatal sanitizers, kernel/import/signature checks and 390 reporter checks. The compiled package and embedded hashes were verified. The format-7 laptop report confirms version `0.7.0`, `integrated_passed`, all 258 kernel startup checks passed, all four CPU blocks passed, cleanup complete, verified provider identity, the same two-read TU117 variant-41 match and no warnings. This combined checkpoint is complete; no repeat laptop test is required. This is a selected CPU profile, not full NVPort/RM or GPU initialization.

## Source baseline

| Input | Inspected baseline | Meaning |
|---|---|---|
| NVIDIA open GPU kernel modules | Release `615.78.08`, commit `1a82fbfda8f321b056eb3568850f9316c5e465c5` | `version.mk` confirms the version; the compatible-GPU table includes device `1F91` |
| GSP firmware and NVIDIA userspace | Corresponding `615.78.08` release required by NVIDIA | No firmware or userspace binary has been downloaded, packaged or validated for Darwin |
| Apple IOPCIFamily | Commit `4822b27a36e2de70e231ecf2bf3021384fab6ec2` | Public API reference; it does not establish binary compatibility with the laptop's installed kernel |
| Mesa NVK | Official documentation inspected on the review date | An alternative Vulkan research path; no Mesa build or source revision has been selected |
| Nouveau ABI reference | Linux `v6.6`, `include/uapi/drm/nouveau_drm.h` | Defines VM initialization, VM binding and command-execution interfaces; not a Darwin interface |

The laptop inventory identifies subsystem `17AA:3806` and revision `A1`. Hardware inclusion in a Linux support table establishes a relevant source candidate, not macOS support.

NVIDIA separates reusable resource-manager logic in `src/` from its Linux interfaces in `kernel-open/`. Calls in `src/nvidia/arch/nvalloc/unix/src/os.c` still reach OS services for PCI access, mapping and work scheduling. Reusing the logic therefore requires implementing and checking these contracts on Darwin; changing the build target alone is insufficient.

## Concrete operating-system boundaries

All NVIDIA paths below refer to the pinned release commit.

| Boundary | Source entry points | Darwin work to assess |
|---|---|---|
| PCI lifecycle and configuration | `kernel-open/nvidia/nv-pci.c`: `nv_pci_probe`, `nv_pci_probe_body`, `nv_pci_validate_bars`; `os-pci.c`: `os_pci_*` | Device matching, attachment, removal and configuration-space semantics |
| MMIO and cache policy | `kernel-open/nvidia/os-interface.c`: `os_map_kernel_space`, `os_unmap_kernel_space` | Region ownership, mapping lifetime and cache attributes |
| DMA and memory ownership | `kernel-open/nvidia/nv-dma.c`: `nv_dma_map_alloc`, `nv_dma_map_pages` | Pinned pages, DMA addresses, IOMMU mappings, synchronization and teardown |
| Interrupts | `kernel-open/nvidia/nv.c`: `nvidia_isr`, `nvidia_isr_msix` | Interrupt delivery, deferred handling and permitted execution context |
| Scheduling and locks | `os-interface.c` and `nv-kthread-q.c` | Work queues, timers, sleepable contexts, mutexes, semaphores and shutdown ordering |
| Firmware and GSP communication | `nv.c`: `nv_get_firmware`; `src/nvidia/src/kernel/gpu/gsp/kernel_gsp.c`: `kgspSendRpc_IMPL`, `kgspRecvPoll_IMPL` | Firmware loading, version verification, RPC buffers, timeouts and failed-start cleanup |
| Application interface | `nv.c`: `nvidia_fops`; `nv-mmap.c`: `nvidia_mmap_helper` | A defined Darwin application/driver protocol, mapped-memory ownership and event delivery |
| Graphics userspace | NVIDIA requires matching userspace components; NVK has its own platform dependencies | A separate graphics implementation and integration path; a kernel attachment is not desktop acceleration |

This is an initial boundary inventory, not a claim that the remaining port is limited to these files. Linux DRM and UVM modules introduce further dependencies.

## First implementation milestone: PCI visibility

The native Intel macOS program in `packages/nvidia-pci` reads IORegistry metadata through IOKit. Match vendor/device IDs exactly and report the registry path, subsystem identity and already-published resource metadata when available. This first inventory should not claim the PCI device, open a hardware user client, map MMIO, enable bus mastering, start DMA, load firmware or invoke ACPI methods.

Acceptance criteria:

- Compile and link against the native macOS SDK.
- Identify `10DE:1F91`, or return an explicit not-visible result without changing configuration.
- Limit output to the GPU and relevant parent bridge; exclude machine identity and unrelated device data.
- Distinguish visible device metadata from confirmed hardware access or initialization.

The earlier operating EFI contained `-wegnoegpu`. In the installed Lilu 1.7.2 source, the external GPU's IOService can be terminated by the disable path. The inventory therefore checks the exact boot-argument token without exposing other arguments, and falls back to the Device Tree when the active service is absent. A missing node does not prove electrical power-off. Transport work uses a separate experimental EFI with the working Intel configuration available for recovery.

The built package includes the executable, a private JSON report launcher, per-file checksums and build provenance. No developer tools are required on the laptop. Native build and enumeration are checked in Intel CI. The first October 15 laptop report found no target while `-wegnoegpu` was active. The automatic [visibility helper](../../packages/nvidia-visibility/README.md) then stopped at its `Mounted` metadata check before creating a candidate or changing EFI/NVRAM. The argument was subsequently removed manually. The later reports agree on the following normalized result:

| Observation | Result |
|---|---|
| Inventory status | `found`, `complete=true`, no warnings |
| Disable argument | `wegnoegpu_present=false` |
| Active service | `IOPCIDevice`, `service_visible=true` |
| GPU identity | `10DE:1F91`, subsystem `17AA:3806`, revision `A1`, class `030000` |
| Topology | GPU `GFX0@0` below `RP05@1C,4` through `IOPP` |
| Parent PCI bridge | Intel `8086:9DBC`, class `060400` |

This completes the PCI visibility milestone. It establishes published identity and topology, not hardware register access, GPU initialization, electrical power state or acceleration. The reports do not audit every setting in the current EFI. Raw reports and private configurations remain outside the repository.

## Current implementation milestone: bounded PCI transport

Version 0.1.0 is limited to IOKit attachment to this exact PCI device, fixed configuration-space reads, and inspection of already-assigned resource descriptors. It defines attachment, refusal and teardown behavior without PCI configuration writes, BAR reassignment, MMIO mapping or reads, DMA, interrupts, ACPI invocation or firmware loading. That laptop attachment is confirmed; the source teardown path has not been tested through runtime stop or unload. The kernel SDK is pinned to Acidanthera commit `3f750085caa17ec3a7880f11c11bf4f48cd6a164`.

Resource inspection reads the provider's published `IODeviceMemory` array directly, with bounded type/tag checks. The convenience `getDeviceMemoryWithRegister` and `getDeviceMemoryWithIndex` calls are excluded: the inspected Apple implementation can call `setTunnelL1Enable`, which does not belong in this observational milestone.

The [native Intel build](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/actions/runs/38660491862) at commit `d782b96f1d83a88ab4db84a1d38145fc9c7de260` passed kernel compilation/linkage, module metadata and signature checks, the production report decoder and the packaged launcher. CI deliberately did not load the kext. Its live `not_attached`, `complete=true` result covers an unloaded probe and is separate from the subsequent successful laptop attachment. The distributed ZIP SHA256 is `202e9cd550eb5cc8ba15088aff5a26ddcd96dda839f2750727350e0215a86f41`.

### Confirmed laptop attachment

The October 15 report from `nvidia-transport` 0.1.0 returns `attached`, `complete=true`, `wegnoegpu_present=false` and no warnings. It identifies the probe as `S540NvidiaPCIProbe` and independently verifies its actual `IOPCIDevice` provider: `10DE:1F91`, subsystem `17AA:3806`, revision `A1`, class `030000`. This establishes successful kernel attachment, fixed PCI configuration reads and already-assigned resource metadata.

| BAR register | Assigned descriptor length |
|---|---|
| `0x10` | 16 MiB |
| `0x14` | 256 MiB |
| `0x1C` | 32 MiB |
| `0x24` | 128 bytes |

No descriptor is retained at `0x18` or `0x20`. Raw BAR type/width flags are absent from this snapshot, so the gaps are not diagnosed as missing resources. Descriptor lengths are not usable VRAM measurements or evidence of mapped register access. The probe did not change PCI command bits or enable bus mastering/DMA; observed configuration values must not be attributed to such changes. Raw reports, resource addresses and private configurations remain excluded from the repository.

## Current implementation: single-read identification, 0.2.0

Version 0.2.0 implements exactly one 32-bit read of [`NV_PMC_BOOT_0`](https://github.com/NVIDIA/open-gpu-kernel-modules/blob/1a82fbfda8f321b056eb3568850f9316c5e465c5/src/common/inc/swref/published/nv_ref.h#L102-L131), documented read-only at BAR0 offset zero. It requires the exact provider identity, matching BAR0 type/alignment/length, already-enabled memory decoding and D0 established through read-only PCI checks, or refuses without repairing configuration or power state. The read-only uncached mapping requests a four-byte subset; the VM mapping retains page granularity and is released after the single load.

The format-2 report distinguishes identification, refusal and failed read/decode, while an old loaded 0.1.0 probe is reported as outdated rather than accepted as a new result. There are no retries, polling, configuration or MMIO writes, DMA, interrupts, firmware loading or GSP initialization. A single MMIO load can still stall the kernel; this implementation provides no recoverable hardware timeout.

The delivered 0.2.0 archive comes from the [successful native Intel build](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/actions/runs/38664993966) at commit `0352cacd844890b4e1a2a3179c1f50cd8ad35b8d`; its ZIP SHA256 is `3c4102039d41bf7a87fac3d42ebc8187dce895b83df3be5cfba6735cccc83f73`.

### Confirmed single-read result: October 15, 2026

The laptop report from 0.2.0 returns `identified`, `complete=true`, `wegnoegpu_present=false` and no warnings, with the actual PCI provider identity verified. Its MMIO result records `read_count=1`, BAR0 offset zero, width 32, register value `0x167000A1`, architecture `0x16`, implementation `0x07` and reason `tu117-identified`. This establishes exactly one completed read of the expected TU117 identification register. It does not validate other registers, usable VRAM, initialization, DMA, firmware startup, execution or graphics acceleration. Runtime stop/unload remains untested; raw reports and private resource addresses remain excluded.

### Confirmed BOOT_42 and local HAL table match, 0.3.0

The pinned NVIDIA resource manager's [`_halmgrIsChipSupported`](https://github.com/NVIDIA/open-gpu-kernel-modules/blob/1a82fbfda8f321b056eb3568850f9316c5e465c5/src/nvidia/src/kernel/core/hal_mgr.c#L125-L148) consumes `NV_PMC_BOOT_42` architecture and implementation fields for HAL matching. The [register definition](https://github.com/NVIDIA/open-gpu-kernel-modules/blob/1a82fbfda8f321b056eb3568850f9316c5e465c5/src/common/inc/swref/published/nv_ref.h#L150-L172) marks BAR0 offset `0xA00` as read-only. The [generated chip table](https://github.com/NVIDIA/open-gpu-kernel-modules/blob/1a82fbfda8f321b056eb3568850f9316c5e465c5/src/nvidia/generated/g_chips2halspec_nvoc.c#L39-L43) maps architecture `0x16` and implementation `0x07` to the TU117 HAL variant.

Version 0.3.0 implements BOOT_0 followed by one guarded BOOT_42 read only after BOOT_0 identifies TU117, for at most two total register loads. Each mapping/read retains the identity, BAR0, memory-decode, D0 and provider-ownership guards. The format-3 snapshot records both outcomes and a local HAL table-match result, including NVIDIA source commit `1a82fbfda8f321b056eb3568850f9316c5e465c5`. Architecture `0x16`, implementation `0x07` and chip `0x167` must agree before the matcher selects TU117 variant index `41`; there are no scans, retries or writes.

The October 15 format-3 laptop report returns `hal_matched`, `complete=true`, `wegnoegpu_present=false` and no warnings, with the actual provider identity verified. BOOT_0 returned `0x167000A1` and BOOT_42 returned `0x167A1000`, one 32-bit load each and two total. Both decode to architecture `0x16` and implementation `0x07`; BOOT_42 chip `0x167` agrees with the pinned table match for TU117 variant index `41`. The HAL-selection result records NVIDIA source commit `1a82fbfda8f321b056eb3568850f9316c5e465c5`.

This confirms two read-only identification loads and a local table comparison. It does not instantiate a HAL object, integrate the resource manager or initialize the GPU. Firmware, DMA, command execution and acceleration remain unimplemented. Runtime stop/unload remains untested, and the individual-load kernel-stall limitation remains. No wider register or memory access is validated by this result.

The 0.3.0 [native Intel build](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/actions/runs/38666863926) passed at commit `dc21ecb52d0cde3b824d2ae692c0982d7e1cc972`, including compilation, signatures, policy/decoder checks and packaged reporter execution with the probe unloaded. Its ZIP SHA256 is `4b0c5c0634be2af65bcfd9fd01f91adb12fb7e6ef8d7fefd59027ccba51e6002`. CI did not load the kext or validate BOOT_42 on the laptop.

## Darwin OS adapter: CPU-only foundations

The [OS-adapter component](../../packages/nvidia-os-adapter/README.md) is separate from the unchanged, confirmed v0.3.0 transport. Its clock, ordinary-RAM and atomic boundaries are CPU-only. The full resource manager and HAL remain unintegrated; these components add no GPU access or initialization.

| Boundary | Implementation | Evidence |
|---|---|---|
| Monotonic clocks | Three exact OS hooks and four adapted upstream uptime callers; logical 1 ms ordinary-clock quantum and raw high-precision Darwin uptime | [Combined GitHub run passed](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/actions/runs/38696607911): provenance, kernel compile/link/import audit and native userspace clock/memory integration |
| Ordinary-RAM primitives | Exact copy/set/compare OS ABI; four adapted release-profile nvport callers preserve 64-bit lengths through bounded 32-bit hook calls | Native actual-caller/backend execution, AddressSanitizer/UndefinedBehaviorSanitizer execution and combined kernel-object checks passed |
| Atomic headers | Unmodified NVIDIA header closure; actual Clang selection of C11 atomics in GNU C11 and Clang intrinsics in C++17 | Native C/C++ semantics, four-thread contention/publication and combined kernel-object checks passed; no atomic runtime helpers |

The [source manifests](../../packages/nvidia-os-adapter/upstream/README.md) pin NVIDIA release `615.78.08` and distinguish unchanged headers from adapted time/memory excerpts. The memory excerpt is not the complete upstream module: allocation, user-copy, checked-build diagnostics and generic move helpers are excluded. Copy overlap remains undefined. The atomic header's LLVM license is retained alongside NVIDIA MIT notices.

The [combined run](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/actions/runs/38696607911) used commit `83d3ae7b2ce19215c73f8c89437257a3e7ac960c`; its verified report SHA256 is `55a669d3d0642bad93eb23fef511b447078a353e0f81e632cbd58acdd3b69fff`. Two relocatable kernel-object links each combine clock and memory with one atomic language consumer: GNU C11 or C++17. Exactly six imports remain: three Apple clock functions and `memcpy`, `memset`, `memcmp`; no atomic runtime helper is required. Native userspace harnesses exercise the real implementations. This establishes compile/link compatibility and tested userspace behavior, not kernel runtime, suspend behavior or GPU deadlines. The ordinary clock quantum is software policy, not measured hardware precision.

Large lengths are checked through chunk plans; no copy, fill or comparison over a buffer larger than 4 GiB is executed. There is no laptop installation package for these CPU-only substeps. Hardware tests will combine components into meaningful milestones; full validation follows the implementation stages. Software deadlines cannot make a stalled MMIO load recoverable.

## Confirmed integrated kernel startup, v0.4.0

The October 15, 2026 laptop report returns `integrated_passed`, `complete=true`, no warnings, and a verified PCI provider identity. All 23 startup assertions passed: timer (6), ordinary-RAM primitives (4), original C++ atomics (5), ordinary host-RAM allocation (4), and thread mutexes (4). The existing identification still completed exactly one BOOT_0 and one BOOT_42 read, selecting TU117 variant `41`.

The check runs once on a sleepable thread. It uses small buffers, a single 256-byte ordinary-RAM allocation with 16-byte alignment, and a mutex created, conditionally acquired, released and reacquired on that same thread. Resources are released before the snapshot is published. This establishes the bounded startup result in the real Tahoe kernel. It does not validate kernel contention/publication, the C11 atomic branch at kernel runtime, interrupt-safe allocation, suspend behavior, usable VRAM, HAL/RM instantiation or GPU initialization. The allocator and mutex retain their limited contracts; full NVIDIA caller compatibility must be reviewed before wider runtime binding. Raw reports and resource addresses remain private. No repeated laptop test is needed for this checkpoint.

## Original-caller integration: bounded allocation and mutex contracts

The [caller component](../../packages/nvidia-caller-integration/README.md) retains three allocation and five mutex function bodies from the pinned NVIDIA source. It is a narrow, explicitly adapted extraction, not complete NVPort or RM integration. Version 0.5.0 confirms these callers and the bounded startup sequence in the laptop kernel.

NVIDIA's nonpaged allocation/free contract excludes sleeping. Candidate hooks therefore use a 32-slot, 4 MiB preallocated reserve with a 128 KiB request ceiling and bounded lock-free bitmap operations. Initialization/shutdown require ordinary thread context and external quiescence. Requests may fail for size, exhaustion or contention. Larger RM allocations require a later design; this is not a general RM heap.

The NVPort mutex caller profile requires ordinary threads, same-owner release and no recursion. Candidate kernel acquisition registers `assert_wait(THREAD_UNINT)` under a simple-lock state guard, drops the guard before `thread_block`, and rechecks the token after waking. Conditional acquisition/release use the spin guard and wake primitive. Native pthread execution tests semantics, not kernel non-sleeping or interrupt behavior. The original mandatory acquisition assertion reaches a real fatal backend; failed acquisition cannot return unlocked. Caller-owned mutex initialization/lifetime is supported, while tracked allocator creation and other synchronization modules are excluded explicitly.

[Targeted GitHub validation passed](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/actions/runs/38722294509) from source `df3738eb8a3ab08f3f0668735a42def18c821cd3`: exact caller provenance, native reserve/caller/mutex execution, fatal sanitizer diagnostics, the original failed-acquisition assertion, and kernel compile/link/import validation. All 16 expected hook/caller/assertion symbols resolved with exactly 15 platform imports and no static initializers. The verified report SHA256 is `1e04b6838516375d7513dec6bbc4e2c67ce850f6a88c4bd8302af8c46efeb424`.

The [v0.5.0 native build passed](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/actions/runs/38726407067) from source `81c1529a31fcc1b61fa3a466442e73fef0fc3aa9`. Its shared entry point serializes the reserve lifecycle; all 35 caller/reserve checks and 23 foundation checks passed plain and with fatal sanitizer diagnostics. The combined kernel object resolved the 16 caller/hook symbols and retained 22 reviewed platform imports. These include the compiler's RAM-zeroing helper `___bzero`, explicitly exported by the pinned [XNU libkern symbol set](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/config/Libkern.exports#L666). The signed package, 272 decoder checks and contained file hashes were verified.

The subsequent format-5 laptop report returns version `0.5.0`, `integrated_passed`, `complete=true`, no warnings and verified provider identity. All 35 original-caller/reserve checks and 23 foundation checks passed in the Tahoe kernel. The same two read-only loads selected TU117 variant `41`. This completes the combined startup milestone; no repeated laptop test is required.

The startup creates no workers and does not intentionally enter the kernel wait path. The report does not validate kernel contention, interrupt-context allocation, suspend/wake, full RM semantics or graphics support. Raw reports and resource addresses remain private.

## V6 tracked-memory and owned-object lifecycle

The [lifecycle component](../../packages/nvidia-nvport-lifecycle/README.md) combines 31 memory functions and 11 synchronization functions from the pinned NVIDIA release. Forty-one bodies are unchanged. The remaining memory-bootstrap function is explicitly adapted to return checked status, unwind allocation/OS-spinlock initialization failures and publish initialized state only after success. This extraction is not the complete NVPort `core.c` or resource manager.

The block adds global/custom allocator dispatch, tracked allocation/free and original counters, allocator release, real spinlocks, allocator-owned mutex/spinlock creation and destruction, bounded exhaustion/reuse and complete cleanup. The same startup lease covers existing v5 checks and the new lifecycle sequence. Reserve slots, tracked allocations and actual OS mutex/spinlock object counts must return to their starting values. The 4 MiB fixed-slot reserve and its 128 KiB request ceiling remain; metadata consumes slots. This is not a general RM heap, VRAM or DMA allocator.

The [native Intel run passed](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/actions/runs/38732985934) from source `a6f6555624b4395454045bbce710c08cf7b6309e`. The production sequence passed 72 lifecycle, 35 caller/reserve and 23 foundation checks, plain and with fatal sanitizers. Native lifecycle coverage passed 107 fault checks and four-thread stress with 4,000 completed cycles; spinlock coverage passed 23 checks and four-thread stress with 16,000 updates, plain and sanitized. Bootstrap/owned-object failure cleanup and fatal assertion paths were checked. The reporter passed 333 decoder checks. Kernel linking resolved 51 functions and two constants with exactly 24 reviewed platform imports. Signatures, all 122 packaged files and 106 source hashes were verified. ZIP SHA256: `fa593618c4174fd505b4f284ee244f1bad109067bf53f0f81565fecdae001891`.

Those userspace backends do not validate kernel interrupt behavior or blocking waits. CI did not load the extension. The kernel startup creates no workers and does not intentionally contend a mutex. Diagnostic/callback paths that traverse tracking state while holding a spinlock are explicitly excluded from this kernel profile; the startup uses silent shutdown without an OOM callback.

The format-6 laptop report confirms version `0.6.0`, `integrated_passed` and `complete=true`. All 72 lifecycle, 35 caller/reserve and 23 foundation checks passed in the Tahoe kernel, with every component true, including cleanup. The actual PCI provider identity is verified; TU117 variant 41 matched through exactly two read-only identification loads. The report has no warnings and a null reason. This completes the bounded sequential startup checkpoint; no repeat laptop test is required. Raw reports and resource addresses remain private. The hardware policy is unchanged: no HAL/RM instantiation, GPU initialization, firmware, DMA or graphics acceleration.

## Milestone status and remaining work

| Milestone | Required result |
|---|---|
| Darwin PCI attachment | Confirmed laptop attachment, fixed configuration reads and assigned resource metadata; runtime stop/unload remains untested |
| Single-read BAR0 identification | Confirmed on the laptop in 0.2.0: exactly one BOOT_0 read with expected TU117 fields; no broader hardware operation validated |
| BOOT_42 and local HAL table match | Confirmed on the laptop in 0.3.0: two read-only identification loads and local TU117 variant-41 match. No HAL object or resource-manager integration |
| CPU-only Darwin OS foundations | Integrated v0.4.0 kernel startup check confirmed: 23 assertions across clocks, ordinary RAM, original C++ atomics, allocation and thread mutexes. No concurrent kernel or resource-manager validation |
| Original allocation/mutex caller startup | Confirmed on the laptop in v0.5.0: 35 caller/reserve checks and 23 foundation checks passed; bounded sequential startup only |
| Tracked memory and owned-object lifecycle | Confirmed on the laptop in v0.6.0: all 130 combined kernel startup checks passed, cleanup complete, two-read TU117 match retained and no warnings; bounded sequential startup only |
| CPU support runtime and RM library consumers | Confirmed on the laptop in v0.7.0: all 258 combined kernel startup checks passed, including 128 support checks, complete cleanup and no warnings; bounded sequential startup only |
| Further hardware transport | Grouped reviewed work for PCI, DMA and interrupts, with bounded access and failure handling |
| GPU and GSP startup | Matching, hashed firmware; observed initialization with timeouts and cleanup; no success inferred from PCI enumeration |
| Minimal execution | One deterministic command with a checked result and recoverable failure path |
| Graphics userspace | An explicit kernel/application ABI and a selected rendering or compute target |
| macOS integration | Separate work for Metal, desktop composition, video outputs and hybrid-GPU behaviour |

NVK supports the GTX 16xx generation in its documented Linux stack and requires Linux 6.6 or newer. Its Vulkan implementation cannot be treated as a plug-in for the NVIDIA resource manager or as a Metal implementation. The Nouveau and NVIDIA application interfaces require separate assessment before choosing a common path.

Electrical power-off remains deferred until after the driver-port attempt, as requested. The optional `_OFF` SSDT stays disabled. HDMI and USB-C video work remain paused; this assessment does not resolve their physical GPU routing.

## Primary sources

- [Pinned NVIDIA source and compatible-GPU table](https://github.com/NVIDIA/open-gpu-kernel-modules/tree/1a82fbfda8f321b056eb3568850f9316c5e465c5).
- [NVIDIA OS interface contract](https://github.com/NVIDIA/open-gpu-kernel-modules/blob/1a82fbfda8f321b056eb3568850f9316c5e465c5/src/nvidia/arch/nvalloc/unix/include/os-interface.h).
- [Apple IOPCIDevice public header](https://github.com/apple-oss-distributions/IOPCIFamily/blob/4822b27a36e2de70e231ecf2bf3021384fab6ec2/IOKit/pci/IOPCIDevice.h).
- [Apple resource-accessor implementation](https://github.com/apple-oss-distributions/IOPCIFamily/blob/4822b27a36e2de70e231ecf2bf3021384fab6ec2/IOPCIDevice.cpp) and [pinned MacKernelSDK](https://github.com/acidanthera/MacKernelSDK/tree/3f750085caa17ec3a7880f11c11bf4f48cd6a164).
- [Mesa NVK requirements](https://docs.mesa3d.org/drivers/nvk.html) and [Nouveau project architecture](https://nouveau.freedesktop.org/).
- [Linux Nouveau ABI reference](https://github.com/torvalds/linux/blob/v6.6/include/uapi/drm/nouveau_drm.h).
- [Apple DriverKit provisioning requirements](https://developer.apple.com/help/account/provisioning-profiles/create-a-driverkit-development-provisioning-profile): DriverKit is a candidate to evaluate, not an assumed entitlement or deployment path.
- [Installed Lilu 1.7.2 device-disable path](https://github.com/acidanthera/Lilu/blob/1.7.2/Lilu/Sources/kern_devinfo.cpp).
- [Existing firmware and ACPI review](acpi-patch-review.md) and [project roadmap](../status/roadmap.md).
