# Lenovo IdeaPad S540-15IWL GTX — macOS Tahoe

An OpenCore project for **macOS Tahoe 26** on the Lenovo IdeaPad S540-15IWL GTX. The working configuration boots from the external Samsung 960 EVO and uses Intel graphics. The official EFI now includes native-menu Intel Wi-Fi and corrected hardware names.

**Status: October 20, 2026.** Webcam, internal microphone, Bluetooth headset audio and microphone, the 3.5 mm headset jack, and lid-close sleep/open-lid wake have been tested on the laptop. **Hotkey update, October 24: F4 microphone mute, F7 Wi-Fi/Bluetooth control and F9 screen lock are user-confirmed working. F8 camera disablement is NOT WORKING and further work is paused by request.** F1–F3 and non-NVIDIA F11–F12 retain their working status. SD-reader investigation resumed on October 24; operational NVIDIA development remains paused.

## Hardware

| Component | Model |
|---|---|
| Laptop | Lenovo IdeaPad S540-15IWL GTX, **81SW** |
| CPU / memory | Intel Core i7-8565U / 12 GB DDR4-2400 |
| Graphics | Intel UHD 620 / NVIDIA GTX 1650 Max-Q 4 GB |
| Display | BOE NV156FHM-N61, 1920×1080 |
| Audio | Realtek ALC257 |
| Wireless | Intel AC9560 Wi-Fi and Intel Bluetooth |
| Touchpad | ELAN0662 I2C |
| macOS storage | External Samsung 960 EVO over USB-C |
| Windows storage | Internal Samsung PM981a, 512 GB |

## Compatibility

“Working” refers to the stated observations. It does not certify every application, peripheral or long-duration workload.

| Feature | Status | Confirmed scope |
|---|---|---|
| Boot and desktop | Working | Independent OpenCore/macOS boot from the external Samsung SSD |
| Intel graphics and internal display | Working | Intel acceleration, Full HD display and corrected startup black-screen delay |
| Brightness control | Working in official EFI | Works in the non-NVIDIA configuration; the separate NVIDIA-test regression remains deferred |
| Native-menu Wi-Fi | Working | AirportItlwm 2.4.0, native menu/network selection; `itlwm` disabled; official Samsung EFI confirmed |
| Internal speakers and microphone | Working |VoodooHDA 3.6.10; video recording tested both webcam and microphone; built-in speakers and internal microphone also work after waking and disconnecting the Bluetooth headset (October 24) |
| 3.5 mm headset output, microphone and switching | Working | Headphone playback, microphone input and speaker/headphone switching tested |
| Bluetooth headset audio and microphone | Working | Playback and headset microphone also confirmed after reconnection following sleep/wake on October 24; automatic reconnection was not separately established |
| Webcam | Working | Video recording confirmed |
| F1–F3 audio keys | Working | Confirmed again on October 20; no repeat test required |
| F4, F7 and F9 icon actions | Working | Microphone mute, Wi-Fi/Bluetooth control and screen lock confirmed by the user with S540 Tasti |
| F8 camera disablement | Not working / paused | The firmware flag changes but video capture continues, including after reopening Photo Booth; further F8 work is suspended by request |
| F11/F12 brightness keys | Working in non-NVIDIA EFI | Keep the working configuration; NVIDIA-test brightness regression remains separate |
| Ordinary Fn function row | Partially verified | Existing F1–F12 event evidence retained; shortcut/session state is tracked in the function-key guide |
| Touchpad and gestures | Working | ELAN0662 gestures and daily operation confirmed; F6 remains within the current F4–F10 review group |
| CPU power management and telemetry | Working | X86PlatformPlugin active; historical frequency, temperature and estimated package-power responses recorded |
| Battery Low Power Mode | Verified CPU/package response | October 24 OFF–ON–ON–OFF test: estimated package power about 11.4 W with the mode on versus 34.4–36.5 W off; active frequency 2.4 GHz versus 3.89–4.00 GHz. Battery 1 / AC 0 retained. This is not a measured autonomy result; see [test scope and thermal limits](docs/status/battery-sleep.md#low-power-mode-under-cpu-load--24-october-2026). |
| RAM and hardware names | Verified | 12 GB DDR4-2400; expandable memory status and CPU/GPU/panel labels corrected |
| Battery and basic sleep/wake | Working | Battery and basic sleep/wake confirmed; user reports modest runtime and attributes it to an aged battery. No further autonomy test requested. |
| USB-A and USB-C storage | Working | Tested connectors at 5 Gb/s; USB-C tested in both orientations; active nine-port map confirmed |
| Internal NVMe detection | Working | 512 GB PM981a available; SMART verified and TRIM reported active |
| SD reader | Unresolved / investigation resumed | O2Micro 1217:8621; SD-only direct-match/rollback package verified against the supplied external EFI, with its configuration and NVIDIA experiment preserved. Target reading on Tahoe remains unconfirmed. See [SD and fingerprint scope](docs/status/sd-fingerprint.md). |
| Fingerprint reader | Not working / work stopped | Goodix 27c6:55b4 enumerates on USB, but macOS fingerprint authentication does not work. Further investigation stopped by user request on October 24. See [retained findings](docs/status/sd-fingerprint.md). |
| HDMI | Not working | No display output established; NVIDIA-related investigation remains deferred |
| USB-C video | Not verified | Video capability and routing not established |
| NVIDIA diagnostics | Confirmed checkpoints | V9 kernel preparation and the complete-image idle-loader ABI passed; see the consolidated validation record |
| NVIDIA acceleration | Not working / development paused | Original RM/GSP initialization and graphics acceleration have not passed a target test |

Detailed observations and their limits are in [Hardware](docs/status/hardware.md), [Battery and sleep](docs/status/battery-sleep.md), and [Function keys](docs/guides/function-keys.md).

## Official EFI

The external Samsung 960 EVO holds the working OpenCore/macOS installation. The 240 GB test EFI remains separate. The official configuration retains Intel graphics and the working USB, Bluetooth, audio and power-management settings.

- Native Wi-Fi and hardware naming changes are installed and confirmed on the official EFI.
- The consolidated config also removes the obsolete `IONVMeFamily` block entry. The internal SSD was already available in the captured runtime; this is configuration cleanup, not a new storage repair. The removal was delivered and validated, but a subsequent boot of that exact final config has not yet been explicitly confirmed.
- VoodooHDA is installed in `/Library/Extensions`; an EFI copy alone does not install the working audio extension.
- SD experiments, NVIDIA probes and complete-image loader packages are not merged into the official EFI.

**[EFI v0.2.0](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/releases/tag/v0.2.0) is the stable Intel-graphics package with native Wi-Fi and the consolidated hardware names.** It preserves the active binary payload from the supplied official EFI. Read the [installation guide](docs/releases/v0.2.0/INSTALL.md): public SMBIOS fields require personalization, and VoodooHDA audio remains separately installed on macOS. [Release notes](docs/releases/v0.2.0/RELEASE-NOTES.md) state the confirmed scope and open limitations. The v0.1.0 release and `config/efi/current` remain historical snapshots; v0.2.0 has its own [versioned recipe and manifests](config/efi/releases/v0.2.0/). Machine-specific SMBIOS identifiers, credentials and raw diagnostic reports remain outside the repository.

## NVIDIA validation — grouped milestones

The [consolidated NVIDIA validation record](docs/status/nvidia-validation.md) is the entry point for completed checkpoints, native builds, target results and retained historical evidence.

| Stage | Latest confirmed result | Boundary |
|---|---|---|
| Diagnostic kernel preparation | V9: **486 kernel startup checks**, cleanup and no warnings; **15 separate userspace firmware checks** | Preparation and selected Resource Server support; no full GPU startup |
| Complete-image idle-loader ABI | Exact signed image loaded, valid idle snapshot, normal unload; target report confirmed on October 20 | Original RM/GSP calls and hardware initialization remained disabled |
| Native development validation | Component, source, symbol, lifecycle, fault and sanitizer evidence retained separately | CI/CPU results do not establish target GPU operation |
| Operational RM/GSP and acceleration | **Not validated on target** | Runtime callbacks, original-entry admission, stack/capacity and bounded shutdown remain gates |

Completed checkpoints are retained as regression coverage. They do not require separate laptop reruns. When NVIDIA work resumes, the next target checkpoint must combine the admitted integration in **one package, one test entry point and one report**, after the prerequisite checks pass.

The existing native workflows already group the automatic checks: the idle-image pipeline performs the selective rebuild, strict link and packaging controls; the extended integration workflow is manual. No native CI or new GPU test is started by this documentation update.

## Remaining work

1. Preserve the confirmed [function-key actions](docs/guides/function-keys.md), including F4, F7 and F9. F8 camera disablement is recorded as non-working and paused; no further F8 tests or builds are planned unless explicitly resumed.
2. Complete the resumed [SD-reader investigation](docs/status/sd-fingerprint.md) using the **external test EFI only**, preserving its existing configuration and NVIDIA experiment. Fingerprint authentication is recorded as not working; further fingerprint work is stopped by request. Keep operational NVIDIA development paused.
3. Treat battery runtime, long standby, sustained thermal behavior and storage endurance as unmeasured coverage, not as demonstrated faults requiring new patches.

See the [Roadmap](docs/status/roadmap.md) for grouped acceptance criteria.

## Documentation and downloads

- [Documentation index](docs/README.md): setup, maintenance, hardware status and recovery.
- [Stable EFI release v0.2.0](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/releases/tag/v0.2.0): complete Intel-graphics EFI, native Wi-Fi, installation guide and checksum. The older [v0.1.0](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/releases/tag/v0.1.0) is retained as history.
- [Generated artifacts](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/actions): compiled companion packages from successful runs. Package guides retain their exact provenance and rollback instructions.
- [Consolidated NVIDIA validation](docs/status/nvidia-validation.md): current checkpoint summary and historical build/package details previously repeated in this README.

**Code → Download ZIP downloads source code without compiled payloads. It is not an installer.** Builders assemble feature sources into distributable packages.

## Repository layout

| Path | Purpose |
|---|---|
| [packages/](packages/) | Feature launchers and runtime sources |
| [builders/](builders/) | Build and package assembly scripts |
| [tests/](tests/) | Validation tests and fixtures |
| [config/](config/) | ACPI, historical EFI profiles, pinned assets and USB mapping |
| [docs/](docs/README.md) | Guides, current status, validation records and roadmap |
| [patches/](patches/) | Driver source patches |
| [licenses/](licenses/) | Dependency licenses |
| [.github/workflows/](.github/workflows/) | Automated builds and checks |
| [archive/](archive/README.md) | Superseded procedures and development history |

