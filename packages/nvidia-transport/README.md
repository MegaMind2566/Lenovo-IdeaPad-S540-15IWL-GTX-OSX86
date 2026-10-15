# NVIDIA hardware transport preparation prototype

Version **0.8.0** combines the existing CPU runtime with bounded host-memory DMA preparation, read-only PCI/interrupt inventory, and firmware/RPC preflight. One package and one report cover the complete sequence.

**This is transport preparation.** NVIDIA HAL/RM construction, GPU initialization, verified device DMA, live interrupt delivery, firmware loading and graphics/Metal acceleration remain unimplemented.

The confirmed v7 laptop baseline passed all 258 CPU startup checks: 128 support, 72 lifecycle, 35 caller/reserve and 23 foundations. V8 retains those blocks as automatic regression coverage. A v8 hardware result is not yet recorded; no separate v7 rerun is required.

## One combined laptop checkpoint

Use the EFI on the **240 GB test disk**. Retain the working Samsung EFI as the fallback.

1. Extract **S540-nvidia-transport-v8.zip** into Downloads.
2. Save the previous `EFI/OC/Kexts/S540NvidiaPCIProbe.kext` outside the EFI directory.
3. Replace that kext with the packaged version. **Keep config.plist unchanged.**
4. Boot from the 240 GB EFI and select Tahoe.
5. Run:

   ```bash
   bash "$HOME/Downloads/S540-nvidia-transport-v8/CHECK-TRANSPORT.command"
   ```

Share **nvidia-transport.json** from the new **NVIDIA-TRANSPORT…** folder on the Desktop. Expected success is **`transport_prepared`**, version **`0.8.0`**, format **8**, with all four CPU blocks and `hardware_preparation` passed. The six GPU/device activity flags remain false even on success.

This single checkpoint includes startup, host-memory preparation, PCI capabilities, observed interrupt configuration, parser/RPC checks and cleanup. No additional package or individual primitive test is needed.

If startup fails, boot using the Samsung EFI and restore the previous test-disk kext. Rollback uses a reboot; runtime unload is untested. This package requires no NVRAM reset, SIP change or new OpenCore entry. The reporter requires no administrator password or developer tools.

## Combined implementation

- **CPU runtime:** existing timer, memory, atomics, allocation, mutex, tracked lifecycle, string/PRNG and real vector/list consumer checks. One nonblocking lease covers the complete sequence.
- **Host-memory DMA preparation:** allocate a bounded 64 KiB host buffer, prepare its descriptor and DMA command, enumerate bounded segments, verify the CPU pattern, then complete and release every owned resource. No GPU command uses these segments and their addresses are never published.
- **Read-only PCI adapter:** the exact NVIDIA `os_pci_read_byte`, `os_pci_read_word` and `os_pci_read_dword` ABI operates on the authenticated, borrowed provider in standard configuration space.
- **Interrupt inventory:** walk the bounded capability list and inspect PM, MSI and MSI-X metadata and geometry. Published enable bits describe observed configuration. The probe registers and arms no interrupt source.
- **Firmware/RPC preflight:** a hardened parser checks the pinned ELF64 GSP container layout, TU117 signature-family selection, bounded MCTP/NVDM/RPC framing, local request ownership and layout arithmetic using CPU fixtures. [Firmware scope and provenance](../nvidia-hardware-transport/firmware/README.md) describe its limits.
- **Failure cleanup:** all blocks retain separate evidence. Native fault cases exercise partial initialization and cleanup; the kernel checkpoint runs a finite sequential startup without worker threads or intentional mutex contention.

DMA mode is explicit. `provider_mapped` uses the published provider mapper; `direct_untranslated` prepares untranslated host segments. Both can pass this bounded preparation stage. Neither establishes GPU DMA compatibility, and `device_dma_verified` remains false. An unresolved mapper is reported as unavailable instead of entering an unbounded mapper lookup.

No real firmware image or approved firmware hash is included. Parser success does not authenticate a real firmware image. The readiness gate keeps firmware loading blocked; `firmware_image_verified` and `firmware_loaded` remain false.

The existing allocation reserve remains **4 MiB**, with **32 slots**, **128 KiB per request** and **16-byte alignment**. Tracking metadata consumes reserve space. This is a selected CPU allocation profile, not a general RM heap, VRAM allocator or pageable-memory service.

## Preparation evidence

The kernel publishes an exact **25-key `HardwarePreparation` dictionary**. The reporter emits it as `hardware_preparation`, using snake_case field names.

| Fields | Contract |
|---|---|
| `Version`, `Status`, `Checks` | Version 1, a positive check count, and a status consistent with all six preparation components. |
| `HostDma`, `PciReadAdapter`, `InterruptInventory`, `FirmwareParser`, `FirmwareRpc`, `Cleanup` | Strict Booleans. Every component must pass for preparation success. |
| `DmaMode`, `DmaBytes`, `DmaSegments`, `DmaReason` | Finite mode/reason codes; 0–65,536 bytes and 0–32 segments. Successful host preparation requires 65,536 bytes, 16–32 segments, an available mode and reason `none`. |
| `PciReason`, `PciCapabilities` | Finite inventory reason and 0–48 capabilities. Successful interrupt inventory requires the complete-inventory reason and at least one capability. |
| `MsiVectors`, `MsixVectors` | MSI is zero or a power of two up to 32; MSI-X is 0–2,048. |
| `MsiObservedEnabled`, `MsixObservedEnabled` | Strict observed configuration bits. An enabled bit requires a nonzero corresponding vector count. These are separate from probe interrupt activation. |
| `FirmwareLoaded`, `FirmwareImageVerified`, `InterruptsEnabled`, `GpuInitialized`, `RmInitialized`, `DeviceDmaVerified` | All six must be Boolean false. Preparation cannot claim these later stages are complete. |

Raw reports and resource addresses remain private. The new DMA/inventory evidence contains bounded counts and reasons, not DMA addresses, MSI-X table addresses or firmware buffers.

## GPU access boundary

The exact-device gate, D0, memory-decode, BAR0, mapping and provider-ownership guards remain in place. The only GPU MMIO accesses are one read-only BOOT_0 load and one conditional read-only BOOT_42 load. Each identification mapping is read-only and released after its single load.

Preparation uses its own nonblocking provider-arbitration scope and releases it before the existing identification scope. It adds no register write, bus-master enable, firmware upload, interrupt registration or power transition. A hardware MMIO load can still fault or stall the kernel; a software deadline cannot make that individual load recoverable.

Kernel contention, interrupt-context operation, suspend/wake, runtime stop/unload and full RM compatibility remain unvalidated. Native concurrency tests exercise userspace backends and do not establish those kernel behaviors.

## Report states

| Format-8 status | Meaning |
|---|---|
| `transport_prepared` | All four CPU blocks and all preparation components passed; the two-read TU117 identification matched. GPU/device readiness flags remain false. |
| `preparation_failed` | Valid preparation evidence records a component failure. Preserve the report. |
| `invalid_preparation` | Preparation evidence is missing, malformed, inconsistent or claims activity outside this version's scope. |
| `foundations_failed` / `callers_failed` / `lifecycle_failed` / `support_failed` | A preceding CPU startup block failed. |
| `invalid_foundations` / `invalid_callers` / `invalid_lifecycle` / `invalid_support` | Preceding CPU evidence is absent or malformed. |
| `outdated_probe` | A format 1–7 probe is loaded. Replace the kext on the EFI actually used for boot and reboot. |
| `not_attached` | The probe service is absent; this report alone does not identify the cause. |
| `refused` / `failed` / `error` | An identification prerequisite, hardware identification operation or report validation failed. |

## Build and provenance

**BUILD.json** records the source revision, validation results, hashes, module metadata, audited platform imports and kernel dependencies. The archive includes source, pinned reference inputs, adaptation records and required licenses. It contains no real firmware image or approved firmware-image hash.

Native Intel macOS CI builds the complete package and runs the combined startup through explicit host fixtures, failure injection, native concurrency checks, fatal assertion cases and sanitizers. It checks kernel compilation/linking, imports, signatures, strict reporter decoding and the packaged launcher. **CI does not load the extension or validate GPU operation.**

NVIDIA is pinned to `1a82fbfda8f321b056eb3568850f9316c5e465c5`; MacKernelSDK to `3f750085caa17ec3a7880f11c11bf4f48cd6a164`. New kernel imports require an explicit audit. Reference parser inputs document provenance; the hardened firmware parser is an adaptation rather than an unchanged NVIDIA parser.
