# v0.3.0 — Working internal Intel EFI with SD support

**Project status: in development.** This release records the current usable **non-NVIDIA** configuration for the Lenovo IdeaPad S540-15IWL GTX (**81SW**). It is a development milestone, not a final build or a claim that all hardware is supported.

## What changed

- The release now follows the user-confirmed **internal Samsung PM981a installation**, where Windows and macOS APFS coexist.
- The **O2Micro SD reader works on the source laptop** with the previous BigSurSDXC 1.9.0 binary and direct `pci1217,8621` personality. The known card is 8 GB FAT32. The user confirmed operation from the updated internal non-NVIDIA EFI after an earlier no-media result.
- The active bootloader is **OpenCore 1.0.8 RELEASE**. Intel graphics, native-menu Wi-Fi, the USB map, brightness support and the existing CPU/battery configuration are retained.
- **NVIDIA remains disabled** through the existing `-wegnoegpu` configuration. NVIDIA probes and experimental initialization packages are not included.
- Windows retains its **native rEFInd route**, while OpenCore's `ScanPolicy=769` hides its boot entry. Existing Windows/rEFInd files are preserved, not redistributed.
- The public package supplies **`EFI/OC`**, plus a rEFInd configuration example. It deliberately omits `EFI/BOOT`, Microsoft boot files and the rEFInd executable. Read the installation instructions; this is not a self-booting USB image.
- Public SMBIOS identity values are sanitized placeholders. Users must preserve or generate their own private identity before booting.

## Hardware status

| Feature | Status and tested scope |
|---|---|
| Internal macOS boot / Intel display | Working; UHD 620 acceleration, Full HD panel and corrected startup backlight |
| Brightness | Slider and F11/F12 working in this non-NVIDIA configuration |
| Native Wi-Fi | Intel AC9560 / tested AirportItlwm 2.4.0; native menu, connectivity and restart/sleep recovery confirmed |
| Speakers and internal microphone | Working with separately installed VoodooHDA 3.6.10, including after wake and Bluetooth disconnection |
| 3.5 mm headset | Playback, microphone and automatic speaker/headphone switching working |
| Bluetooth headset | Playback, microphone and reconnection working; also confirmed after sleep/wake, without a separate automatic-reconnection claim |
| Webcam video | Working; video recording confirmed |
| Touchpad | ELAN0662 operation and gestures working |
| F1–F3 / F11–F12 | Audio and brightness controls working |
| F4 / F7 / F9 | Working through separately installed S540 Tasti 0.1.3 and its matching driver: microphone input-level mute/restore, Wi-Fi/Bluetooth control and screen lock |
| F5 browser reload | User-confirmed; direct/Fn distinction and general remapping remain separate |
| F6 | Earlier touchpad toggle confirmation retained; current complete mapping remains open |
| F8 camera disablement | **Not working; work paused by request.** Camera video itself works |
| F10 display action | **Unverified/deferred** pending a working external display and established action |
| CPU and battery | Power management, reporting and discharge working; Low Power Mode produced a measured CPU/package response in a short comparison |
| Sleep and wake | Lid and idle cycles confirmed, including one 3,603-second lid sleep and a 91-second idle sleep with no recorded DarkWake |
| USB storage | Tested USB-A and USB-C connectors at 5 Gb/s; both USB-C orientations and file access confirmed |
| Internal NVMe | Working; 512 GB detected, SMART verified and TRIM reported active |
| **O2Micro SD reader** | **User-confirmed working from the updated internal EFI** with the known 8 GB FAT32 card, including insertion during an active macOS session, mounting/unmounting and continued availability after sleep |
| Fingerprint authentication | **Not working; investigation stopped by request** |
| NVIDIA acceleration | **Unavailable and disabled in this EFI**; separate experimental work remains outside the release |
| HDMI | **Not working**; no usable output established |
| USB-C video | **Unverified** |
| Fans | **Working — user-confirmed**; RPM is not readable in the current macOS configuration. Investigation is closed for this release by request |

## Separate audio and hotkey installations

The EFI alone does not install VoodooHDA in macOS's auxiliary kernel collection or install the S540 Tasti app/driver. Existing users should retain the working installations and their private rollback state. Fresh users need the separate companion packages and their documented macOS permissions, approval and restart steps. See the release assets and [INSTALL.md](INSTALL.md).

The audio driver is the tested **VoodooHDA 3.6.10 S540 variant**, not AppleALC. The retained fresh-install audio wrapper has not been newly validated by a fresh-system install/reboot for this release; its own verification instructions remain required. F4/F7/F9 depend on the matching S540 Tasti installation; F8 is explicitly not fixed by the app's popup/status changes. The accepted F9/Command-L lock behavior is described in the [function-key guide](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/blob/v0.3.0/docs/guides/function-keys.md).

## Validation and limits

The new SD result is a **user functional confirmation on the source laptop**. The prior negative result and initialization trace remain documented; the later successful result supersedes the earlier no-media status for this setup. The release uses the previous direct-match driver, not the unvalidated S18R-disabled/3V3 candidate.

The SD update preserves the existing Intel configuration and native Windows/rEFInd boot files.

Insertion while macOS is running, mounting/unmounting and continued availability after sleep are user-confirmed on the known card. Write/data-integrity validation, throughput and arbitrary SD/SDXC capacities have not been newly established. The observed low-power CPU response is not a battery-runtime measurement. Hibernation, overnight standby, sustained thermal/storage behavior and all peripheral combinations remain outside the confirmed scope.

Public sanitization and static package checks are distinct from running the public placeholder identity unchanged, which is not supported. Do not treat a successful build, loaded driver or correct hardware name as proof of every function.

## Continuing development

The project remains open. The release preserves the current Intel baseline while tracking unsupported hardware, deferred work and separate NVIDIA research. Existing experimental checkpoints do not establish NVIDIA acceleration and are not activated by this release. [Hardware](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/blob/v0.3.0/docs/status/hardware.md), [Roadmap](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/blob/v0.3.0/docs/status/roadmap.md), and [source provenance](SOURCE-PROVENANCE.md) retain the detailed boundaries.
