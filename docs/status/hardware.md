# Verified hardware and official EFI status

Updated on **27 October 2026** for the current **internal non-NVIDIA EFI**, published as v0.3.0. The source laptop now boots macOS internally alongside native Windows. SD operation is user-confirmed after the internal update. **Official EFI status: Stable — known limitations.** The classification covers the tested Lenovo IdeaPad S540-15IWL GTX (81SW) running macOS Tahoe **26.7.1 (25G241)** with Intel UHD 620 and NVIDIA disabled. It applies to the confirmed functions and tested sleep/wake cycles; prolonged standby and hibernation remain unverified and deferred. Future macOS updates require validation. The project remains **in development**; the table separates working functions, accepted non-working features and unverified coverage.

## Current results

| Component | Verified result | Limit or remaining scope |
|---|---|---|
| Platform | Lenovo IdeaPad S540-15IWL GTX (81SW); i7-8565U, 4 cores / 8 threads; 12 GB DDR4-2400 | Public SMBIOS identity is sanitized; private identity is preserved locally |
| Board / firmware provenance | Lenovo LNVNB161216, BIOS BWCN19WW dated 26 May 2021; OEM ACPI retained | Historical inventory, not a new firmware check |
| Internal boot | macOS APFS and Windows coexist on the internal 512 GB Samsung PM981a; current non-NVIDIA OpenCore boots internally | Windows starts natively through the existing rEFInd route; its files are preserved |
| Intel graphics / panel | UHD 620 acceleration, Metal 3, BOE NV156FHM-N61 1920×1080; startup backlight corrected | Sustained graphics performance is not established by the inventory |
| Brightness | Slider and direct F11/F12 work in the official non-NVIDIA EFI | The separate NVIDIA-test regression does not change this result |
| Native Wi-Fi | Intel AC9560, tested AirportItlwm 2.4.0; native menu, connectivity and restart/sleep recovery confirmed | AirDrop and Continuity are not claimed |
| Bluetooth | Intel USB 8087:0AAA; headset playback and microphone, disconnection and reconnection confirmed, including after sleep/wake | Automatic versus manual reconnection was not specified |
| Audio | ALC257 through separately installed VoodooHDA 3.6.10; speakers, internal microphone, wired headphone output/input and switching work | Built-in speaker/microphone operation also confirmed after wake and Bluetooth disconnection; EFI alone does not install VoodooHDA |
| Webcam video | Integrated UVC 13D3:56B2; recorded video confirmed | F8 privacy/power toggle is a separate non-working function |
| Touchpad | ELAN0662 I2C input and gestures working; F6 enable/disable is user-confirmed | F6 reconfirmed on 27 October; no further toggle test is pending |
| Keyboard actions | F1–F3 audio and non-NVIDIA F11/F12 brightness work; F4 microphone input-level mute/restore, F7 Wi-Fi/Bluetooth and F9 lock confirmed with S540 Tasti 0.1.3 | F5 browser reload was user-confirmed; direct/Fn distinction remains separate. F6 touchpad toggle is reconfirmed working; F10 remains pending in the same workstream as HDMI. See [Function keys](../guides/function-keys.md) |
| F8 camera disablement | **NOT WORKING**: firmware flag changes but video capture continues, even after reopening Photo Booth | Further work paused by request; camera video itself works |
| USB | Active nine-port map (six HS / three SS); both tested USB-A connectors and USB-C in both orientations negotiated 5 Gb/s; file access confirmed | Tested devices/cables only; link speed is not sustained storage throughput |
| Internal NVMe | 512 GB detected, SMART verified, TRIM active | Not a sustained endurance/storage benchmark |
| CPU / battery | X86PlatformPlugin active; CPU response, battery reporting and discharge confirmed | Modest runtime attributed by the user to an aged battery; no autonomy repair inferred |
| Low Power Mode | Battery-on / AC-off setting retained; short OFF–ON–ON–OFF comparison shows about 11.4 W estimated package power and 2.4 GHz on versus 34.4–36.5 W and 3.89–4.00 GHz off | Not equal-work efficiency, whole-laptop power or measured autonomy; [test limits](battery-sleep.md#low-power-mode-under-cpu-load--24-october-2026) |
| Lid and idle sleep | One 3,603-second clamshell sleep and one 91-second idle sleep resumed, with no recorded DarkWake in those cycles | Prolonged sleep/overnight standby and hibernation remain unverified and deferred by request; not every peripheral's recovery was tested |
| **SD reader** | **Working on the source laptop from the updated internal non-NVIDIA EFI**, user-confirmed 24 October; O2Micro 1217:8621, previous direct-match BigSurSDXC 1.9.0, known 8 GB FAT32 card | Earlier negative result retained as history; insertion during an active session, mounting/unmounting and availability after sleep confirmed; writes, throughput and arbitrary capacities not newly validated. Operation was reconfirmed on 27 October; no further SD checks are pending for this milestone. [Evidence](sd-fingerprint.md#current-internal-efi-result--24-october-2026) |
| Fingerprint | **NOT WORKING in macOS**: Goodix 27c6:55b4 enumerates on internal HS02, but authentication is unavailable | Investigation stopped by request; [retained findings](sd-fingerprint.md) |
| NVIDIA acceleration | **Unavailable and disabled in this release** with -wegnoegpu; no experimental NVIDIA payloads included | Separate experimental research and historical checkpoints remain outside this EFI |
| HDMI / F10 | **Open as one linked workstream**; HDMI has no usable display output established and F10 remains pending | Physical routing/driver support and the intended display-mode action remain unresolved |
| USB-C video | **Not supported natively by the laptop** | Native USB-C video is a hardware limitation; USB data transfer works. No EFI video fix is pending for this port |
| Fans | **Working — user-confirmed**; RPM telemetry is unavailable in the current macOS configuration | VirtualSMC and SMCProcessor 1.3.8 expose CPU temperatures but no fan RPM. Investigation is closed for this release by request; no driver/control change was made |

## Passive fan-telemetry check — 24 October 2026

Before publication, the user supplied a native check on macOS 26.7.1 / 25G241 with the internal non-NVIDIA boot arguments retained. VirtualSMC 1.3.8 and SMCProcessor 1.3.8 were loaded. SMCSuperIO and YogaSMC were absent, and the SMCSuperIO IORegistry query was empty. Three working powermetrics SMC samples reported CPU temperatures of **58, 60 and 59 °C**, but no fan/RPM lines, with some invalid-key messages.

The passive result is **fan RPM telemetry unavailable in this configuration**; it is not a measured fan speed of zero. The user subsequently confirmed physical fan operation and accepted the status **fans working, RPM not readable by macOS**. Fan investigation is closed for this release, with no further firmware collection or laptop tests requested. No new driver, EC write or fan setting is included. The [historical investigation](../reference/s540-fan-sensors.md) retains the read-only findings and their limits.

## F8 result and decision — 24 October 2026

The target reports `CameraState=0` and `LastCameraResult=7` after F8, while the webcam remains usable after reopening Photo Booth. This confirms the key/firmware path, not a working video block. The webcam itself still captures video correctly. App 0.1.3 corrects the misleading success popup; it does not implement camera disablement. The user has accepted F8 as non-working and requested that further work stop. F4, F7 and F9 retain their confirmed working status.

## Current internal configuration and public release

The applied internal config preserves the Intel baseline, native Wi-Fi, USB, brightness, NVRAM and identity while adding only the reviewed SD entry/property and exact working SD bundle. OpenCore is **1.0.8 RELEASE**, NVIDIA remains disabled with `-wegnoegpu`, and `ScanPolicy=769` preserves the native Windows/rEFInd separation.

The SD installer copied and verified the config and driver before a final metadata comparison stopped. The user's recursive diff showed only the expected config/bundle changes and `OC/._config.plist`, leaving Windows, rEFInd and other pre-existing files unchanged. The user subsequently reported SD operation from the updated internal setup after an initial negative report. This later functional confirmation is the current result.

The v0.3.0 public package contains **EFI/OC only** with sanitized identity values and a rEFInd config example. It does not redistribute Microsoft boot files, the existing fallback EFI executable or rEFInd itself. Audio and hotkeys remain separately installed macOS companions. [Installation](../releases/v0.3.0/INSTALL.md) explains the boundary.

## Evidence and limits

The current status combines the user's functional confirmations with the 20 October hardware report, loaded-driver list and USB IORegistry capture. The report's 17 reader commands completed successfully. Raw reports, complete configurations, serials, network identifiers and volume names stay private.

The applied USB map contains **six HS and three SS entries**. Its `port-count` value of 15 is the highest hardware port index, not fifteen enabled entries. The connected Intel Bluetooth, webcam and fingerprint device are on internal type-255 ports. Current enumeration does not prove every empty port; the separate 14 October USB-A and reversed-USB-C observations provide the external connector coverage.

Historical USB results cover the tested enclosures and cables: the Samsung/Realtek RTL9210 system disk negotiated 5 Gb/s over USB-C in both orientations; an Initio enclosure negotiated 5 Gb/s on each USB-A connector, with file access confirmed. Link speed and USB power allocation are not storage throughput or measured laptop power. Fingerprint-device enumeration does not establish macOS fingerprint authentication.

The original Windows hardware report and OEM ACPI collection identify the board, BIOS, codec and device paths. They remain provenance for the hardware inventory; they do not replace macOS runtime evidence. The [boot/network record](../guides/boot-network.md), [battery/sleep record](battery-sleep.md) and [CPU record](cpu-thermal.md) distinguish current results from older measurements. The [exact Lenovo model specification](https://psref.lenovo.com/syspool/Sys/PDF/IdeaPad/ideapad_S540_15IWL_GTX/ideapad_S540_15IWL_GTX_Spec.pdf) does not declare DisplayPort Alt Mode; working USB-C data is not proof of USB-C video.

## Historical NVIDIA checkpoints — separate experimental work

The sections below retain the earlier development record unchanged. They concern separate NVIDIA test configurations, not the official non-NVIDIA EFI. These dated checkpoints do not establish graphics acceleration or redefine the state of newer experimental work. The release does not activate them or close the project.

## NVIDIA PCI visibility: October 15, 2026

The first native inventory returned `not_visible`, `complete=true`, `wegnoegpu_present=true` and no warnings. The automatic [visibility helper](../../packages/nvidia-visibility/README.md) subsequently stopped at its required `Mounted` metadata check before creating a candidate or changing EFI/NVRAM. The disable argument was then removed manually.

The latest reports agree on the following normalized evidence:

| Item | Observed result |
|---|---|
| Inventory | `found`, `complete=true`, no warnings |
| Disable argument | `wegnoegpu_present=false` |
| Active service | `IOPCIDevice`, `service_visible=true` |
| GPU | `10DE:1F91`, subsystem `17AA:3806`, revision `A1`, class `030000` |
| Topology | `GFX0@0` below `RP05@1C,4` through `IOPP` |
| Parent bridge | Intel `8086:9DBC`, class `060400` |

PCI visibility is therefore confirmed. The inventory reads published metadata; it does not open the device or verify PCI configuration-space access, MMIO, DMA, GSP, GPU execution, acceleration or electrical power state. It does not audit every current EFI setting or establish the physical routing of HDMI. Raw reports and private configurations remain outside the repository.

## NVIDIA PCI attachment: October 15, 2026

The laptop report from `nvidia-transport` 0.1.0 returns `attached`, `complete=true`, `wegnoegpu_present=false` and no warnings. The active probe is `S540NvidiaPCIProbe`, with an `IOPCIDevice` provider whose identity is verified as `10DE:1F91`, subsystem `17AA:3806`, revision `A1`, display class `030000`. This confirms kernel attachment and the bounded fixed PCI configuration-read milestone.

The snapshot retains these already-assigned resource descriptors:

| BAR register | Descriptor length |
|---|---|
| `0x10` | 16 MiB |
| `0x14` | 256 MiB |
| `0x1C` | 32 MiB |
| `0x24` | 128 bytes |

The snapshot has no descriptor at `0x18` or `0x20`. Raw BAR type/width flags were not collected, so those gaps are not diagnosed as missing resources. Resource descriptors do not demonstrate MMIO access or usable VRAM capacity. The probe does not change PCI command bits, enable bus mastering or allocate DMA; observed command/status values are not evidence of changes made by the probe.

The confirmed 0.1.0 result includes no GPU register read, GSP initialization, command execution or acceleration. The subsequent 0.2.0 register-read result is recorded separately below. Runtime stop/unload remains untested. NVIDIA electrical power-off and external-display work retain their deferred status. Raw reports, resource addresses and private EFI configuration stay outside the repository.

## NVIDIA single-read identification: October 15, 2026

The format-2 laptop report from `nvidia-transport` 0.2.0 returns `identified`, `complete=true`, `wegnoegpu_present=false` and no warnings. The actual `IOPCIDevice` provider identity is verified as `10DE:1F91`, subsystem `17AA:3806`, revision `A1`, class `030000`.

| Observation | Result |
|---|---|
| Register | `NV_PMC_BOOT_0`, BAR0 offset zero |
| Access | Exactly one read, 32 bits |
| Register value | `0x167000A1` |
| Decoded architecture / implementation | `0x16` / `0x07`, TU117 |
| Result reason | `tu117-identified` |

This confirms the one bounded identification-register read. It does not establish general MMIO access, GPU initialization, usable VRAM, DMA, firmware operation, command execution or acceleration. Runtime stop/unload and power-management transitions remain untested. This confirms the 0.2.0 milestone; the separate 0.3.0 result is recorded below.

## NVIDIA BOOT_42 and local HAL table match: October 15, 2026

The format-3 laptop report from `nvidia-transport` 0.3.0 returns `hal_matched`, `complete=true`, `wegnoegpu_present=false` and no warnings. The actual PCI provider identity is verified.

| Observation | BOOT_0 | BOOT_42 |
|---|---|---|
| Completed 32-bit reads | 1 | 1 |
| Register value | `0x167000A1` | `0x167A1000` |
| Decoded architecture / implementation | `0x16` / `0x07` | `0x16` / `0x07` |
| Decoded chip ID | Not used in this phase | `0x167` |

The result records two total loads and a local table match for TU117 variant index `41`, with NVIDIA source commit `1a82fbfda8f321b056eb3568850f9316c5e465c5`. It confirms only these two read-only identification loads and the pinned table match. No NVIDIA HAL object is instantiated, the resource manager is not integrated, and GPU initialization, firmware operation, DMA and acceleration remain unimplemented. Runtime stop/unload remains untested. The separate CPU-only Darwin OS adapter passed [combined kernel compile/link/import and native userspace checks](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/actions/runs/38696607911) for clocks, ordinary-RAM primitives and unchanged NVIDIA atomic-header integration. This adds no kernel runtime or GPU validation; operations over buffers larger than 4 GiB are not executed. The later integrated v4 laptop result is recorded below; full validation follows the implementation stages. Private resource addresses and raw reports remain excluded.

## NVIDIA integrated OS-adapter package: October 15, 2026

Version 0.4.0 adds ordinary host-RAM allocation and same-owner thread mutexes to the clock, RAM and original atomic foundations. [Native GitHub build and package checks passed](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/actions/runs/38717866330) from source `4f3ccfa8970c9fd6ae5d00197753883dcba484aa`. The actual integrated runtime passed 23 native checks; the reporter passed 219 decoder checks. Kernel compilation, linking, known-import auditing and signatures passed. The distributed archive checksum and every file checksum were verified.

The earlier returned format-4 laptop report records: version `0.4.0`, `integrated_passed`, `complete=true`, no warnings, and the actual PCI provider identity verified. `OSFoundations` records `passed`, 23 assertions, and true results for timer, memory, atomics, allocation and mutex. BOOT_0 and BOOT_42 each completed one read, retaining TU117 variant `41` and two total loads.

The startup check runs on one thread and uses small buffers, one 256-byte ordinary host-RAM allocation and one mutex, all released before the snapshot is published. It confirms execution of this check in the Tahoe kernel; it does not establish concurrent kernel behavior, interrupt-safe allocation, suspend/resume or full NVIDIA caller compatibility. The existing OpenCore entry was retained. NVIDIA HAL/RM, GPU initialization, firmware, DMA and acceleration remain unimplemented. No repeated laptop test is required for this checkpoint. Private resource addresses and raw reports remain excluded.

## NVIDIA original-caller kernel startup confirmed: October 15, 2026

Version 0.5.0 passed its [native Intel build and package checks](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/actions/runs/38726407067) from source `81c1529a31fcc1b61fa3a466442e73fef0fc3aa9`. It combines eight original NVIDIA allocation/mutex callers with a 4 MiB reserve, the new mutex backend and the existing foundations. The same startup entry point passed 35 caller/reserve checks and 23 foundation checks, both plain and under AddressSanitizer/UndefinedBehaviorSanitizer. The reporter passed 272 decoder checks; kernel compilation, 22-import auditing, 16 resolved caller/hook symbols and signatures passed. The two read-only TU117 identification loads are unchanged.

The distributed ZIP SHA256 is `eb110f82039ecc73f9cc89fc4b4a276947425b784c1fad833dd05a9a1771ea6b`. Its 99 contained files, including 84 source inputs, were checked against the package records. CI did not load the kernel extension.

The returned format-5 laptop report confirms version `0.5.0`, `integrated_passed`, `complete=true`, no warnings and the exact PCI provider identity. `OSFoundations` passed all 23 checks with timer, memory, atomics, allocation and mutex true. `CallerIntegration` passed all 35 checks with allocation callers, mutex callers and reserve true. BOOT_0 and BOOT_42 each completed one read; the pinned local HAL table matched TU117 variant `41` after two total loads.

This confirms the bounded sequential startup with the new backends and eight original NVIDIA callers in the real Tahoe kernel. The sequence creates no workers and does not intentionally enter a blocking mutex wait; kernel contention, interrupt-context allocation and suspend/wake remain unvalidated. GPU initialization, HAL/RM, firmware, DMA and acceleration remain unimplemented. No repeated laptop test is required for this milestone. Only this normalized result is retained publicly; raw reports and resource addresses remain private.

## NVIDIA v6 lifecycle confirmed: October 15, 2026

The [v6 lifecycle block](../../packages/nvidia-nvport-lifecycle/README.md), source `a6f6555624b4395454045bbce710c08cf7b6309e`, passed its [native Intel build and checks](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/actions/runs/38732985934). It combines tracked memory, real spinlocks, allocator-owned mutex lifecycle, checked bootstrap/failure cleanup and reserve/allocation/OS-object accounting under the shared v5 startup lease. The production sequence passed 72 lifecycle checks, 35 caller/reserve checks and 23 foundation checks, plain and with fatal AddressSanitizer/UndefinedBehaviorSanitizer. Native failure/stress checks and kernel compilation/import/signature checks passed; all 122 contained files and 106 source hashes were verified. CI did not load the extension.

The format-6 laptop report confirms version `0.6.0`, `integrated_passed` and `complete=true`. All 130 kernel startup checks passed: 72 lifecycle, 35 caller/reserve and 23 foundations. Every component passed, including cleanup. The actual PCI provider identity is verified as `10DE:1F91`, subsystem `17AA:3806`, revision `A1`, with `-wegnoegpu` absent. Exactly one BOOT_0 and one BOOT_42 read selected TU117 variant 41 from the pinned table. The report has no warnings and a null reason. Raw reports and resource addresses remain private.

This completes the combined v6 sequential kernel-startup checkpoint; no repeat laptop test is required. It does not establish kernel contention, interrupt behavior, runtime stop/unload or suspend/wake. The GPU policy remains exactly two read-only identification loads. HAL/RM, GPU initialization, firmware, DMA and graphics remain unimplemented.

## NVIDIA v7 combined CPU runtime confirmed: October 15, 2026

The [v7 CPU support runtime](../../packages/nvidia-nvport-runtime/README.md), source `30e064dc5bc346e2d46a3fd5bc7ba26e58f9bed8`, passed its [native Intel build](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/actions/runs/38740433010). It combines checked memory/PRNG initialization and reverse shutdown, original string and unsigned utilities, real vector/list consumers, failure cleanup and strict format-7 reporting. An explicit vector correction fixes old-buffer release when reallocating an empty allocated vector.

The production sequence passed 128 new support checks plus the existing 72 lifecycle, 35 caller/reserve and 23 foundation checks: 258 total, plain and with fatal AddressSanitizer/UndefinedBehaviorSanitizer. Native container coverage passed 15,283 checks, 12 allocation-failure positions and 64 cycles of 128 model-checked vector mutations. Native failure/lease coverage passed 60 checks and 48 mixed startup attempts; the observed run completed 12 and correctly refused 36 under the shared lease. All 390 reporter decoder checks passed. Kernel compilation/linking, the unchanged 24-import platform contract and signatures passed. The downloaded ZIP, all 163 contained files and 146 embedded source hashes were verified. ZIP SHA256: `a674e976125070351a9bc47f33f91b2d06d1f30fbd582935a58149596a1bda94`.

CI did not load the extension. The subsequent format-7 laptop report confirms version `0.7.0`, `integrated_passed` and `complete=true`. All 258 kernel startup checks passed: 128 support, 72 lifecycle, 35 caller/reserve and 23 foundations. Every component passed, including both cleanup results. The actual PCI provider is verified as `10DE:1F91`, subsystem `17AA:3806`, revision `A1`, with `-wegnoegpu` absent. Exactly one BOOT_0 and one BOOT_42 read selected TU117 variant 41 from the pinned source table. The report has no warnings and a null reason. Raw reports and resource addresses remain private.

This completes the combined v7 bounded sequential kernel-startup checkpoint; no repeat laptop test is required. Kernel contention, interrupt behavior, runtime unload and suspend/wake remain unvalidated. The result adds no GPU register access, RM/HAL construction, firmware, DMA or acceleration.

## NVIDIA v8 hardware-transport preparation confirmed: October 15, 2026

The format-8 laptop report confirms version `0.8.0`, `transport_prepared`, `complete=true`, no warnings and a null reason. All 390 kernel startup checks passed: the existing 258 CPU checks and 132 preparation checks, with every component and cleanup result true. The extra preparation check compared with the 131-check native path is the kernel provider-arbitration guard. The exact PCI provider identity is verified, and the same two read-only identification loads select TU117 variant 41.

Host preparation reports `direct_untranslated`, 65,536 bytes, 16 segments and reason `none`. PCI inventory reports three capabilities, one MSI vector and zero MSI-X vectors; both observed enable bits are false. Untranslated preparation does not prove device DMA compatibility or absence of an IOMMU. All six later-activity fields remain false: device DMA verified, firmware image verified, firmware loaded, interrupts enabled, GPU initialized and RM initialized.

The [combined component](../../packages/nvidia-hardware-transport/README.md) executes actual wired host-memory/IODMACommand preparation and cleanup, exact read-only PCI hooks and bounded PM/MSI/MSI-X inventory, plus synthetic firmware ELF64/SHA256/RPC/layout/deadline/cancellation checks. All components and the existing CPU regressions share one startup lease and one report. No real firmware image is approved or loaded; no interrupt handler, device DMA transfer, RM/HAL construction, GSP initialization or acceleration is included. Raw reports, resource addresses and private configurations remain outside the repository.

This combined v8 kernel-startup checkpoint is complete; no additional laptop test is requested for it. The next implementation block is the actual selected Resource Manager startup path and its missing Darwin services. Device DMA, interrupt delivery, real firmware loading and GPU/GSP initialization remain later integration work.

The [native Intel build](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/actions/runs/38752519794) passed from source `70f798c2269cff5dd3e50546afe7ffe713e2c6ac`: 258 CPU regressions and 131 native preparation checks, 535 reporter checks, kernel compilation/linking, signatures and the reviewed import contract. The aggregate run completed eight of 32 mixed attempts and correctly refused 24 under the lease, plain and sanitized. The 639,644-byte ZIP, all 195 files and 176 embedded source hashes were verified. ZIP SHA256: `5218be643594d60a050d59d1c856d39b82d1836fd0534d7a1159fa58a139c776`. CI did not load the kext; the separate laptop report recorded above completes the kernel checkpoint.

## NVIDIA v9 Resource Server and host-services confirmed: October 15, 2026

Version `0.9.0` / format `9` groups the original standalone NVOC Resource Server, cached host allocation/kernel mapping, retained read-only 4 KiB PCI sessions and official matching release `615.78.08` GSP/UCODES byte verification into one package. The confirmed combined success status is `resource_server_prepared`. Native macOS CI and compiled-package verification passed, including startup, constructor unwind, lock matching and typed-iterator checks. The format-9 laptop report confirms all 486 kernel startup checks passed (258 CPU, 132 hardware preparation and 96 services), complete cleanup, a null reason and no warnings. All 15 separate userspace firmware checks passed; the exact provider identity and two-read TU117 variant-41 match are retained. The v9 checkpoint is complete; no repeat laptop test is requested.

The selected original Resource Server exercises real client/resource lifecycle, access isolation, sharing and control/refusal paths. Host-memory implementation provides four exact allocation/free/kernel-mapping ABIs and explicit unsupported device-DMA results. Retained PCI sessions preserve provider lifetime and validate handles while reading only configuration space. The matching official firmware pair has been acquired, hashed and parsed with its complete NVIDIA license preserved, but these userspace byte checks do not execute inside the kernel or load firmware onto the GPU.

The strict 16-field `RmServices` kernel result and separate userspace `firmware_assets` evidence retain that distinction. `FullRmInitialized` and all six existing kernel device-activity flags remain false. No full `coreInitializeRm()`, global/GPU RM, interrupt delivery, device DMA transfer, firmware load or GPU initialization is claimed. Framework provider arbitration may wait; only the shared startup lease is nonblocking. Raw reports, addresses and private configurations remain excluded.

The v9 [verified build record](../../README.md#documentation-and-downloads) records source `c477895c45507139ec9ea8e7536d70d49088f333`, 485 passed native aggregate checks (258 CPU, 131 preparation and 96 services), the audited kernel import/link/signature checks and the verified 347-file archive. CI did not load the extension. The separate actual kernel result is 486 checks; the additional check over the 485 native aggregate is the kernel provider-arbitration check.

## Deferred brightness regression after the v9 checkpoint

Brightness works normally when booting the non-NVIDIA EFI. The NVIDIA-test EFI has unavailable adjustment and a disabled system slider. In that configuration, Intel UHD 620 (`3EA5`) still exposes Metal 3 and the internal Full HD main display is online. Lilu 1.7.2, WhateverGreen 1.7.1 and BrightnessKeys 1.0.3 are loaded, `-igfxblr` is present and AppleBacklightDisplay is active. This establishes a difference between EFI configurations; the responsible setting or probe behavior has not been isolated. The working non-NVIDIA EFI is retained. Investigation is deferred by request, with no additional tests, packages or patches.

