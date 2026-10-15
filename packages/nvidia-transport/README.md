# NVIDIA integrated NVPort prototype

Version **0.5.0** combines the existing two-read TU117 identification with a bounded kernel startup check of original NVIDIA allocation and mutex callers, backed by a preallocated memory reserve and a new mutex implementation. The earlier timer, RAM and atomic checks run against these same backends.

**This is an experimental integration checkpoint, not a complete NVIDIA driver.** It does not instantiate NVIDIA HAL/RM objects, initialize the GPU, load firmware, perform DMA, submit GPU commands or provide rendering/Metal/display acceleration.

## One laptop test

Use the separate EFI on the **240 GB test disk**. Keep the working Samsung EFI available.

1. Extract **S540-nvidia-transport-v5.zip** into Downloads.
2. Back up the current `EFI/OC/Kexts/S540NvidiaPCIProbe.kext` outside the EFI directory.
3. Replace that kext with the new one. **Keep the current config.plist unchanged.**
4. Boot from the 240 GB EFI, then select Tahoe.
5. Run:

   ```bash
   bash "$HOME/Downloads/S540-nvidia-transport-v5/CHECK-TRANSPORT.command"
   ```

Share **nvidia-transport.json** from the new **NVIDIA-TRANSPORT…** folder on the Desktop.

Expected success is **`integrated_passed`** from version **`0.5.0`**, format **5**. The result requires both CPU blocks to pass and the same two identification registers to select TU117 variant 41. A successful startup normally records **23 foundation checks and 35 caller/reserve checks**.

If startup fails, boot from the working Samsung EFI and restore the previous kext on the test disk. Runtime unload is untested; rollback uses a reboot. No NVRAM reset, SIP change or config edit is required by this package.

## What the startup check covers

- All three original allocation callers and five original mutex callers execute in the kernel.
- The 4 MiB reserve supplies 32 fixed slots, with a 128 KiB request limit and 16-byte alignment.
- Allocation failure, full-reserve refusal, live-allocation shutdown refusal, reuse and quiescent cleanup are checked.
- Caller-owned mutex initialization, available/busy conditional acquisition, ordinary uncontended acquisition, release and destruction are checked.
- Timer, small-buffer RAM operations and original C++ atomics run against the new backends.

The same production `checkIntegrated()` entry point runs in native CI and in probe startup. A nonblocking singleton lease serializes reserve lifecycle operations. All successful startup allocations are released before the immutable report is published.

The startup sequence is finite and single-threaded. It creates no workers and does not intentionally enter the kernel mutex wait path. Kernel contention, interrupt-context allocation, suspend/wake and full NVIDIA caller compatibility are not established by this test. The reserve is not a general RM heap or VRAM/DMA allocation service.

## GPU access boundary

The PCI gate remains `10DE:1F91`, subsystem `17AA:3806`, revision `A1`. The existing memory-decode, D0, BAR0, provider-ownership and mapping guards remain in place. The only GPU register accesses are one aligned read-only BOOT_0 load and one conditional BOOT_42 load. There are no added GPU reads, writes, power transitions, firmware, DMA or interrupt setup.

Each read uses a unique read-only cache-inhibited mapping released after its single load. An MMIO load can fault or hang the kernel; software cannot provide a recoverable timeout for that individual load.

## Report results

| Format-5 status | Meaning |
|---|---|
| `integrated_passed` | Foundations and original callers passed; two-register TU117 identification matched. |
| `foundations_failed` / `callers_failed` | A CPU startup block failed. Preserve the report. |
| `invalid_foundations` / `invalid_callers` | A CPU result is absent or malformed. |
| `refused` / `failed` | A GPU identification prerequisite or load failed. |
| `outdated_probe` | An earlier probe, including v4, is loaded. Replace the kext on the EFI actually used to boot and reboot. |
| `not_attached` | The probe service is absent; the report does not identify the cause. |
| `error` | Snapshot, provider or report validation failed. |

The reporter requires no administrator password or developer tools. It does not install a kext or change EFI, SIP, NVRAM or kernel collections. Raw reports and resource addresses remain private.

## Build and provenance

**BUILD.json** records the exact project commit, source/output hashes, native results, kernel imports and module version. The complete package checks thin x86_64 Mach-O output, matching kmod/Info versions, KPI dependencies, signatures, decoder fixtures and the packaged launcher.

Native tests exercise actual callers, reserve exhaustion/reuse/concurrent churn, mutex contention/publication, the mandatory failed-acquisition assertion and the same integrated startup sequence. AddressSanitizer and UndefinedBehaviorSanitizer instrument production sources with fatal diagnostics. CI compiles and links the kernel code but does not load it.

The archive includes source, reference bytes, adaptation/provenance records, validation reports and NVIDIA/LLVM/MacKernelSDK licenses. NVIDIA is pinned to `1a82fbfda8f321b056eb3568850f9316c5e465c5`; MacKernelSDK to `3f750085caa17ec3a7880f11c11bf4f48cd6a164`. These build checks do not establish v5 laptop execution or graphics acceleration.
