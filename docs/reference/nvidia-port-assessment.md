# NVIDIA port assessment

Reviewed on October 15, 2026. Target: Lenovo IdeaPad S540-15IWL GTX, Intel macOS Tahoe, NVIDIA GTX 1650 Max-Q, PCI `10DE:1F91`.

**Status:** source assessment complete; a Darwin GPU driver has not been implemented or loaded. The [native read-only PCI inventory](../../packages/nvidia-pci/README.md) is implemented; the laptop returned not_visible with -wegnoegpu active and no warnings. The [separate EFI visibility experiment](../../packages/nvidia-visibility/README.md) precedes a bounded Darwin transport prototype. Intel graphics remains the operating configuration.

## Source baseline

| Input | Inspected baseline | Meaning |
|---|---|---|
| NVIDIA open GPU kernel modules | Release `615.78.08`, commit `1a82fbfda8f321b056eb3568850f9316c5e465c5` | `version.mk` confirms the version; the compatible-GPU table includes device `1F91` |
| GSP firmware and NVIDIA userspace | Corresponding `615.78.08` release required by NVIDIA | No firmware or userspace binary has been downloaded, packaged or validated for Darwin |
| Apple IOPCIFamily | Commit `4822b27a36e2de70e231ecf2bf3021384fab6ec2` | Public API reference; it does not establish binary compatibility with the laptop's installed kernel |
| Mesa NVK | Official documentation inspected on the review date | An alternative Vulkan research path; no Mesa build or source revision has been selected |
| Nouveau ABI reference | Linux `v6.6`, `include/uapi/drm/nouveau_drm.h` | Defines VM initialization, VM binding and command-execution interfaces; not a Darwin interface |

The exact laptop subsystem ID must come from the device rather than a neighbouring Lenovo entry in NVIDIA's table. Hardware inclusion in a Linux support table establishes a relevant source candidate, not macOS support.

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

The retained EFI contains `-wegnoegpu`. In the installed Lilu 1.7.2 source, the external GPU's IOService can be terminated by the disable path. The inventory therefore checks the exact boot-argument token without exposing other arguments, and falls back to the Device Tree when the active service is absent. Its effect on the observed device graph must be recorded before selecting a matching strategy. A missing node does not prove electrical power-off. Any later change needed to attach a transport prototype belongs in a separate experimental EFI with the working Intel configuration available for recovery.

The built package includes the executable, a private JSON report launcher, per-file checksums and build provenance. No developer tools are required on the laptop. Native build and enumeration are checked in Intel CI. On October 15 the laptop lookup completed successfully but found no target in either plane while -wegnoegpu was active. This result does not establish power-off or exclusivity of the cause. A staged copy of the current Samsung EFI now provides the next visibility experiment; the original Delete/Add boot-args policy is checked before preparation so normal Samsung boot restores the working arguments.

## Subsequent milestones

| Milestone | Required result |
|---|---|
| Darwin transport | Native build, defined attachment/teardown, bounded resource access and failure handling |
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
- [Mesa NVK requirements](https://docs.mesa3d.org/drivers/nvk.html) and [Nouveau project architecture](https://nouveau.freedesktop.org/).
- [Linux Nouveau ABI reference](https://github.com/torvalds/linux/blob/v6.6/include/uapi/drm/nouveau_drm.h).
- [Apple DriverKit provisioning requirements](https://developer.apple.com/help/account/provisioning-profiles/create-a-driverkit-development-provisioning-profile): DriverKit is a candidate to evaluate, not an assumed entitlement or deployment path.
- [Installed Lilu 1.7.2 device-disable path](https://github.com/acidanthera/Lilu/blob/1.7.2/Lilu/Sources/kern_devinfo.cpp).
- [Existing firmware and ACPI review](acpi-patch-review.md) and [project roadmap](../status/roadmap.md).
