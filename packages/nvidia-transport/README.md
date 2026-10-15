# NVIDIA Resource Server and host-service prototype

Version **0.9.0** combines the original standalone NVIDIA Resource Server, Darwin host-memory services, a retained read-only PCI session, the existing CPU/transport checks, and verification of the actual matching firmware pair. One compiled package and one report cover the complete checkpoint.

**This is a selected Resource Server profile.** Full RM construction, GPU/GSP initialization, verified device DMA, live interrupt delivery, firmware loading and graphics/Metal acceleration remain unimplemented.

V8 remains the confirmed laptop baseline: all 390 kernel startup checks passed, including cleanup, exact provider identity and the two-read TU117 variant-41 match. V9 is a candidate until native macOS CI, package verification and its combined laptop result are recorded. Its earlier checks run automatically; no separate v8 rerun is needed.

## One combined laptop checkpoint

Use the EFI on the **240 GB test disk**. Retain the working Samsung EFI as the fallback.

1. Extract **S540-nvidia-transport-v9.zip** into Downloads. Keep its complete `firmware` directory.
2. Save the previous `EFI/OC/Kexts/S540NvidiaPCIProbe.kext` outside the EFI directory.
3. Replace that kext with the packaged version. **Keep config.plist unchanged.**
4. Boot from the 240 GB EFI and select Tahoe.
5. Run:

   ```bash
   bash "$HOME/Downloads/S540-nvidia-transport-v9/CHECK-TRANSPORT.command"
   ```

Share **nvidia-transport.json** from the new **NVIDIA-TRANSPORT…** folder on the Desktop. Expected success is **`resource_server_prepared`**, version **`0.9.0`**, format **9**. It requires every kernel block and the separate `firmware_assets` result to pass.

The launcher verifies the three packaged firmware/license files in that same command. No extra memory, PCI, firmware or individual primitive package is required. The reporter needs no administrator password or developer tools.

If startup fails, boot using the Samsung EFI and restore the previous test-disk kext. Rollback uses a reboot; runtime unload is untested. This package requires no NVRAM reset, SIP change or new OpenCore entry.

## Combined implementation

| Block | Included behavior | Boundary |
|---|---|---|
| Existing CPU runtime | Foundations, original callers, tracked allocation, object lifecycle, string/PRNG utilities and real vector/list consumers | Selected bounded runtime; ordinary-thread startup |
| Hardware preparation | 64 KiB host-memory descriptor/DMA-command preparation, CPU verification, PCI capability/IRQ inventory and parser/RPC fixtures | Host segments are not proof of device DMA; no interrupt source is armed |
| Resource Server | Original NVOC objects, clients, resources, parent/child handles, access isolation, sharing and original dispatch/refusal paths | Standalone library profile; no global `coreInitializeRm()` or GPU RM |
| Darwin host memory | Exact NVIDIA allocation/free and kernel-mapping ABI, wired cached pages, authenticated handles and deferred allocation release | Device-less 4 KiB pages, bounded allocations; physical pages are not device DMA addresses |
| Retained PCI session | Provider lifetime, target revalidation, aligned configuration reads, generation-qualified handles and quiescent stop | Read-only observer; no PCI write, provider open or interrupt registration |
| Actual firmware assets | Matching unmodified GSP/UCODES files and full license, exact byte hashes, ELF/UCODES parsing and checked layout | Userspace CPU-file readiness; no upload, GPU signature authentication or execution |

The [Resource Server/host-service bundle](../nvidia-rm-services/README.md) and [firmware assets](../nvidia-firmware-assets/README.md) document source provenance and narrower contracts. All owned objects are released before the aggregate returns. One nonblocking startup lease covers earlier regressions and the selected services. IOKit provider arbitration and ordinary mutexes can wait: `lockForArbitration(false)` is not a nonblocking try-lock.

The existing reserve remains **4 MiB**, with **32 slots**, **128 KiB per request** and **16-byte alignment**. Metadata consumes reserve space. The added host-memory service is separately bounded; neither service supplies VRAM or establishes GPU DMA compatibility.

## Kernel and userspace evidence

The kernel snapshot retains the earlier four CPU blocks and exact **25-key `HardwarePreparation` dictionary**. Its `hardware_preparation` JSON includes DMA mode/size/segment counts, finite failure reasons, PCI capability/vector counts, observed MSI/MSI-X enable bits and cleanup. Successful host preparation requires 65,536 bytes and 16–32 bounded segments. `provider_mapped` and `direct_untranslated` remain distinct; neither proves device DMA operation.

Format 9 adds the exact **16-key `RmServices` dictionary**, emitted as `rm_services`:

| Fields | Contract |
|---|---|
| `Version`, `Status`, `Checks` | Version 1, positive total checks and status consistent with all eight service components. |
| `ResourceServer`, `HostMemory`, `PciSession`, `Clients`, `Resources`, `Sharing`, `Control`, `Cleanup` | Strict Booleans; every component must pass. |
| `ResourceServerChecks`, `HostMemoryChecks`, `PciSessionChecks` | Bounded integral component counts. A passing component requires a positive count; their sum cannot exceed the total. |
| `Profile` | Exactly `standalone-resource-server-cached-host-readonly-pci`. |
| `FullRmInitialized` | Boolean false. Selected Resource Server objects do not establish full RM startup. |

The reporter's separate `firmware_assets` field verifies actual bytes from `firmware/gsp_tu10x.bin`, `firmware/ucodes_tu10x.bin` and the complete `firmware/NVIDIA-DRIVER-LICENSE.txt`. Its 15-check result includes file presence, hashes, GSP/UCODES parsing, exact sizes/directory counts, pair readiness and cleanup. Missing, changed or unsafe files block final success. Paths, file contents and addresses are not copied into the report.

`firmware_assets.pair_ready` means immutable approved files are ready as **CPU input**. The kernel's six later-activity flags remain false: `firmware_image_verified`, `firmware_loaded`, `device_dma_verified`, `interrupts_enabled`, `gpu_initialized` and `rm_initialized`. Userspace asset verification does not overwrite those kernel flags. Observed MSI/MSI-X enable bits describe existing configuration and are separate from this probe arming an interrupt.

## Hardware boundary and remaining work

The exact-device gate, D0, memory-decode, BAR0, mapping and provider-ownership guards remain in place. GPU MMIO access is still exactly one read-only BOOT_0 load and one conditional read-only BOOT_42 load. Each mapping is read-only and released after its single load.

This package adds no GPU register write, bus-master enable, firmware upload, interrupt registration or power transition. A hardware MMIO load can fault or stall the kernel; a software deadline cannot make that individual load recoverable.

Kernel contention, interrupt-context execution, suspend/wake, runtime stop/unload, full RM compatibility, GSP startup and acceleration remain separate work. Native concurrency tests exercise userspace backends and do not establish those kernel behaviors. Raw reports and resource addresses remain private.

## Report states

| Format-9 status | Meaning |
|---|---|
| `resource_server_prepared` | Earlier kernel blocks, selected Resource Server/host services, TU117 identification and the actual CPU firmware-file verification passed. Full RM/GPU initialization remains false. |
| `rm_services_failed` / `invalid_rm_services` | A selected service failed, or its kernel evidence is missing/malformed. |
| `firmware_assets_unavailable` / `firmware_assets_failed` / `invalid_firmware_assets` | The packaged firmware check was omitted, failed, or returned inconsistent evidence. |
| `preparation_failed` / `invalid_preparation` | Hardware-preparation evidence failed or is absent/malformed. |
| `foundations_failed` / `callers_failed` / `lifecycle_failed` / `support_failed` | A preceding CPU block failed; corresponding `invalid_*` states mean absent/malformed evidence. |
| `outdated_probe` | A format 1–8 probe is loaded. Replace the kext on the EFI actually used for boot and reboot. |
| `not_attached` | The probe is absent; this report alone does not identify the cause. |
| `refused` / `failed` / `error` | An identification prerequisite, hardware identification operation or report validation failed. |

## Build and provenance

**BUILD.json** records the source revision, checks, hashes, module metadata, audited imports and kernel dependencies. The archive includes source, reference inputs, adaptation records, the three unmodified firmware/license files and required licenses. Firmware retains the complete NVIDIA Driver License Agreement separately from the bridge/parser source license.

Native Intel macOS CI builds the complete bundle, exercises the shared startup with explicit host fixtures, failure injection, concurrency cases and sanitizers, and verifies actual firmware bytes. It also checks kernel compilation/linking, imports, signatures, strict reporter decoding and the packaged launcher. **CI does not load the extension or prove GPU operation.**

NVIDIA source is pinned to `1a82fbfda8f321b056eb3568850f9316c5e465c5`; MacKernelSDK to `3f750085caa17ec3a7880f11c11bf4f48cd6a164`. New kernel imports require an explicit audit. The optional local build wrapper uses a private Python environment with the pinned extraction dependency; it is not part of the laptop checkpoint.
