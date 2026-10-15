# NVIDIA PCI and BAR0 identification prototype

This experimental IOKit service targets the S540 GTX 1650 Max-Q (`10DE:1F91`, subsystem `17AA:3806`, revision `A1`). Version **0.1.0** successfully attached to its PCI provider and reported fixed configuration reads and assigned resource descriptors on the laptop. Version **0.2.0** adds one read-only `NV_PMC_BOOT_0` identification read and awaits laptop validation.

The prototype does not initialize the GPU or provide acceleration, command submission, display output, DMA or GSP firmware support. NVIDIA's Linux resource manager has not been integrated.

## Upgrade the existing experiment

Use the complete **S540-nvidia-transport-v2.zip**, extracted into Downloads. Keep the working Samsung EFI available. Apply the upgrade only to the separate EFI on the **240 GB test boot HDD**.

1. Save the existing `EFI/OC/Kexts/S540NvidiaPCIProbe.kext` outside the EFI directory as a private backup.
2. Replace that one kext with **S540NvidiaPCIProbe.kext** from this package. The existing `Kernel → Add` entry remains valid; **no config edit is required**.
3. Boot the HDD from the firmware's one-time boot menu, then select the existing Tahoe installation.
4. Run:

   ```bash
   bash "$HOME/Downloads/S540-nvidia-transport-v2/CHECK-TRANSPORT.command"
   ```

5. Share **nvidia-transport.json** from the new **NVIDIA-TRANSPORT…** folder on the Desktop.

This is the first hardware test of the MMIO read. A single MMIO load can hang or fault the kernel, and a software timeout cannot make that load recoverable. Use the separate test EFI and retain the unchanged Samsung boot path. If the experiment fails to boot, boot from Samsung and restore the previous kext on the test HDD. Do not attempt a live unload.

No administrator command, system installation, SIP change, NVRAM reset or kernel collection rebuild is part of this procedure. The reporter requires no developer tools.

## New experimental EFI installations

If the previous probe was never added, copy the kext into `EFI/OC/Kexts/` and add the dictionary from **Kernel-Add-entry.plist** under `Kernel → Add`. This fragment is not a replacement config. It uses `Arch=x86_64`, `Enabled=true`, `MinKernel=25.0.0`, `MaxKernel=25.99.99`, `BundlePath=S540NvidiaPCIProbe.kext`, `ExecutablePath=Contents/MacOS/S540NvidiaPCIProbe` and `PlistPath=Contents/Info.plist`.

Keep `-wegnoegpu` absent and `SSDT-DGPU-OFF.aml` disabled. Preserve `-igfxblr` and the working Intel settings. Validate the configuration with the matching OpenCore validator before booting the separate test EFI.

## Read policy

The service uses a private match category and verifies the exact PCI identity from configuration space. It reads the provider's retained, already-published `IODeviceMemory` array directly. It does not call `IOPCIDevice::open()` or the resource convenience getters, which can alter provider resource or link-power state.

Before mapping, it requires an unambiguous BAR0 descriptor, the expected 16 MiB aperture, matching assigned address and resource tag, a non-prefetchable 32-bit memory BAR, memory decoding already enabled, and PCI D0. A bounded conventional capability walk establishes D0 without issuing a power transition. Framework arbitration serializes compliant ownership and termination, and an already-open provider causes refusal. Arbitration can block and does not freeze power management.

The mapping requests offset `0`, length `4`, read-only access, inhibited caching and a unique mapping. VM mappings still have page granularity. The service rechecks identity, BAR0, memory decoding and D0 immediately before exactly one aligned volatile 32-bit load. It releases the mapping immediately afterward. It performs no retries, scans, polling, register writes, PCI writes, BAR sizing, ACPI calls, resets, firmware operations, interrupt setup or DMA allocation.

The decoded architecture must be `0x16` and implementation `0x07` for TU117. Zero, all-ones and mismatching results are explicit failures. Matching these fields identifies the register response; it does not establish GPU initialization or usable VRAM.

## Report outcomes

The native Intel reporter validates the actual parent PCI device and a strict Format 2 snapshot. It opens no hardware user client and never writes registry properties.

| Status | Meaning |
| --- | --- |
| `identified` | One read returned the expected TU117 architecture and implementation fields. |
| `refused` | A prerequisite failed; zero MMIO reads were performed. The fixed reason selects the next investigation. |
| `failed` | One read completed but returned zero, all-ones or unexpected identification fields. |
| `outdated_probe` | Version 0.1.0 is still loaded; replace the kext on the EFI actually used to boot and reboot. |
| `not_attached` | The probe service was not found; the report does not establish why loading or matching failed. |
| `error` | The snapshot, provider or report could not be validated. |

Refusal is a complete diagnostic outcome. Failed reads and invalid reports return a nonzero exit status. Raw reports and resource addresses remain private. Source teardown removes the snapshot, but runtime unload has not been validated.

## Build and source references

The native Intel CI build compiles and links the kext, checks its Mach-O type and module metadata, verifies ad-hoc signatures, and runs decoder and policy tests. It does not load the experimental kext or validate the laptop's MMIO response.

The build pins [MacKernelSDK](https://github.com/acidanthera/MacKernelSDK/tree/3f750085caa17ec3a7880f11c11bf4f48cd6a164). Its unmodified module runtime includes Apple code under APSL 2.0; the archive includes the license and source location in **THIRD-PARTY-NOTICES.txt**. Project source is under the adjacent MIT license.

Register semantics and decoding are based on NVIDIA's pinned [nv_ref.h](https://github.com/NVIDIA/open-gpu-kernel-modules/blob/1a82fbfda8f321b056eb3568850f9316c5e465c5/src/common/inc/swref/published/nv_ref.h) and [nv_arch.h](https://github.com/NVIDIA/open-gpu-kernel-modules/blob/1a82fbfda8f321b056eb3568850f9316c5e465c5/src/common/inc/swref/published/nv_arch.h). Apple API behavior was reviewed against [IOPCIFamily](https://github.com/apple-oss-distributions/IOPCIFamily/tree/4822b27a36e2de70e231ecf2bf3021384fab6ec2) and [XNU](https://github.com/apple-oss-distributions/xnu/tree/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea).
