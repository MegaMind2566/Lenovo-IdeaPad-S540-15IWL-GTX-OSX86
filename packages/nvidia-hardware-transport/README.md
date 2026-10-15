# NVIDIA hardware-transport preparation

This component implements the combined v8 preparation block for the S540's NVIDIA GTX 1650 Max-Q (`10DE:1F91`, subsystem `17AA:3806`, revision `A1`). It is delivered inside **S540-nvidia-transport-v8**, version `0.8.0`, report format `8`. A successful result is `transport_prepared`.

**Confirmed kernel checkpoint:** version `0.8.0` returned `transport_prepared` on the laptop with all 390 combined checks passed: 258 CPU and 132 preparation. Cleanup is complete, the verified provider and two-read TU117 variant-41 match are retained, and there are no warnings. [Native Intel CI](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/actions/runs/38752519794) and compiled-package verification also passed. No additional laptop test is requested for this completed checkpoint.

## Combined scope

| Area | Implemented preparation | Boundary |
|---|---|---|
| Host DMA memory | Wired 64 KiB IOBufferMemoryDescriptor, explicit mapper selection, IODMACommand attachment/preparation, bounded segment walk, CPU pattern verification, completion and release | No buffer address or transfer is submitted to the GPU; device DMA is unverified |
| PCI read adapter | Exact NVIDIA byte/word/dword read signatures, authenticated borrowed context, bounded aligned standard-configuration reads and cleared outputs on failure | No configuration writes, resource reassignment or bus-master changes |
| Interrupt capability inventory | Bounded PM/MSI/MSI-X walk, duplicate/loop/overlap checks, vector metadata and MSI-X table/PBA geometry against published BAR descriptors | No interrupt handler, registration, enable, acknowledgement or delivery check |
| Firmware preflight | Pinned hardened ELF64 parser, required release/section checks, SHA256 and checked buffer/page-table layout | Synthetic fixtures only; no real image or approved hash is bundled |
| RPC and deadlines | Plain MCTP/NVDM/RPC framing, lengths, sequences, stale-message rejection, cancellation and deadline state | CPU state only; no live GSP queue or GPU wait |
| Integration and cleanup | One shared startup lease, component results, failure injection and resource accounting | No RM/HAL construction, GSP startup or GPU initialization |

The production entry point is `S540NvidiaHardwareRuntime::checkIntegrated`. It retains the existing 23 foundation, 35 caller/reserve, 72 lifecycle and 128 support checks under the same startup lease, then runs the new preparation callback before releasing CPU state. The probe retains exactly one BOOT_0 and one BOOT_42 identification load. No additional MMIO read or write is introduced by this component.

## Host DMA contract

The buffer is wired host memory, with 4 KiB maximum segments and a maximum of 32 segment entries. The state machine explicitly prepares the descriptor and command, validates complete segment coverage, checks the CPU buffer pattern, completes the command and descriptor, clears the attachment and releases every owned object.

Mapper selection avoids the potentially unbounded device-mapper resolution path. An already-published provider IOMapper is retained and used. An unresolved or incompatible `iommu-parent` property is refused. If no mapper property is present, the command uses explicit untranslated preparation and reports `direct_untranslated`. This mode does not prove that an IOMMU is absent, that the GPU accepts the resulting addresses, or that a device transfer would succeed. Null-mapper mapped operation and implicit mapper fallback are excluded from this bounded profile.

Preparation, completion, clear and descriptor-completion failures retain distinct reasons. Cleanup does not silently retry a failed operation. DMA resource addresses are not included in preparation metadata.

## PCI and interrupt contract

The adapter implements the pinned NVIDIA `os_pci_read_byte`, `os_pci_read_word` and `os_pci_read_dword` ABI. A single active borrowed context authenticates the handle before provider access. The caller supplies the shared lease and provider arbitration; native CI substitutes an explicit standard-configuration fixture.

The capability walk remains within the 256-byte standard PCI configuration space. PM, MSI and MSI-X capabilities are checked for malformed ranges, loops, duplicate singleton entries and overlap. BAR validation distinguishes 32-bit and 64-bit memory, upper words and invalid/I/O encodings. MSI-X table and pending-bit-array geometry must fit the matching published memory descriptor; no BAR mapping is required for these checks.

The report records capabilities, advertised vector counts and observed MSI/MSI-X enable bits. An observed enabled bit is firmware/provider state, not evidence that this probe enabled interrupts. `interrupts_enabled` remains false for actions by this implementation.

## Firmware and RPC contract

The [firmware implementation](firmware/README.md) pins eleven NVIDIA source references at `1a82fbfda8f321b056eb3568850f9316c5e465c5`, release `615.78.08`. The hardened parser checks little-endian ELF64 structure, checked ranges, alignment, overlaps, exact firmware version and the required image, TU11x signature and GNU build-id sections. Successfully parsing an image does not authenticate a signature.

SHA256 hashes actual bytes and has standard-vector coverage. Firmware assets and the approved-hash list are empty. A valid synthetic image is explicitly rejected by the real-image readiness gate. The layout planner emits sizes and offsets only. RPC checks cover one plain single-packet envelope, its release-pinned headers, exact sequence/length rules and a bounded CPU request window. Deadline checks do not wait for a device.

## Validation implemented for the combined build

[Native Intel CI](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/actions/runs/38752519794) passed these suites, plain and with fatal AddressSanitizer/UndefinedBehaviorSanitizer. The extension was not loaded in CI.

| Suite | Coverage |
|---|---|
| DMA native harness | 309 checks, 21 fault cases, three cleanup-status cases and 64 startup/cleanup cycles |
| PCI native harness | 172 checks across read ABI, capability structure, BAR type and MSI-X geometry |
| Firmware native harness | 349 checks, including malformed/truncated inputs and SHA256 vectors; 89 production startup self-checks |
| Firmware provenance | Seven checks over pinned references and empty real-image approval state |
| Aggregate failure harness | 47 checks, seven cross-stage fault cases and four workers with eight mixed v7/v8 attempts each |
| Production aggregate | 258 CPU regressions and 131 native preparation checks, with cold-state and resource-release accounting |

The verified build source is `70f798c2269cff5dd3e50546afe7ffe713e2c6ac`. Kernel compilation/linking, signatures, the unchanged 24 CPU imports and 11 additional reviewed SDK imports passed. All 535 reporter checks passed. The aggregate failure harness covered seven cross-stage faults; its 32 mixed startup attempts completed eight and correctly refused 24, plain and sanitized. The downloaded 639,644-byte ZIP, all 195 files and 176 embedded source hashes were verified. ZIP SHA256: `5218be643594d60a050d59d1c856d39b82d1836fd0534d7a1159fa58a139c776`. Native userspace simulation does not validate kernel DMA mappings, actual interrupt delivery or GPU responses. CI does not load the extension.

## Completed laptop checkpoint

The format-8 laptop report confirms version `0.8.0`, `transport_prepared`, `complete=true`, no warnings and a null reason. All 390 kernel startup checks passed: the existing 258 CPU checks and 132 preparation checks, with every component and cleanup result true. The extra preparation check compared with the 131-check native path is the kernel provider-arbitration guard. The exact PCI provider identity is verified, and the same two read-only identification loads select TU117 variant 41.

Host preparation reports `direct_untranslated`, 65,536 bytes, 16 segments and reason `none`. PCI inventory reports three capabilities, one MSI vector and zero MSI-X vectors; both observed enable bits are false. Untranslated preparation does not prove device DMA compatibility or absence of an IOMMU. All six later-activity fields remain false: device DMA verified, firmware image verified, firmware loaded, interrupts enabled, GPU initialized and RM initialized.

The [transport package guide](../nvidia-transport/README.md) retains the compiled package, existing OpenCore entry, 240 GB test EFI and Samsung fallback procedure for reproduction. The combined checkpoint is complete; no separate DMA, PCI, firmware or repeated v8 laptop test is required.

Format 8 contains 25 preparation metadata fields, including component status, DMA mode/size/segments, PCI inventory, observed interrupt state and finite failure reasons. Successful host preparation does not override the mandatory false fields for device DMA verification, real firmware verification/loading, interrupt enabling, GPU initialization and RM initialization.

## Next integration work

The working estimate after v8 is three broad blocks: actual selected RM startup and remaining macOS services; device DMA/interrupt handling and matching real GSP firmware; then the first bounded GPU/GSP initialization attempt with observable failure or response. Dependencies may change this grouping; it is not a promise of three releases. Minimal command execution and graphics integration remain subsequent milestones.
