# NVIDIA PCI and HAL identification prototype

This experimental IOKit service targets the S540 GTX 1650 Max-Q (`10DE:1F91`, subsystem `17AA:3806`, revision `A1`). Version **0.1.0** PCI attachment and version **0.2.0** single-read `NV_PMC_BOOT_0` identification are confirmed on the laptop. The v0.2 report returned `0x167000A1`, architecture `0x16`, implementation `0x07`, and no warnings.

Version **0.3.0** adds one conditional `NV_PMC_BOOT_42` read and a local match against NVIDIA's pinned TU117 HAL-selection table. Its laptop result is pending. Built archives include native-check provenance in BUILD.json. A table match does not instantiate NVIDIA's HAL or integrate the Linux resource manager. GPU initialization, firmware, DMA, command submission, display output and acceleration remain unimplemented.

## Upgrade the existing experiment

Extract the complete **S540-nvidia-transport-v3.zip** into Downloads. Keep the working Samsung EFI available. Apply the upgrade only to the separate EFI on the **240 GB test boot HDD**.

1. Save the existing `EFI/OC/Kexts/S540NvidiaPCIProbe.kext` outside the EFI directory as a private backup of the working v0.2.0 probe.
2. Replace that one kext with **S540NvidiaPCIProbe.kext** from this package. The existing `Kernel → Add` entry remains valid; **no config edit is required**.
3. Boot the HDD from the firmware's one-time boot menu, then select the existing Tahoe installation.
4. Run:

   ```bash
   bash "$HOME/Downloads/S540-nvidia-transport-v3/CHECK-TRANSPORT.command"
   ```

5. Share **nvidia-transport.json** from the new **NVIDIA-TRANSPORT…** folder on the Desktop.

This extends the experimental hardware read to a second documented register. An MMIO load can hang or fault the kernel; software cannot provide a recoverable timeout for that load. Use the separate test EFI. If boot fails, boot from Samsung and restore the previous kext on the HDD. Runtime unload is untested; use a reboot for rollback.

The package requires no administrator command, system installation, SIP change, NVRAM reset or kernel collection rebuild. The reporter requires no developer tools.

## New experimental EFI installations

If no previous probe was added, copy the kext into `EFI/OC/Kexts/` and add the dictionary from **Kernel-Add-entry.plist** under `Kernel → Add`. This fragment is not a replacement config. It uses `Arch=x86_64`, `Enabled=true`, `MinKernel=25.0.0`, `MaxKernel=25.99.99`, `BundlePath=S540NvidiaPCIProbe.kext`, `ExecutablePath=Contents/MacOS/S540NvidiaPCIProbe` and `PlistPath=Contents/Info.plist`.

Keep `-wegnoegpu` absent and `SSDT-DGPU-OFF.aml` disabled. Preserve `-igfxblr` and the working Intel settings. Validate the configuration with the matching OpenCore validator before booting the separate test EFI.

## Read and selection policy

The private service category and exact PCI configuration identity gate attachment. The probe retains the already-published `IODeviceMemory` resources directly, without opening the provider or calling resource convenience getters that can change link or resource state.

The prerequisites require an unambiguous matching BAR0 descriptor, the expected 16 MiB aperture, matching address/tag, a non-prefetchable 32-bit memory BAR, memory decoding already enabled and PCI D0. A bounded conventional capability walk establishes D0 without a power transition. Provider arbitration serializes compliant ownership and termination; an already-open provider causes refusal. The arbitration lock can block and does not freeze power management.

The prototype first requests a unique read-only, cache-inhibited four-byte mapping at BAR0 offset zero and reads BOOT_0 once. Only if BOOT_0 identifies the exact TU117 target does it request a separate four-byte mapping at offset `0xA00` and read BOOT_42 once. The mapping's returned virtual address already includes the requested offset. Each mapping is released immediately after its load. Identity, BAR0, memory decoding and D0 are rechecked before each mapping and immediately before each load. Actual VM mappings retain page granularity.

BOOT_0 uses its architecture extension bit and implementation field. BOOT_42 uses architecture bits `29:24`, implementation bits `23:20` and chip ID bits `29:20`. Both must agree on architecture `0x16` and implementation `0x07`; BOOT_42 chip ID must be `0x167`. The local selector then reports **TU117, variant index 41**, tied to NVIDIA source commit `1a82fbfda8f321b056eb3568850f9316c5e465c5`.

There are at most two aligned 32-bit volatile loads per startup. The prototype performs no scans, retries, polling, writes, BAR sizing, ACPI calls, resets, power transitions, firmware operations, interrupt setup or DMA allocation. The table result is identification metadata; no NVIDIA HAL object is constructed or executed.

## Report outcomes

The native reporter validates the actual PCI parent and a strict Format 3 snapshot, including phase order, read counts, decoded identities and pinned table provenance. It opens no hardware user client and writes no registry properties.

| Status | Meaning |
| --- | --- |
| `hal_matched` | Both identification reads agree and the local pinned table selects TU117 variant 41. |
| `refused` | A prerequisite failed before a load in the relevant phase. Earlier completed reads remain explicitly counted. |
| `failed` | An identification read completed but returned zero, all-ones or unexpected fields. |
| `outdated_probe` | A valid 0.1.0 or 0.2.0 probe is loaded; replace the kext on the EFI actually used to boot and reboot. |
| `not_attached` | The service was not found; the report does not establish why loading or matching failed. |
| `error` | Snapshot, provider or report validation failed. |

BOOT_42 is marked `not_attempted` when BOOT_0 is not identified. A HAL match requires exactly two completed reads. Refusal is a complete diagnostic outcome. Failed reads and invalid reports return a nonzero exit status. Raw reports and resource addresses remain private. Runtime stop/unload remains untested.

## Build and source references

The native Intel CI build compiles and links the kext, checks Mach-O types and module metadata, verifies ad-hoc signatures, and runs policy and native decoder tests. It executes the packaged reporter without loading the experimental kext. Version 0.2.0 passed its [native build](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/actions/runs/38664993966); the laptop BOOT_0 result was established separately. Each archive's BUILD.json records its completed native checks. Version 0.3.0 laptop validation is pending.

An optional source bundle can be generated from an exact checkout with `builders/package_nvidia_local.py --source-commit FULL_SHA --output-dir OUTPUT`. The generated **S540-nvidia-build-local-v2.zip** supports Intel macOS with Apple Command Line Tools. Its wrapper fetches the pinned public SDK Git revision and performs native compile, signature and decoder checks. It does not install or load the probe. The explicit `--allow-legacy-probe` build option accepts an already-loaded 0.1.0 or 0.2.0 probe as outdated; CI remains strict about having no loaded probe.

The SDK is pinned to [MacKernelSDK commit 3f75008](https://github.com/acidanthera/MacKernelSDK/tree/3f750085caa17ec3a7880f11c11bf4f48cd6a164). Its unmodified module runtime includes Apple code under APSL 2.0. The built archive includes that license and its source location in **THIRD-PARTY-NOTICES.txt**; project source uses the adjacent MIT license.

The identification registers are documented in pinned NVIDIA [nv_ref.h](https://github.com/NVIDIA/open-gpu-kernel-modules/blob/1a82fbfda8f321b056eb3568850f9316c5e465c5/src/common/inc/swref/published/nv_ref.h). The real resource manager consumes BOOT_42 in [`_halmgrIsChipSupported`](https://github.com/NVIDIA/open-gpu-kernel-modules/blob/1a82fbfda8f321b056eb3568850f9316c5e465c5/src/nvidia/src/kernel/core/hal_mgr.c#L125-L148); the local match follows its fields and the pinned [TU117 table entry](https://github.com/NVIDIA/open-gpu-kernel-modules/blob/1a82fbfda8f321b056eb3568850f9316c5e465c5/src/nvidia/generated/g_chips2halspec_nvoc.c#L39-L43). Apple API behavior was reviewed against [IOPCIFamily](https://github.com/apple-oss-distributions/IOPCIFamily/tree/4822b27a36e2de70e231ecf2bf3021384fab6ec2) and [XNU](https://github.com/apple-oss-distributions/xnu/tree/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea).
