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

Current status as of **October 15, 2026**. **Pending** means the feature has not yet been established as working or not working.

| Feature | Status | Details |
|---|---|---|
| macOS boot and desktop | Working | Tahoe and OpenCore on the external 960 EVO; independent SSD boot confirmed |
| Intel graphics acceleration | Working | IntelAccelerator, Metal 3, up to 1536 MB shared graphics memory |
| Internal display | Working | Full HD resolution; startup black-screen delay corrected |
| Brightness slider | Working | Brightness control through macOS settings |
| Audio playback and controls | Working | VoodooHDA, F1–F3 and jack switching; quiet-volume correction confirmed during YouTube playback |
| Wired headphone output and switching | Working | Jack output works; speakers mute on connection and resume after unplugging |
| Wired headset microphone | Working | Microphone input through the 3.5 mm combo jack |
| Internal microphone | Working | S540 microphone correction v2 |
| Wi-Fi through HeliPort | Working | Intel AC9560 with itlwm; disconnection, reconnection and network switching confirmed |
| Bluetooth headphone audio and microphone | Working | Playback, headset voice capture, disconnection and reconnection confirmed |
| Webcam | Working | Image capture confirmed alongside the internal microphone |
| CPU power management | Working | X86PlatformPlugin active; frequency and estimated package power respond to activity |
| CPU temperature telemetry | Working | Readings retained at idle and during desktop activity; fan RPM remains unavailable |
| Battery detection and battery power | Working | Internal battery recognized; discharge reported after AC removal |
| External SSD access | Working | Samsung 960 EVO in a USB-C enclosure |
| USB-C SuperSpeed and connector orientation | Working | Samsung/RTL9210 at 5 Gb/s in both laptop-side connector orientations with the current cable |
| USB-A SuperSpeed and file access | Working | Same Initio enclosure at 5 Gb/s; files open on both tested USB-A connectors |
| F11/F12 brightness keys | Working | BrightnessKeys companion package; not included in EFI v0.1.0 |
| F6 touchpad toggle | Working | Direct key enables and disables the touchpad |
| Fn function row | Configured | Ordinary F1–F12 events recorded; four conflicting macOS shortcuts disabled, session refresh confirmation pending |
| Touchpad and gestures | Working | ELAN0662 gestures confirmed in daily use; F6 toggle also works |
| NVIDIA PCI attachment | Working diagnostic | Probe 0.1.0 attaches to `10DE:1F91`, verifies subsystem `17AA:3806`, reads fixed PCI configuration and assigned resource metadata; no GPU initialization or acceleration |
| NVIDIA BAR0 identification | Working diagnostic | Probe 0.2.0 completed one read-only `NV_PMC_BOOT_0` read with the expected TU117 fields; no GPU initialization or acceleration |
| NVIDIA HAL table match | Working diagnostic | Version 0.3.0 completed two read-only identification loads and a pinned local TU117 variant-41 table match; no HAL object or GPU initialization |
| NVIDIA OS-adapter startup | Working diagnostic | Version 0.4.0 passed the integrated kernel startup check for clocks, ordinary RAM, atomics, allocation and thread mutexes; no GPU initialization |
| NVIDIA original-caller startup | Pending | Version 0.5.0 compiled package and native checks passed; the combined laptop result remains pending |
| Remaining icon keys | Pending | Microphone, refresh, airplane mode, camera, lock and display actions; further icon-key investigation deferred |
| USB-C video | Pending | No video test available; hardware video capability and routing remain unverified |
| USB 2 device coverage / storage reliability | Pending | External USB 2 devices, measured throughput and sustained reliability |
| SD reader / fingerprint reader | Pending | Driver support and device operation |
| Battery runtime / sleep and wake | Pending | Measured runtime and device recovery; basic battery power is confirmed |
| NVIDIA electrical power-off | Pending | Deferred until after the driver-port attempt; PCI visibility does not establish electrical power state |
| NVIDIA acceleration | Not working | GTX 1650 Max-Q has no supported driver in this configuration |
| Native macOS Wi-Fi interface | Not working | Network management uses HeliPort |
| HDMI output | Not working | No image or external display in the macOS report; physical GPU routing under investigation |

Detailed hardware information is in [Hardware](docs/status/hardware.md).

## Operating configuration

macOS and OpenCore use the external Samsung 960 EVO. Independent boot is confirmed after manually copying the current private EFI from the 240 GB HDD. The HDD remains available as a recovery route; Windows remains on the internal PM981a.

NVIDIA probe 0.1.0 is confirmed to attach to the GTX 1650 Max-Q and read its fixed PCI configuration and assigned resource descriptors. Version 0.2.0 is also confirmed on the laptop: exactly one guarded read of the BAR0 identification register returned the expected TU117 fields. Version 0.3.0 subsequently completed two read-only identification loads and a local pinned-table match for TU117 variant 41. Version 0.4.0 then returned `integrated_passed` on the laptop, confirming the bounded CPU-component startup check in the Tahoe kernel while retaining the same two-register TU117 identification. These are diagnostic milestones; NVIDIA's HAL is not instantiated, its resource manager is not integrated, and GPU initialization and graphics acceleration remain unimplemented. Intel remains the operating display GPU; the reports do not audit the full current EFI.

Audio uses a VoodooHDA extension installed in `/Library/Extensions`, including the S540 microphone correction. The EFI alone does not install this extension. The audio guides document the existing installation and upgrade procedures; those helpers require their original rollback state.

## Development priorities

- Collect one combined laptop result for the [verified v0.5.0 NVPort package](packages/nvidia-transport/README.md). It connects eight original allocation/mutex callers to a bounded reserve and a new mutex backend. Version 0.4.0 remains the confirmed kernel checkpoint; full resource-manager integration, DMA, firmware startup and acceleration remain unimplemented.
- Complete storage reliability and remaining USB 2 device checks. Both USB-A connectors and USB-C in both orientations negotiate 5 Gb/s with the tested hardware. Audio peripherals, battery power and independent SSD boot work; measured battery runtime remains open.
- Complete Intel stability and power-management coverage; sustained cooling and fan telemetry remain open. External-display work is paused.
- Complete remaining device support and investigate connection performance from the recorded Internet baseline; wired/Bluetooth microphones, headphone switching and wireless reconnection work.
- Retain the working keyboard controls; remaining icon actions, equalization and sleep refinements are deferred.
- Keep native macOS Wi-Fi integration open; NVIDIA electrical power-off remains deferred until after the driver-port attempt.

See the [Roadmap](docs/status/roadmap.md) for the implementation plan.

## Documentation and downloads

The CPU-only OS adapter contains clock, ordinary-RAM and atomic foundations. [Combined GitHub validation passed](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/actions/runs/38696607911), including kernel-object linking and native userspace execution. The v0.4.0 integrated package adds ordinary host-RAM allocation and thread mutexes for a single laptop startup check. The v4 laptop report returned `integrated_passed`, confirming the bounded startup check in the Tahoe kernel. Concurrent kernel execution and full NVIDIA caller compatibility remain unvalidated.

The [documentation index](docs/README.md) links to setup, maintenance, and recovery procedures. Main guides: [Intel graphics](docs/guides/intel-graphics.md), [Tahoe audio](docs/guides/tahoe-audio.md), and [microphone correction](docs/guides/microphone-fix.md).

Download the [first EFI release, v0.1.0](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/releases/tag/v0.1.0), with compatibility notes and setup instructions. Personalize its SMBIOS identity before use.

Generated packages are available in **Artifacts** from successful [GitHub Actions runs](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/actions). Current companion packages are `S540-microfono-fix-v2`, `S540-volume-fine-v1` and `S540-brightness-keys-v2`. The [function-key guide](docs/guides/function-keys.md) records the complete keyboard mapping and remaining work.

The **S540-nvidia-transport-v5** compiled package passed its [native Intel build and checks](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/actions/runs/38726407067) from source `81c1529a31fcc1b61fa3a466442e73fef0fc3aa9`. Its shared startup sequence passed 23 foundation checks and 35 original-caller/reserve checks, both plain and with sanitizers. The archive and every contained file checksum were verified. Version 0.4.0 remains the confirmed laptop checkpoint; v5 kernel execution is pending. The [package guide](packages/nvidia-transport/README.md) describes the single combined test. No HAL object, resource manager, initialized GPU or acceleration is provided.

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
