# Lenovo IdeaPad S540-15IWL GTX — macOS Tahoe

An OpenCore project for **macOS Tahoe 26** on the Lenovo IdeaPad S540-15IWL GTX. The goal is to improve hardware support while keeping configuration, driver patches, and recovery procedures organized and reproducible.

Tahoe boots directly from the external Samsung 960 EVO, with Intel graphics acceleration, audio, Wi-Fi, Bluetooth headphone audio, and the webcam. Development continues on the remaining hardware features.

## Hardware

| Component | Model |
|---|---|
| Laptop | Lenovo IdeaPad S540-15IWL GTX, **81SW** |
| CPU / memory | Intel Core i7-8565U / 12 GB DDR4 |
| Graphics | Intel UHD 620 / NVIDIA GTX 1650 Max-Q 4 GB |
| Display | Internal 1920×1080 panel |
| Audio | Realtek ALC257 |
| Wireless | Intel AC9560 Wi-Fi and Bluetooth |
| Touchpad | ELAN0662 I2C |
| macOS storage | External Samsung 960 EVO over USB-C |
| Windows storage | Internal Samsung PM981a |

## Compatibility

Current status as of **October 19, 2026**. **Pending** means the feature has not yet been established as working or not working.

| Feature | Status | Details |
|---|---|---|
| macOS boot and desktop | Working | Tahoe and OpenCore on the external 960 EVO; independent SSD boot confirmed |
| Intel graphics acceleration | Working | IntelAccelerator, Metal 3, up to 1536 MB shared graphics memory |
| Internal display | Working | Full HD resolution; startup black-screen delay corrected |
| Brightness slider | Deferred regression | Works with the non-NVIDIA EFI; unavailable with a disabled slider in the NVIDIA-test EFI. Differing cause not isolated; work deferred |
| Audio playback and controls | Working | VoodooHDA, F1–F3 and jack switching; quiet-volume correction confirmed during YouTube playback |
| Wired headphone output and switching | Working | Jack output works; speakers mute on connection and resume after unplugging |
| Wired headset microphone | Working | Microphone input through the 3.5 mm combo jack |
| Internal microphone | Working | S540 microphone correction v2 |
| Wi-Fi through HeliPort | Retained fallback | Previous itlwm configuration worked, including reconnection and network switching; the current connection uses native AirportItlwm |
| Bluetooth headphone audio and microphone | Working | Playback, headset voice capture, disconnection and reconnection confirmed |
| Webcam | Working | Image capture confirmed alongside the internal microphone |
| CPU power management | Working | X86PlatformPlugin active; frequency and estimated package power respond to activity |
| CPU temperature telemetry | Working | Readings retained at idle and during desktop activity; fan RPM remains unavailable |
| Battery detection and battery power | Working | Internal battery recognized; discharge reported after AC removal |
| External SSD access | Working | Samsung 960 EVO in a USB-C enclosure |
| USB-C SuperSpeed and connector orientation | Working | Samsung/RTL9210 at 5 Gb/s in both laptop-side connector orientations with the current cable |
| USB-A SuperSpeed and file access | Working | Same Initio enclosure at 5 Gb/s; files open on both tested USB-A connectors |
| F11/F12 brightness keys | Deferred regression | Brightness control works with the non-NVIDIA EFI; the NVIDIA-test EFI has a deferred adjustment regression |
| F6 touchpad toggle | Working | Direct key enables and disables the touchpad |
| Fn function row | Configured | Ordinary F1–F12 events recorded; four conflicting macOS shortcuts disabled, session refresh confirmation pending |
| Touchpad and gestures | Working | ELAN0662 gestures confirmed in daily use; F6 toggle also works |
| NVIDIA PCI attachment | Working diagnostic | Probe 0.1.0 attaches to `10DE:1F91`, verifies subsystem `17AA:3806`, reads fixed PCI configuration and assigned resource metadata; no GPU initialization or acceleration |
| NVIDIA BAR0 identification | Working diagnostic | Probe 0.2.0 completed one read-only `NV_PMC_BOOT_0` read with the expected TU117 fields; no GPU initialization or acceleration |
| NVIDIA HAL table match | Working diagnostic | Version 0.3.0 completed two read-only identification loads and a pinned local TU117 variant-41 table match; no HAL object or GPU initialization |
| NVIDIA OS-adapter startup | Working diagnostic | Version 0.4.0 passed the integrated kernel startup check for clocks, ordinary RAM, atomics, allocation and thread mutexes; no GPU initialization |
| NVIDIA original-caller startup | Working diagnostic | Version 0.5.0 passed 35 original-caller/reserve checks and 23 foundation checks in the Tahoe kernel; two-read TU117 identification retained |
| NVIDIA tracked memory and object lifecycle | Working diagnostic | Version 0.6.0 passed 72 lifecycle, 35 caller/reserve and 23 foundation checks in the Tahoe kernel, including cleanup; no warnings or GPU initialization |
| NVIDIA CPU support runtime and RM library consumers | Working diagnostic | Version 0.7.0 passed all 258 combined startup checks in the Tahoe kernel: 128 support, 72 lifecycle, 35 caller/reserve and 23 foundations; cleanup complete and no warnings |
| NVIDIA hardware-transport preparation | Working diagnostic | Version 0.8.0 passed all 390 combined kernel startup checks: 258 CPU and 132 preparation; cleanup complete, two-read TU117 match retained and no warnings. Device DMA and GPU initialization remain unimplemented |
| NVIDIA Resource Server and host services | Working diagnostic | Version 0.9.0 passed 486 kernel startup checks (258 CPU, 132 hardware and 96 services), all cleanup and 15 separate userspace firmware checks; no warnings. Full RM and GPU initialization remain false |
| Remaining icon keys | Pending | Microphone, refresh, airplane mode, camera, lock and display actions; further icon-key investigation deferred |
| USB-C video | Pending | No video test available; hardware video capability and routing remain unverified |
| USB 2 device coverage / storage reliability | Pending | External USB 2 devices, measured throughput and sustained reliability |
| SD reader / fingerprint reader | Pending | Driver support and device operation |
| Battery runtime / sleep and wake | Pending | Measured runtime and device recovery; basic battery power is confirmed |
| NVIDIA electrical power-off | Pending | Deferred until after the driver-port attempt; PCI visibility does not establish electrical power state |
| NVIDIA acceleration | Not working | GTX 1650 Max-Q has no supported driver in this configuration |
| Native macOS Wi-Fi interface | Working basic functions | [AC9560 Tahoe integration](packages/wifi-native/README.md): test EFI on the external 240 GB disk: native menu/settings, network visibility, connection and browsing confirmed by the user; reboot reconnection and Wi-Fi recovery after sleep also reported working. Service renamed from Ethernet to Wi-Fi |
| HDMI output | Not working | No image or external display in the macOS report; physical GPU routing under investigation |

Detailed hardware information is in [Hardware](docs/status/hardware.md).

## Operating configuration

macOS and OpenCore use the external Samsung 960 EVO. Independent boot is confirmed after manually copying the current private EFI from the 240 GB HDD. The HDD remains available as a recovery route; Windows remains on the internal PM981a.

NVIDIA probe 0.1.0 is confirmed to attach to the GTX 1650 Max-Q and read its fixed PCI configuration and assigned resource descriptors. Version 0.2.0 is also confirmed on the laptop: exactly one guarded read of the BAR0 identification register returned the expected TU117 fields. Version 0.3.0 subsequently completed two read-only identification loads and a local pinned-table match for TU117 variant 41. Version 0.4.0 then returned `integrated_passed` on the laptop. Version 0.5.0 also returned `integrated_passed`, confirming all 35 original-caller/reserve checks and 23 foundation checks in the Tahoe kernel while retaining the same two-register TU117 identification. Version 0.6.0 then confirmed all 72 lifecycle, 35 caller/reserve and 23 foundation checks in the Tahoe kernel, including cleanup, with no warnings and the same two-read TU117 match. Version 0.7.0 subsequently confirmed all 128 support-runtime checks alongside the existing 130, with complete cleanup and no warnings. These are diagnostic milestones; NVIDIA's HAL is not instantiated, and global/GPU RM initialization and graphics acceleration remain unimplemented. The selected standalone Resource Server is confirmed in the v9 kernel checkpoint. Intel remains the operating display GPU; the reports do not audit the full current EFI.

Brightness works normally when booting the non-NVIDIA EFI. With the NVIDIA-test EFI, adjustment is unavailable and the system slider is disabled, while Intel acceleration and the internal panel remain active. The responsible configuration difference or probe behavior has not been isolated. Keep the working non-NVIDIA EFI; investigation is deferred by request, with no additional test requested.

Audio uses a VoodooHDA extension installed in `/Library/Extensions`, including the S540 microphone correction. The EFI alone does not install this extension. The audio guides document the existing installation and upgrade procedures; those helpers require their original rollback state.

## Development priorities

The next integrated milestone now includes **global RM, operational device transport and actual GSP/adapter initialization together**. Its [development sources](packages/nvidia-gsp-bootstrap/README.md) include original-header lifecycle calls, verified immutable firmware delivery and observation of the original decoded GSP-init response. This is development work, without a new installable package or a confirmed GPU boot. The combined development control now passes all 148 allocation-failure positions. Full operational OS callback coverage, compiled kernel stack policy, platform power ownership and native validation of the adapted RM lifecycle remain gates. The first GPU command follows successful initialization; no repeat v9 laptop test is requested.

Development is grouped into complete integration milestones. The completed v7 bundle covers the selected NVIDIA CPU-runtime dependencies, allocation and synchronization contracts, startup, failure cleanup and one combined reporter. Component implementation, fault tests, stress checks and packaging run in GitHub before any laptop checkpoint. One package and one combined boot/report cover a completed bundle; individual wrappers and library additions do not trigger separate laptop tests. The confirmed v7 checks remain regression coverage within later packages, with no separate rerun. See the [bundled milestone scope](docs/status/roadmap.md#bundled-nvidia-development).

- Continue global RM and device/GPU integration from the confirmed [v9 Resource Server and host-services checkpoint](packages/nvidia-rm-services/README.md). All 486 kernel startup checks, cleanup and 15 separate userspace firmware checks passed, with no warnings. This checkpoint is complete; no repeat laptop test is requested. Full global RM, device DMA, interrupt delivery, firmware loading and GPU initialization remain open. Brightness adjustment has a deferred regression specific to the NVIDIA-test EFI; it works with the non-NVIDIA EFI, and the responsible difference remains unisolated.
- Complete storage reliability and remaining USB 2 device checks. Both USB-A connectors and USB-C in both orientations negotiate 5 Gb/s with the tested hardware. Audio peripherals, battery power and independent SSD boot work; measured battery runtime remains open.
- Complete Intel stability and power-management coverage; sustained cooling and fan telemetry remain open. External-display work is paused.
- Complete remaining device support and investigate connection performance from the recorded Internet baseline; wired/Bluetooth microphones, headphone switching and wireless reconnection work.
- Retain the working keyboard controls; remaining icon actions, equalization and sleep refinements are deferred.
- Retain the working [native AC9560 Wi-Fi integration](packages/wifi-native/README.md). Basic native operation, reboot reconnection and Wi-Fi recovery after sleep are user-confirmed; measured performance and long-term reliability remain separate. NVIDIA electrical power-off remains deferred until after the driver-port attempt.

See the [Roadmap](docs/status/roadmap.md) for the implementation plan.

## Documentation and downloads

The last verified [native Intel macOS development build](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/actions/runs/39169319480) used source `d81b19845bf31bca61464e198bdc883790af05bc`. Both unchanged and seven-overlay checked profiles compiled all 1,100 RM units with their private namespace; original-header bridges used the same checked headers. The compiled-bridge kernel dependency control passed. All 25 project bridge units compiled with matched platform imports. Its 1,594 CPU/contract checks passed in each plain and fatal-sanitized variant. These are source and CPU checks; kernel RM, physical device transport and GSP startup remain unconfirmed.

Current development adds a persistent [bootstrap owner](packages/nvidia-gsp-bootstrap/README.md), bound-device no-bounce DMA-remap policy and two-phase context cleanup. The owner assembles real context, transport, immutable firmware copies and timers, retaining them through failed cleanup and retry. Transport (307), context lifecycle (24) and bootstrap ownership (43) checks passed natively on Intel macOS, plain and with fatal address, undefined-behavior and function-type sanitizers. The exact DMA-remap ABI also compiled against the pinned original header. The actual compiled closure now recognizes that callback as provided; 132 other reviewed callbacks remain unimplemented. Its initialization entry explicitly refuses while complete callback coverage, aggregate stack policy, power lifetime and RM allocation retirement under active interrupts remain open. No new installable package or laptop test is offered.

The **S540-nvidia-transport-v9** package is confirmed in the Tahoe kernel: version `0.9.0`, report format `9`, `resource_server_prepared`, all 486 startup checks passed (258 CPU, 132 hardware and 96 services), cleanup complete and no warnings. All 15 separate userspace firmware-asset checks passed; the exact provider and two-read TU117 variant-41 match are retained. It integrates the selected original `RS_STANDALONE`/NVOC Resource Server subsystem; it does not execute full `coreInitializeRm()` or initialize global/GPU RM. A strict 16-field `RmServices` kernel result is separate from userspace `firmware_assets` byte verification. The official release `615.78.08` GSP/UCODES pair has been acquired, hashed and parsed with its complete NVIDIA license preserved; it is not loaded or executed. `FullRmInitialized` and the six existing kernel device-activity fields remain false. Native CI, compiled-package verification and the combined laptop checkpoint passed; no repeat laptop test is requested. Constructor unwind, lock matching and typed-iterator corrections are covered by the passing native checks.

The v9 [native Intel build](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/actions/runs/38778926403) passed from source `c477895c45507139ec9ea8e7536d70d49088f333`. The production aggregate passed 485 native checks: 258 CPU, 131 preparation and 96 services (45 Resource Server, 24 memory, 20 PCI and seven integration gates), plain and with fatal address, undefined-behavior and function-type sanitizers. Memory (166), PCI (252), Resource Server backend (134), allocation pressure (598), aggregate failure (33) and reporter (670) checks passed. Kernel compilation/linking and signatures passed; all 21 services platform imports matched the audited reference, including 14 new imports and seven existing CPU imports. The actual two firmware files and complete license bytes were verified. The 17,994,306-byte ZIP, all 347 files and 321 embedded source hashes were verified. ZIP SHA256: `e70ed12220fae374670b4dcf291769f9a70900d1d42d11fe7457a4c5dc7f619d`. CI did not load the extension. The subsequent laptop report confirms 486 kernel checks; the one-check difference from the 485 native checks is the kernel provider-arbitration check.

The **S540-nvidia-transport-v8** compiled package is confirmed in the Tahoe kernel: version `0.8.0`, report format `8`, `transport_prepared`, all 390 checks passed, cleanup complete and no warnings. Its [hardware-transport component](packages/nvidia-hardware-transport/README.md) combines the existing 258 CPU checks and 132 preparation checks; the extra check over the native preparation path is the provider-arbitration guard. Host memory is `direct_untranslated`, 65,536 bytes in 16 segments. PCI inventory records three capabilities, one MSI vector, no MSI-X vectors and neither observed enable bit set. This is host preparation, without proof of device DMA or IOMMU absence. The v8 package includes no approved real firmware image or firmware load, no interrupt handler is registered, and GPU/RM initialization remains false. The same two-read TU117 variant-41 match is retained. The [package guide](packages/nvidia-transport/README.md) retains reproduction and rollback instructions; this checkpoint is complete and requires no additional laptop test.

The v8 build source is `70f798c2269cff5dd3e50546afe7ffe713e2c6ac`. Native startup passed all 258 CPU regressions and 131 preparation checks; DMA (309), PCI (172), firmware (349), provenance (7), aggregate failure (47) and reporter (535) checks passed. The aggregate run exercised seven cross-stage faults and 32 mixed startup attempts, with eight completed and 24 correctly refused under the shared lease, plain and sanitized. Kernel compilation/linking, signatures, the unchanged 24 CPU imports and 11 additional reviewed SDK imports passed. The 639,644-byte ZIP, all 195 files and 176 embedded source hashes were verified. ZIP SHA256: `5218be643594d60a050d59d1c856d39b82d1836fd0534d7a1159fa58a139c776`. CI did not load the extension. The subsequent laptop report completed the 390-check kernel checkpoint.

The CPU-only OS adapter contains clock, ordinary-RAM and atomic foundations. [Combined GitHub validation passed](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/actions/runs/38696607911), including kernel-object linking and native userspace execution. The v0.4.0 integrated package adds ordinary host-RAM allocation and thread mutexes for a single laptop startup check. The v4 laptop report returned `integrated_passed`. The v5 report subsequently confirmed the foundations with the new reserve/mutex backends and all eight original allocation/mutex callers. The v6 report subsequently confirmed the combined lifecycle block with all 130 startup checks, including cleanup. Concurrent kernel execution and full NVIDIA caller compatibility remain unvalidated.

The [documentation index](docs/README.md) links to setup, maintenance, and recovery procedures. Main guides: [Intel graphics](docs/guides/intel-graphics.md), [Tahoe audio](docs/guides/tahoe-audio.md), and [microphone correction](docs/guides/microphone-fix.md).

Download the [first EFI release, v0.1.0](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/releases/tag/v0.1.0), with compatibility notes and setup instructions. Personalize its SMBIOS identity before use.

Generated packages are available in **Artifacts** from successful [GitHub Actions runs](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/actions). Current companion packages are `S540-microfono-fix-v2`, `S540-volume-fine-v1` and `S540-brightness-keys-v2`. The [function-key guide](docs/guides/function-keys.md) records the complete keyboard mapping and remaining work.

The **S540-nvidia-transport-v5** compiled package passed its [native Intel build and checks](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/actions/runs/38726407067) from source `81c1529a31fcc1b61fa3a466442e73fef0fc3aa9`. Its shared startup sequence passed 23 foundation checks and 35 original-caller/reserve checks, both plain and with sanitizers. The archive and every contained file checksum were verified. The format-5 laptop report confirms version 0.5.0: `integrated_passed`, all 35 caller/reserve checks and 23 foundation checks passed, exact provider identity verified, TU117 variant 41 matched, and no warnings. This milestone is complete. The [package guide](packages/nvidia-transport/README.md) retains installation and rollback instructions. No HAL object, resource manager, initialized GPU or acceleration is provided.

The **S540-nvidia-transport-v6** compiled package passed its [native Intel build and checks](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/actions/runs/38732985934) from source `a6f6555624b4395454045bbce710c08cf7b6309e`. Its [lifecycle component](packages/nvidia-nvport-lifecycle/README.md) combines 31 memory functions and 11 synchronization functions: 41 unchanged NVIDIA bodies and one explicit checked-bootstrap adaptation. The production startup passed 72 lifecycle checks, 35 caller/reserve checks and 23 foundation checks, plain and with fatal sanitizers. Native failure/stress checks, 333 reporter decoder checks, kernel linking/imports and signatures passed. All 122 contained files and 106 source hashes were verified. ZIP SHA256: `fa593618c4174fd505b4f284ee244f1bad109067bf53f0f81565fecdae001891`. One shared lease covers v5 and v6; the two read-only GPU identification loads remain unchanged. The format-6 laptop report confirms version 0.6.0: `integrated_passed`, all 130 checks passed in the Tahoe kernel, cleanup complete, provider identity verified, TU117 variant 41 matched and no warnings. This combined checkpoint is complete; no repeat laptop test is required. Kernel contention, interrupt behavior, full resource-manager operation and acceleration remain unvalidated.

The **S540-nvidia-transport-v7** compiled package passed its [native Intel build](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/actions/runs/38740433010) from source `30e064dc5bc346e2d46a3fd5bc7ba26e58f9bed8`. It adds the [checked CPU support runtime and real RM library consumers](packages/nvidia-nvport-runtime/README.md): original strings/PRNG, selected unsigned utilities, vector/list operations and explicit empty-vector cleanup correction. The production entry point passed 258 startup checks (128 new support checks plus the existing 130), plain and with fatal sanitizers. Container coverage passed 15,283 checks, including 12 allocation-failure positions; failure/lease coverage and all 390 reporter checks passed. Kernel linking verified 120 C functions, three data symbols and the same 24 platform imports. All 163 files and 146 embedded source hashes were verified. ZIP SHA256: `a674e976125070351a9bc47f33f91b2d06d1f30fbd582935a58149596a1bda94`. The format-7 laptop report confirms version 0.7.0: `integrated_passed`, all 258 kernel startup checks passed, all four CPU blocks passed, cleanup complete, verified provider identity, the same two-read TU117 variant-41 match and no warnings. The combined checkpoint is complete; no repeat laptop test is required. Full RM construction and GPU initialization remain unimplemented.

**Code → Download ZIP downloads source code, without compiled payloads. It is not an installer.** Builders assemble the feature sources into distributable ZIPs with their own launchers and runtime layout.

## Repository layout

| Path | Purpose |
|---|---|
| [packages/](packages/) | Feature-specific launchers and runtime sources |
| [builders/](builders/) | Package build and assembly scripts |
| [tests/](tests/) | Validation tests and fixtures |
| [config/](config/) | ACPI, hardware profiles, pinned assets, and USB mapping |
| [docs/](docs/README.md) | Guides, hardware information, and roadmap |
| [patches/](patches) | Driver source patches |
| [licenses/](licenses) | Dependency licenses |
| [.github/workflows/](.github/workflows) | Automated builds and checks |
| [archive/](archive/README.md) | Superseded procedures and development history |

Machine-specific SMBIOS identifiers, Wi-Fi credentials, and original diagnostic reports are kept out of the repository. The S540 VoodooHDA variant is a project modification, not an official upstream release.
