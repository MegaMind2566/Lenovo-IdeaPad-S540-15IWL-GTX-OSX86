# NVIDIA port assessment

Reviewed on October 15, 2026. Target: Lenovo IdeaPad S540-15IWL GTX, Intel macOS Tahoe, NVIDIA GTX 1650 Max-Q, PCI `10DE:1F91`.

**Status:** PCI visibility, 0.1.0 attachment/configuration/resource reads, 0.2.0 BOOT_0 identification and the [transport prototype](../../packages/nvidia-transport/README.md) 0.3.0 two-read/local HAL table match are confirmed on the laptop. The CPU-only Darwin clock adapter is implemented; its GitHub validation is pending. HAL instantiation, resource-manager integration, GPU initialization, DMA, firmware loading, execution and graphics acceleration remain unimplemented. Runtime stop/unload is untested. Intel graphics remains the operating display configuration.

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

## Darwin OS adapter: CPU-only clock component

The [OS-adapter component](../../packages/nvidia-os-adapter/README.md) is separate from the unchanged, confirmed v0.3.0 transport. It implements CPU-only monotonic-clock hooks for an adapted NVIDIA uptime caller. The full resource manager and HAL remain unintegrated; this component adds no GPU reads, writes or initialization.

The implemented clock hooks are `os_get_monotonic_time_ns`, `os_get_monotonic_time_ns_hr` and `os_get_monotonic_tick_resolution_ns`. NVIDIA's actual [nvport time caller](https://github.com/NVIDIA/open-gpu-kernel-modules/blob/1a82fbfda8f321b056eb3568850f9316c5e465c5/src/nvidia/src/libraries/nvport/time/time_unix_kernel_os.c#L68-L80) consumes these hooks, and its [GPU timeout code](https://github.com/NVIDIA/open-gpu-kernel-modules/blob/1a82fbfda8f321b056eb3568850f9316c5e465c5/src/nvidia/src/kernel/gpu/gpu_timeout.c#L282-L302) uses uptime and resolution to form deadlines. The pinned Darwin [clock header](https://github.com/acidanthera/MacKernelSDK/blob/3f750085caa17ec3a7880f11c11bf4f48cd6a164/Headers/kern/clock.h#L86-L115) provides `clock_get_uptime`, `absolutetime_to_nanoseconds` and `clock_timebase_info` for the kernel backend; the native userspace harness uses `mach_absolute_time` and its timebase.

The source adapts four contiguous upstream uptime functions with their signatures and bodies unchanged, while narrowing includes and build guards. Three NVIDIA ABI headers are retained unchanged with pinned provenance and MIT notices. This is an adapted excerpt, not the complete upstream time module. The ordinary clock is rounded down to a logical 1 ms quantum and reports `1,000,000` ns resolution; the high-precision hook returns raw Darwin uptime in nanoseconds. The quantum is a software policy, not measured hardware precision.

GitHub validation is pending: compile the caller and kernel backend, produce a relocatable link with an import audit, and execute a native userspace harness plus targeted clock checks. These checks will cover source/ABI compatibility and userspace clock behavior, not kernel runtime, suspend behavior or GPU deadlines. This component has no laptop installation package. Future laptop tests will combine components into meaningful integration milestones. Software deadlines cannot make a stalled MMIO load recoverable.

## Milestone status and remaining work

| Milestone | Required result |
|---|---|
| Darwin PCI attachment | Confirmed laptop attachment, fixed configuration reads and assigned resource metadata; runtime stop/unload remains untested |
| Single-read BAR0 identification | Confirmed on the laptop in 0.2.0: exactly one BOOT_0 read with expected TU117 fields; no broader hardware operation validated |
| BOOT_42 and local HAL table match | Confirmed on the laptop in 0.3.0: two read-only identification loads and local TU117 variant-41 match. No HAL object or resource-manager integration |
| CPU-only Darwin clock adapter | Implemented with adapted upstream uptime caller; GitHub validation pending. No kernel runtime validation or resource-manager integration |
| Further hardware transport | Separate reviewed work for DMA and interrupts, with bounded access and failure handling |
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
