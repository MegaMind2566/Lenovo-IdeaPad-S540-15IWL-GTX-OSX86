# NVIDIA integrated CPU support runtime prototype

Version **0.7.0** combines the existing foundation/caller/object-lifecycle blocks with a checked CPU runtime, NVIDIA string and pseudorandom utilities, and real vector/list library consumers used by the resource manager. Startup, failure cleanup, reporting and delivery are integrated into one package.

**This is an experimental CPU-side integration milestone.** NVIDIA HAL/RM construction, GPU initialization, firmware, DMA, GPU commands and graphics/Metal acceleration remain unimplemented.

## One combined laptop test

Use the EFI on the **240 GB test disk** and retain the working Samsung EFI as the fallback.

1. Extract **S540-nvidia-transport-v7.zip** into Downloads.
2. Save the previous `EFI/OC/Kexts/S540NvidiaPCIProbe.kext` outside the EFI directory.
3. Replace that kext with the new one. **Keep config.plist unchanged.**
4. Boot from the 240 GB EFI and select Tahoe.
5. Run:

   ```bash
   bash "$HOME/Downloads/S540-nvidia-transport-v7/CHECK-TRANSPORT.command"
   ```

Share **nvidia-transport.json** from the new **NVIDIA-TRANSPORT…** folder on the Desktop. Expected success is **`integrated_passed`**, version **`0.7.0`**, format **7**, with all four CPU evidence blocks passed. Version 0.6.0 is already confirmed; its checks remain automatic regression coverage within this report and require no separate test.

If startup fails, boot using the Samsung EFI and restore the previous test-disk kext. Rollback uses a reboot; runtime unload is untested. This package requires no NVRAM reset, SIP change or new OpenCore entry.

## Combined scope

- The existing 23 foundation and 35 original-caller/reserve checks remain in the same startup sequence.
- Real NVPort allocator dispatch and count tracking cover global/custom allocation and release.
- Original allocator-owned synchronization callers create and destroy their own NVPort storage and Darwin backing objects.
- Spinlocks preserve the prior interrupt state in the kernel backend.
- The bounded startup verifies lifecycle transitions and returns tracked allocations, reserve slots and OS backing-object counts to their initial state.
- One nonblocking startup lease covers both the existing checks and the new lifecycle. No worker thread or intentionally contended mutex wait runs during kernel startup.
- The [support runtime](../nvidia-nvport-runtime/README.md) adds original string and xorshift utilities, checked memory/PRNG initialization and reverse-order shutdown.
- Original vector/list consumers exercise tracked allocation, growth, insertion, iteration, removal and destruction. An explicit vector correction fixes old-buffer release when an allocated vector is empty; allocation failure preserves the previous container.
- Support initialization, utilities, consumers and cleanup have independent evidence. Success requires every component, not only the previous 130 startup assertions.

The memory entry point is an explicit, status-returning adaptation of NVIDIA's bootstrap. It checks lock-storage allocation and spinlock initialization before publishing initialized state. The support core then checks actual PRNG allocation and refuses shutdown while consumer allocations or custom allocators remain live. Adaptations and exact source provenance are recorded in the manifests. This is a selected CPU profile, not full NvPort core or RM initialization.

The selected release profile enables allocation counters. Fenceposts, allocation lists, caller information, GSP limits and log instrumentation are excluded. Active allocation counts are real; this profile does not provide active/peak allocation byte sizes. Reserve and OS-object accounting provide separate cleanup evidence.

The backing reserve remains bounded: **4 MiB**, **32 slots**, **128 KiB per request**, **16-byte alignment**. Tracking and allocator metadata also consume slots. Oversize and exhausted requests fail explicitly. This is not a general RM heap, pageable-memory implementation, VRAM or DMA service. The public Unix allocation profile is non-interrupt context and no sleeping; a lock-free bitmap does not establish interrupt-context support.

## GPU and hardware boundary

The exact PCI gate and existing D0, memory-decode, BAR0, mapping and provider-ownership guards remain in place. The only GPU accesses are one read-only BOOT_0 load and one conditional read-only BOOT_42 load. No new MMIO operation, register write, firmware, DMA, hardware interrupt registration or power transition is added.

Each identification mapping is read-only and released after its single load. A hardware MMIO load can fault or stall the kernel; a software deadline cannot make that individual load recoverable.

The startup uses silent shutdown and registers no OOM report callback. Non-silent tracking-registry reports hold a spinlock and are outside the selected kernel diagnostic profile; the real diagnostic bridge rejects unsupported interrupt/interrupt-disabled contexts.

Kernel contention, interrupt-context execution, suspend/wake, runtime stop/unload and full RM compatibility remain unvalidated. Native concurrency tests cover the functional userspace backends and do not prove those kernel behaviors.

## Report states

| Format-7 status | Meaning |
|---|---|
| `integrated_passed` | Foundation, original-caller, NVPort lifecycle and support-runtime blocks passed; TU117 identification matched. |
| `foundations_failed` / `callers_failed` / `lifecycle_failed` / `support_failed` | A CPU startup block reported failure. Preserve the report. |
| `invalid_foundations` / `invalid_callers` / `invalid_lifecycle` / `invalid_support` | CPU evidence is absent or malformed. |
| `outdated_probe` | An earlier probe is loaded. Replace the kext on the EFI actually used for boot and reboot. |
| `not_attached` | The probe service is absent; the report alone does not identify the cause. |
| `refused` / `failed` / `error` | A hardware prerequisite, identification operation or report validation failed. |

The reporter needs no administrator password or developer tools. It reads published evidence and does not install software or change EFI, SIP, NVRAM or kernel collections. Raw reports and resource addresses remain private.

## Build and provenance

**BUILD.json** records the exact source revision, validation results, source/output hashes, module metadata, platform imports and kernel dependencies. The archive includes source, original reference bytes, adaptation records and NVIDIA/LLVM/MacKernelSDK licenses.

One native Intel macOS CI builds the complete package. It runs original-caller and lifecycle checks, allocation overflow/exhaustion and partial-initialization cases, synchronization failure cleanup, native concurrent execution, fatal assertion subprocesses and AddressSanitizer/UndefinedBehaviorSanitizer. The actual combined startup entry point is also executed natively. Kernel compilation/linking, exact import auditing, signatures, strict decoder tests and the packaged launcher are checked. CI does not load the extension.

NVIDIA is pinned to `1a82fbfda8f321b056eb3568850f9316c5e465c5`; MacKernelSDK to `3f750085caa17ec3a7880f11c11bf4f48cd6a164`. The compiler's `__bzero` RAM helper (Mach-O `___bzero`) is an explicitly reviewed libkern export. All new dependencies must be audited before the package is accepted.
