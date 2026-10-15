# Retained PCI provider sessions

This component provides a reusable, retained, read-only PCI provider session for later RM integration. It is part of the combined services bundle. It does not replace the existing transport C exports, initialize RM or leave a persistent session after its startup check.

## Interface and lifetime

`S540NvidiaRmPci::ProviderSession` retains exactly one provider after verifying `10DE:1F91`, subsystem `17AA:3806`, revision `A1` and display class `030000`. It captures immutable identity and bus/device/function metadata for that session generation. Production metadata records `readOnly=true`, `providerOpened=false` and `segmentKnown=false`.

Owner-issued handles are opaque integer tokens, never pointers that the adapter dereferences. A process-wide monotonic generation prevents a stopped handle from becoming valid after restart or reuse of object storage. Foreign, null and stale handles fail before provider access. The generation counter refuses exhaustion rather than wrapping.

Every accepted read holds an operation lease. `stop()` first rejects new leases, waits for accepted operations to finish, and then releases the provider once. Concurrent stop callers do not own a second release. The owner must prevent new API entry before freeing session object storage. Stop must not be called from a backend callback or while holding a guard needed by another accepted reader.

Kernel start and read callers hold provider arbitration on their calling thread. Each access rejects inactive or already-open providers and rechecks the exact target identity. The session does not open the provider or claim exclusive GPU ownership. Framework `lockForArbitration(false)` may wait for another owner; it is not a nonblocking try-lock. The aggregate startup lease remains a separate caller responsibility.

## Configuration and lookup policy

Byte, word and dword reads cover the aligned 4 KiB PCI configuration aperture. Narrow widths, crossing accesses and invalid alignment are rejected before access; valid outputs are zeroed on failure. The pinned public SDK wrappers call the exported `extendedConfigRead8/16/32` APIs. Extended configuration reads are PCI metadata access, not GPU BAR MMIO.

A direct owner-issued handle is usable without inventing a PCI segment. Public bus/device/function getters do not establish the provider's PCI segment. Production BDF lookup therefore returns `NV_ERR_NOT_SUPPORTED` with a null handle and invalid vendor/device sentinels. The adapter does not reinterpret Apple's `domain-id` as a PCI segment or assume segment zero. Explicit native fixture metadata exercises the eventual verified-segment selection path; it is not hardware evidence.

The future exact C bridge can route the pinned NVIDIA read hooks to `readByte`, `readWord` and `readDword`, and `os_pci_init_handle` to `lookup`, after the selected RM caller contract is ready. No duplicate C exports are introduced here. Original NVIDIA value-returning PCI wrappers ignore hook status, so the startup boundary must handle backend failures and unsupported lookup explicitly before adopting that bridge.

Configuration writes, BAR resizing/mapping, bus-master changes, resets, interrupts, firmware, device DMA and GPU initialization are outside this component.

## Combined startup check

`S540NvidiaRmPci::check(IOPCIDevice *)` runs 20 checks under its own framework arbitration scope and returns component flags for session creation, reads, handles, lifecycle and cleanup. It checks identity through all three access widths, makes one aligned PCI extended-configuration read at `0x100`, verifies refusals and unknown-segment lookup, then stops the session and verifies stale-handle rejection. No worker threads, fault injection or interrupt registration are used in this kernel sequence.

The native `check()` uses an explicit backend fixture and the same production sequence. Its extra provider-reference assertion replaces the kernel arbitration assertion, so both successful paths contain 20 checks.

The native harness adds backend failures, wrong identities, missing metadata, stale/foreign handles, object-storage reuse, 4,000 concurrent reads, a blocked-read/stop race and 16 concurrent-double-stop/restart rounds. Its 252 checks pass plain and with fatal AddressSanitizer/UndefinedBehaviorSanitizer. Native results do not establish kernel contention behavior or actual PCI device responses. Retention and all native provider references balance on exit.

## Primary references

The authored adapter and pinned ABI/API references are listed in [PROVENANCE.json](PROVENANCE.json). No upstream NVIDIA function body is copied or represented as an initialized RM implementation.

- [NVIDIA OS PCI declarations](https://github.com/NVIDIA/open-gpu-kernel-modules/blob/1a82fbfda8f321b056eb3568850f9316c5e465c5/src/nvidia/arch/nvalloc/unix/include/os-interface.h), declarations 102–108.
- [NVIDIA Linux PCI implementation](https://github.com/NVIDIA/open-gpu-kernel-modules/blob/1a82fbfda8f321b056eb3568850f9316c5e465c5/kernel-open/nvidia/os-pci.c), reference for opaque handles and the 4 KiB interface.
- [Pinned MacKernelSDK PCI header](https://github.com/acidanthera/MacKernelSDK/blob/3f750085caa17ec3a7880f11c11bf4f48cd6a164/Headers/IOKit/pci/IOPCIDevice.h), public read wrappers and BDF getters.
- [Apple PCI implementation](https://github.com/apple-oss-distributions/IOPCIFamily/blob/4822b27a36e2de70e231ecf2bf3021384fab6ec2/IOPCIDevice.cpp), aligned configuration access, public BDF getters and provider-state checks.
- [Pinned IOLock header](https://github.com/acidanthera/MacKernelSDK/blob/3f750085caa17ec3a7880f11c11bf4f48cd6a164/Headers/IOKit/IOLocks.h), ordinary-thread mutual exclusion and sleep/wakeup.
- [XNU IOService implementation](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/iokit/Kernel/IOService.cpp), recursive arbitration, possible waiting and ownership checks.
- [Apple IOPCIFamily exports](https://github.com/apple-oss-distributions/IOPCIFamily/blob/4822b27a36e2de70e231ecf2bf3021384fab6ec2/config/IOPCIFamily.exports) and [XNU IOKit exports](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/config/IOKit.exports).
