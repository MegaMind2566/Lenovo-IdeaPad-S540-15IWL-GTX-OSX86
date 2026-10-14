# Lenovo IdeaPad S540-15IWL GTX — macOS Tahoe

An OpenCore project for **macOS Tahoe 26** on the Lenovo IdeaPad S540-15IWL GTX. The goal is to improve hardware support while keeping configuration, driver patches, and recovery procedures organized and reproducible.

Tahoe currently runs with Intel graphics acceleration, audio, Wi-Fi, Bluetooth headphone audio, and the webcam. Development continues on the remaining hardware features.

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

Current status as of **October 14, 2026**. **Pending** means the feature has not yet been established as working or not working.

| Feature | Status | Details |
|---|---|---|
| macOS boot and desktop | Working | Tahoe on the external 960 EVO; OpenCore on a USB HDD |
| Intel graphics acceleration | Working | IntelAccelerator, Metal 3, up to 1536 MB shared graphics memory |
| Internal display | Working | Full HD resolution; startup black-screen delay corrected |
| Brightness slider | Working | Brightness control through macOS settings |
| Audio playback and volume | Working | VoodooHDA; gradual volume changes and F1–F3 controls |
| Internal microphone | Working | S540 microphone correction v2 |
| Wi-Fi through HeliPort | Working | Intel AC9560 with itlwm |
| Bluetooth headphone audio | Working | Headphone playback |
| Webcam | Working | Image available in Photo Booth |
| CPU power management | Working | X86PlatformPlugin active |
| Battery detection | Working | Battery and charge state available |
| External SSD access | Working | Samsung 960 EVO in a USB-C enclosure |
| NVIDIA acceleration | Not working | GTX 1650 Max-Q has no supported driver in this configuration |
| F11/F12 brightness keys | Not working | Brightness remains available through the slider |
| Native macOS Wi-Fi interface | Not working | Network management uses HeliPort |
| Touchpad and gestures | Pending | ELAN0662 functionality requires verification |
| Analog audio jack / Bluetooth microphone | Pending | Separate from speaker and Bluetooth headphone playback |
| HDMI / USB-C video | Pending | Output routing and external display support |
| USB SuperSpeed / USB-C orientation | Pending | Transfer speed and both connector orientations |
| SD reader / fingerprint reader | Pending | Driver support and device operation |
| Battery runtime / sleep and wake | Pending | Power transitions and device recovery |
| NVIDIA electrical power-off | Pending | Disabling its driver does not establish that the GPU is powered off |

Detailed hardware information is in [Hardware](docs/status/hardware.md).

## Operating configuration

macOS uses the external SSD; Windows remains on the internal PM981a. OpenCore currently boots from a separate USB HDD. Moving the EFI to the 960 EVO is a planned step.

Audio uses a VoodooHDA extension installed in `/Library/Extensions`, including the S540 microphone correction. The EFI alone does not install this extension. Follow the audio guides for installation and rollback.

## Development priorities

- Consolidate the current configuration and complete the pending hardware features.
- Improve audio equalization and function-key support in a later stage.
- Complete battery, sleep, wake, and external display support.
- Investigate NVIDIA support, including the Linux driver port as a research project.

See the [Roadmap](docs/status/roadmap.md) for the implementation plan.

## Documentation and downloads

The [documentation index](docs/README.md) links to setup, maintenance, and recovery procedures. Main guides: [Intel graphics](docs/guides/intel-graphics.md), [Tahoe audio](docs/guides/tahoe-audio.md), and [microphone correction](docs/guides/microphone-fix.md).

Generated packages are available in **Artifacts** from successful [GitHub Actions runs](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/actions). The current microphone package is `S540-microfono-fix-v2`.

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
