# Lenovo IdeaPad S540-15IWL GTX — macOS Tahoe

An OpenCore project for **macOS Tahoe 26** on the **Lenovo IdeaPad S540-15IWL GTX (81SW)**. The current official configuration runs macOS and Windows on the internal Samsung NVMe, uses **Intel UHD 620**, and keeps **NVIDIA disabled**.

**Project status: in development — 27 October 2026.** [v0.3.0](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/releases/tag/v0.3.0) publishes the working non-NVIDIA baseline, including the newly user-confirmed SD reader. It is a tested milestone, not a completed project or a claim that every device works. NVIDIA research remains separate from this release.

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
| SD reader | O2Micro PCI `1217:8621`, subsystem `17AA:3803` |
| Fingerprint reader | Goodix USB `27c6:55b4` |
| Internal storage | Samsung PM981a 512 GB; Windows and macOS APFS coexist |

## Working, not working and unverified hardware

“Working” refers to the observations stated below on the source laptop. It does not certify other hardware revisions, every card/peripheral or all long-duration workloads.

| Feature | Status | Confirmed scope / limitation |
|---|---|---|
| Internal macOS boot and desktop | Working | OpenCore/macOS boot from the internal NVMe; Windows retains its separate native boot path |
| Intel graphics and internal display | Working | UHD 620 acceleration, Full HD panel and corrected startup black-screen delay |
| Brightness slider and F11/F12 | Working | Confirmed with the non-NVIDIA EFI |
| Native-menu Wi-Fi | Working | Intel AC9560 with the tested AirportItlwm 2.4.0 variant; network selection and recovery after restart/sleep confirmed |
| Speakers and internal microphone | Working | Separately installed VoodooHDA 3.6.10; playback and recording also confirmed after wake and Bluetooth-headset disconnection |
| 3.5 mm headset output/input | Working | Playback, headset microphone and speaker/headphone switching confirmed |
| Bluetooth headset audio/input | Working | Playback and microphone confirmed, including after reconnection following sleep/wake; automatic reconnection was not separately established |
| Webcam video | Working | Video recording confirmed |
| Touchpad and gestures | Working | ELAN0662 I2C operation and gestures confirmed |
| F1–F3 audio controls | Working | Speaker mute and volume controls |
| F4, F7 and F9 actions | Working with companion | S540 Tasti provides microphone input-level mute/restore, Wi-Fi/Bluetooth control and screen lock; these are separately installed macOS components |
| F5 browser reload | User-confirmed | Browser reload was accepted by the user; direct/Fn event distinction and a general remapping are separate questions |
| F6 touchpad toggle | **Working — user-confirmed** | Touchpad enable/disable reconfirmed on 27 October; no further F6 test is pending |
| F8 camera disablement | **Not working — paused** | The firmware flag changes but video capture continues; further F8 work is paused by request |
| F10 external-display action | **Pending — linked to HDMI** | Tracked together with HDMI output; a working external display and the intended display-mode action remain prerequisites |
| CPU power management | Working | X86PlatformPlugin active; frequency and estimated package-power responses observed |
| Battery Low Power Mode | CPU response verified | About 11.4 W estimated package power with the mode on versus 34.4–36.5 W off in the retained short CPU-load comparison; not a measured autonomy result |
| Battery reporting | Working | Battery operation and discharge confirmed; the user attributes modest runtime to an aged battery |
| Lid sleep/wake and idle sleep | Working in tested cycles | A 3,603-second lid sleep and a 91-second idle sleep resumed; no DarkWake recorded in those cycles |
| USB-A / USB-C storage | Working | Tested connectors negotiated 5 Gb/s; USB-C tested in both orientations and file access confirmed |
| Internal NVMe | Working | 512 GB detected, SMART verified and TRIM reported active |
| **SD reader** | **Working on the source laptop** | User-confirmed from the updated internal non-NVIDIA EFI using the previous direct-match BigSurSDXC driver and the known 8 GB FAT32 card; insertion during an active session, mounting/unmounting and availability after sleep confirmed; writes, throughput and other card classes not newly validated |
| Fingerprint authentication | **Not working — work stopped** | Goodix enumerates on USB, but macOS fingerprint authentication is unavailable; investigation stopped by request |
| NVIDIA acceleration | **Unavailable in this release** | NVIDIA stays disabled with `-wegnoegpu`; experimental NVIDIA payloads are excluded and research remains separate |
| HDMI | **Not working** | No usable display output established |
| USB-C video | **Not supported natively by the laptop** | Native video output through the built-in USB-C port is unavailable; USB data transfer works. This is a hardware limitation |
| Fans | **Working — user-confirmed** | RPM telemetry is unavailable in the current macOS configuration; investigation is closed for this release and no fan-control change is included |

Detailed observations are in [Hardware](docs/status/hardware.md), [Battery and sleep](docs/status/battery-sleep.md), [Function keys](docs/guides/function-keys.md), and [SD / fingerprint](docs/status/sd-fingerprint.md).

## Official non-NVIDIA release

**[Download v0.3.0](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/releases/tag/v0.3.0)** and read [INSTALL.md](docs/releases/v0.3.0/INSTALL.md) before copying files.

- The public payload contains **`EFI/OC` only**, with the active Intel configuration, native Wi-Fi, USB map, brightness support and the working direct-match SD bundle.
- The package does **not** contain `EFI/BOOT`, Microsoft boot files or a rEFInd executable. It is **not a drop-in USB boot image**. The supplied rEFInd configuration is an example for a separately installed loader.
- Existing internal dual-boot users update only the backed-up `EFI/OC` directory and preserve their existing Microsoft, fallback boot and rEFInd files and firmware entries. Windows starts natively through rEFInd; `ScanPolicy=769` keeps its boot entry out of the OpenCore picker.
- OpenCore uses the **1.0.8 RELEASE** build. NVIDIA remains disabled and no NVIDIA experiment is merged into the official configuration.
- Public SMBIOS identity fields are placeholders. Preserve your existing private identity or personalize them locally; never publish serials, MLB, ROM or SystemUUID.

[Release notes](docs/releases/v0.3.0/RELEASE-NOTES.md) and [source provenance](docs/releases/v0.3.0/SOURCE-PROVENANCE.md) separate the tested laptop result, public packaging checks and remaining work. Older [v0.2.0](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/releases/tag/v0.2.0) and [v0.1.0](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/releases/tag/v0.1.0) assets remain historical snapshots.

## macOS companions are separate

Copying the EFI does not install the complete audio or hotkey setup:

- **Audio:** retain the working VoodooHDA **3.6.10 S540** installation in `/Library/Extensions`. Fresh installations need the separate [audio package](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/releases/download/v0.3.0/S540-audio-Tahoe-3.6.10-v1.zip) and its approval/restart steps. See the release assets and [audio](docs/guides/tahoe-audio.md), [microphone](docs/guides/microphone-fix.md), and [volume](docs/guides/volume-control.md) guides. AppleALC is not the active audio path.
- **Hotkeys:** the S540 Tasti **0.1.3** app and its matching installed hotkey driver provide F4/F7/F9. Retain the working installation and the permissions it requires, or use the matching [S540-Tasti-v1.3.zip](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/releases/download/v0.3.0/S540-Tasti-v1.3.zip) companion asset. The accepted F9 mapping also uses Command-L for locking; see [Function keys](docs/guides/function-keys.md). F8 remains non-working despite the camera itself working.
- **Low Power Mode:** the tested battery setting is enabled, with AC unchanged at off. This is a macOS preference, not a setting installed by an EFI copy.

## Development continues

This release preserves the usable Intel baseline while the repository continues to track separate research and limitations. NVIDIA source/native/target checkpoints are documented in the [validation record](docs/status/nvidia-validation.md); they must not be interpreted as graphics acceleration or merged into this EFI. Completed checkpoints remain recorded without requiring routine laptop reruns.

The remaining external-display work is HDMI output and the linked F10 display action. F6 and the SD reader are user-confirmed working, with no further retests requested for this milestone. The stated SD card/coverage limits remain evidence boundaries, not pending tasks. Prolonged sleep/overnight standby and hibernation remain unverified and deferred by request. Changing the displayed Mac model label is optional and is not a release requirement. Native USB-C video is a laptop hardware limitation, not an EFI issue. Fans are user-confirmed working; unavailable macOS RPM telemetry is an accepted limitation and its investigation is closed for this release. F8 and fingerprint work remain paused/stopped as stated above. The [Roadmap](docs/status/roadmap.md) keeps these states distinct from the confirmed functions.

## Documentation and source layout

- [Documentation index](docs/README.md)
- [Release v0.3.0 installation](docs/releases/v0.3.0/INSTALL.md), [release notes](docs/releases/v0.3.0/RELEASE-NOTES.md), [provenance](docs/releases/v0.3.0/SOURCE-PROVENANCE.md)
- [Hardware status](docs/status/hardware.md) and [roadmap](docs/status/roadmap.md)
- [Generated build artifacts](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/actions)

**Code → Download ZIP downloads repository sources, not the assembled EFI or macOS installer.**

| Path | Purpose |
|---|---|
| [packages/](packages/) | Feature sources, launchers and runtime components |
| [builders/](builders/) | Reproducible package assembly |
| [tests/](tests/) | Validation and fixtures |
| [config/](config/) | ACPI, versioned EFI profiles, asset locks and USB mapping |
| [docs/](docs/README.md) | Setup, status, recovery, research and roadmap |
| [patches/](patches/) / [licenses/](licenses/) | Driver patches and dependency notices |
| [.github/workflows/](.github/workflows/) | Build, validation and publication workflows |
| [archive/](archive/README.md) | Superseded procedures and history |
