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
| Bluetooth headphone audio and microphone | Working | Playback and headset voice capture confirmed |
| Webcam | Working | Image capture confirmed alongside the internal microphone |
| CPU power management | Working | X86PlatformPlugin active |
| Battery detection | Working | Battery and charge state available |
| External SSD access | Working | Samsung 960 EVO in a USB-C enclosure |
| NVIDIA acceleration | Not working | GTX 1650 Max-Q has no supported driver in this configuration |
| F11/F12 brightness keys | Working | BrightnessKeys companion package; not included in EFI v0.1.0 |
| F6 touchpad toggle | Working | Direct key enables and disables the touchpad |
| Fn function row | Configured | Ordinary F1–F12 events recorded; four conflicting macOS shortcuts disabled, session refresh confirmation pending |
| Remaining icon keys | Pending | Microphone, refresh, airplane mode, camera, lock and display actions; further icon-key investigation deferred |
| Native macOS Wi-Fi interface | Not working | Network management uses HeliPort |
| Touchpad and gestures | Working | ELAN0662 gestures confirmed in daily use; F6 toggle also works |
| Analog audio jack | Pending | Connector operation remains to be verified |
| HDMI / USB-C video | Pending | Output routing and external display support |
| USB SuperSpeed / USB-C orientation | Pending | Transfer speed and both connector orientations |
| SD reader / fingerprint reader | Pending | Driver support and device operation |
| Battery runtime / sleep and wake | Pending | Power transitions and device recovery |
| NVIDIA electrical power-off | Pending | Disabling its driver does not establish that the GPU is powered off |

Detailed hardware information is in [Hardware](docs/status/hardware.md).

## Operating configuration

macOS uses the external SSD; Windows remains on the internal PM981a. OpenCore currently boots from a separate USB HDD. Moving the EFI to the 960 EVO is a planned step.

Audio uses a VoodooHDA extension installed in `/Library/Extensions`, including the S540 microphone correction. The EFI alone does not install this extension. The audio guides document the existing installation and upgrade procedures; those helpers require their original rollback state.

## Development priorities

- Make the external SSD independently bootable and consolidate the current working EFI.
- Complete storage, USB, Intel stability, power management and external display support.
- Finish wireless reconnection, audio peripheral and remaining device support.
- Retain the working keyboard controls; remaining icon actions, equalization and sleep refinements are deferred.
- Keep native macOS Wi-Fi integration and NVIDIA driver-port research open.

See the [Roadmap](docs/status/roadmap.md) for the implementation plan.

## Documentation and downloads

The [documentation index](docs/README.md) links to setup, maintenance, and recovery procedures. Main guides: [Intel graphics](docs/guides/intel-graphics.md), [Tahoe audio](docs/guides/tahoe-audio.md), and [microphone correction](docs/guides/microphone-fix.md).

Download the [first EFI release, v0.1.0](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/releases/tag/v0.1.0), with compatibility notes and setup instructions. Personalize its SMBIOS identity before use.

Generated packages are available in **Artifacts** from successful [GitHub Actions runs](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/actions). Current companion packages are `S540-microfono-fix-v2` and `S540-brightness-keys-v2`. The [function-key guide](docs/guides/function-keys.md) records the complete keyboard mapping and remaining work.

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

