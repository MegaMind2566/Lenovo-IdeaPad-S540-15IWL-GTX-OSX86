# Hardware roadmap

Updated on **8 November 2026**. The current official **v0.3.0 non-NVIDIA** baseline remains stable with known limitations. A separate NullMoth 2.7.2 target profile now has confirmed NVIDIA Metal execution, HDMI video/audio, brightness and one short sleep/wake cycle on the source laptop; it is not merged into the release. Both profiles concern macOS Tahoe **26.7.1 (25G241)** on the Lenovo IdeaPad S540-15IWL GTX (81SW). Future macOS updates require validation. **The project remains in development.**

## Current work and limits

| State | Work | Scope |
|---|---|---|
| Preserve confirmed | Internal Intel-based boot and native Windows | Keep the working rEFInd/native-Windows route, OpenCore ScanPolicy 769 and private identity; update the OpenCore directory only |
| Confirmed in this milestone | O2Micro SD reader | Working from the updated internal non-NVIDIA EFI with the known 8 GB FAT32 card; insertion during an active macOS session, mounting/unmounting and availability after sleep are user-confirmed |
| Accepted working scope | SD reader coverage | SD operation is reconfirmed working; no further checks are requested for this milestone. Throughput, broader card/SDXC classes and write/data-integrity validation remain unmeasured evidence boundaries, not pending tasks |
| Preserve confirmed | Audio, network, touchpad and keys | Keep internal/wired/Bluetooth audio, native Wi-Fi, gestures, F1–F5/F7/F9 and brightness in both tested profiles; F4/F7/F9 require the matching S540 Tasti macOS companion |
| Confirmed | F6 touchpad toggle | User reconfirmed touchpad enable/disable on 27 October; no further F6 test is pending |
| Not working / paused | F8 camera disablement | Firmware changes do not stop video capture; the user accepted this limitation and paused further work |
| Not working / work stopped | Fingerprint authentication | Goodix 27c6:55b4 enumerates on USB but macOS authentication is unavailable; investigation stopped by request |
| Unavailable in the official EFI / confirmed experimentally | NVIDIA acceleration | v0.3.0 keeps `-wegnoegpu`. NullMoth 2.7.2 separately passed NVIDIA compute, rendering and presentation checks on the source laptop |
| Confirmed experimentally | HDMI output and display audio | NVIDIA-routed LG TV output works at 1920×1080 60 Hz, with exact-match NMXAudio playback. This remains outside v0.3.0 |
| Unverified | F10 display action | A working HDMI display is now available, but the physical display-mode action itself has not been separately confirmed |
| Native hardware limitation | USB-C video | The laptop does not provide native USB-C video output; USB data transfer works. This is not a pending EFI fix |
| Working / accepted telemetry limitation | Fans | Physical operation is user-confirmed; RPM is not readable in the current macOS configuration. Investigation is closed for this release by request; no further firmware collection, laptop tests or fan-control/driver change is included |
| Deferred by request | Prolonged sleep / standby and hibernation | Not verified; keep these checks suspended. Official-profile cycles and one 54-second NullMoth HDMI/audio cycle remain valid |
| Optional / not a release requirement | Displayed Mac model label | The cosmetic 13-inch label change is not a priority; no test or EFI change is requested |
| Coverage boundary / not active work | Other long-duration behavior | Battery autonomy and sustained storage/cooling remain beyond the established short tests; no further tests are requested by this update |

## Confirmed baseline

| Area | Result | Boundary |
|---|---|---|
| Intel display | Accelerated UHD 620, internal Full HD panel, corrected startup backlight and F11/F12 brightness | NullMoth A/B regression resolved by restoring `applbkl=1`; the official EFI was not changed |
| Native Wi-Fi | Tested AirportItlwm 2.4.0, native menu and connectivity; recovery after restart/sleep confirmed | AirDrop and Continuity not claimed |
| Audio and camera | Speakers, internal/wired/Bluetooth microphones, headphone switching and webcam video work | VoodooHDA 3.6.10 is separately installed in macOS; F8 video disablement is not working |
| Sleep recovery | Official lid/idle cycles and selected peripherals confirmed; NullMoth HDMI/audio/backlight/Wi-Fi/Bluetooth survived one scheduled 54-second cycle | These observations are not overnight reliability, hibernation or calibrated standby drain |
| USB | Nine-port map; tested USB-A and USB-C connectors at 5 Gb/s, both USB-C orientations and file access confirmed | Link rate is not a sustained throughput benchmark |
| CPU / battery | X86PlatformPlugin, reporting and discharge; Low Power Mode lowers observed estimated CPU package power/frequency in the retained short comparison | Not whole-laptop power, equal-work efficiency or measured runtime; user attributes modest autonomy to an aged battery |
| SD | Previous direct-match BigSurSDXC driver, known 8 GB FAT32 card, internal boot and the stated insertion/mount/sleep behaviors confirmed | Does not validate the separate 3V3 candidate or every card class |

## Development policy

Preserve confirmed functions and investigate a reported regression from its actual runtime evidence. Do not infer a hardware failure merely from an unmeasured feature or repeat completed laptop checks as routine coverage.

The [NVIDIA validation record](nvidia-validation.md) and package records retain the independent source, native-build and target checkpoints. They have different scopes from the [NullMoth target profile](../../packages/nullmoth-s540/README.md): the successful third-party runtime does not retroactively complete this repository's RM/GSP port. All NVIDIA experiments remain excluded from the official Intel release.

F8 and fingerprint work stay paused/stopped unless the user explicitly resumes them. Fan RPM investigation is closed for this release with working fans and unavailable macOS telemetry recorded separately. Do not introduce firmware provisioning, EC writes or unrelated driver changes as part of an ordinary EFI update.

## References

- [Current hardware results](hardware.md)
- [Function keys](../guides/function-keys.md)
- [SD and fingerprint](sd-fingerprint.md)
- [Battery and sleep](battery-sleep.md)
- [NVIDIA validation and grouped checkpoints](nvidia-validation.md)
- [v0.3.0 installation](../releases/v0.3.0/INSTALL.md)
