# NVIDIA integrated OS-adapter prototype

Version **0.4.0** combines the bounded TU117 identification probe with the Darwin clock, ordinary-RAM memory operations, NVIDIA atomics, host-RAM allocator and ordinary-thread mutex adapter. One startup self-check exercises those CPU components inside the kernel. The GPU identification remains the same two read-only register loads used by the confirmed v0.3.0 probe.

**This is a development checkpoint. It does not initialize the GPU or provide graphics acceleration.** The NVIDIA HAL and resource manager are not instantiated. Firmware, DMA, command submission and display output remain unimplemented. Successful CI checks establish compilation and native user-space behavior; the laptop report establishes the kernel execution result separately.

## Confirmed laptop result

The October 15, 2026 format-4 laptop report returns `integrated_passed`, `complete=true`, and no warnings. The actual PCI provider identity is verified. All 23 startup assertions passed across the five CPU components: timer, ordinary-RAM operations, original C++ atomics, ordinary host-RAM allocation and thread mutexes. BOOT_0 and BOOT_42 each completed one read and retained the TU117 variant-41 match.

This confirms the bounded startup check in the real Tahoe kernel. It runs on one thread, uses small RAM buffers and one 256-byte allocation, and releases its allocations and mutex before publishing the snapshot. It does not validate kernel contention, interrupt-context allocation, suspend behavior, full NVIDIA caller compatibility or GPU initialization. Raw reports and resource addresses remain private. No repeated laptop test is needed for this checkpoint.

## Deployment and reporter

Extract **S540-nvidia-transport-v4.zip** into Downloads. Keep the working Samsung EFI available. Use only the separate EFI on the **240 GB test disk**.

1. Save the existing `EFI/OC/Kexts/S540NvidiaPCIProbe.kext` outside the EFI directory.
2. Replace that kext with the one in this package. **Keep the existing config: no edit is required.**
3. Boot from the 240 GB disk, then select Tahoe.
4. Run this one command:

   ```bash
   bash "$HOME/Downloads/S540-nvidia-transport-v4/CHECK-TRANSPORT.command"
   ```

5. Share **nvidia-transport.json** from the new **NVIDIA-TRANSPORT…** folder on the Desktop.

The expected result is **`integrated_passed`**: all five CPU-component checks passed in the kernel, and both identification registers still select TU117 variant 41. This result does not establish GPU initialization or acceleration. If boot fails, boot from Samsung and restore the previous kext on the test disk. Runtime unload remains untested; rollback uses a reboot.

The reporter needs no administrator password or developer tools. It does not install a kext or change EFI, SIP, NVRAM or kernel collections.

## Boundaries and report results

The PCI gate remains `10DE:1F91`, subsystem `17AA:3806`, revision `A1`. The probe requires an already-enabled memory decoder, D0 and a matching 16 MiB BAR0 descriptor. It opens no GPU user client and performs no power transitions, GPU writes, firmware operations, interrupt setup or DMA allocation.

The probe performs at most one aligned 32-bit BOOT_0 load and one conditional BOOT_42 load. Both must identify TU117. Each uses a unique read-only, cache-inhibited mapping released after the load; prerequisites are checked again before each mapping and load. An MMIO load can fault or hang the kernel; software cannot provide a recoverable timeout for that load.

The new self-check uses ordinary CPU RAM. The allocator uses `IOMalloc`/`IOFree`; the mutex uses `IOLock` in a sleepable thread context. Allocation and lock resources created by the check are released before the report is published. No worker threads or GPU operations are added.

| Format-4 status | Meaning |
| --- | --- |
| `integrated_passed` | CPU-component self-checks passed in the kernel and both GPU IDs select TU117 variant 41. |
| `refused` | A hardware prerequisite failed before the corresponding load. |
| `foundations_failed` | At least one CPU-component check failed. |
| `invalid_foundations` | The CPU-component result is absent or invalid. |
| `failed` | An identification read failed. |
| `outdated_probe` | An earlier probe is loaded. Replace the kext on the EFI actually used to boot, then reboot. |
| `not_attached` | The service was not found; the report does not establish the cause. |
| `error` | Snapshot, actual PCI provider or report validation failed. |

The format-4 report records component checks separately from GPU identification. Older snapshots remain recognizable as outdated. Raw reports and resource addresses remain private.

## Build and provenance

The native Intel CI build runs the existing timer, memory and C/C++ atomic checks; allocator alignment, allocation failure and exact-size free checks; mutex contention and publication checks; and the same integrated CPU self-check used by the kernel probe. Address and undefined-behavior sanitizers instrument the new backends and integration. The build also compiles and links the real kernel sources, audits adapter imports, checks Intel Mach-O metadata, verifies ad-hoc signatures, and runs the report decoder. CI does not load the experimental kext.

**BUILD.json** records the exact project commit, source and output hashes, native results and kernel import audit. The archive includes the corresponding adapter/probe source, NVIDIA reference inputs and provenance records under **source/**. NVIDIA source is pinned to commit `1a82fbfda8f321b056eb3568850f9316c5e465c5`. MIT notices remain in the original and adapted files. LLVM and MacKernelSDK license texts and source references are included in **licenses/** and **THIRD-PARTY-NOTICES.txt**.

MacKernelSDK is pinned to commit `3f750085caa17ec3a7880f11c11bf4f48cd6a164`. An optional source-only local-build bundle can be generated with `builders/package_nvidia_local.py`; the ready-built CI package is intended for the laptop test above.
