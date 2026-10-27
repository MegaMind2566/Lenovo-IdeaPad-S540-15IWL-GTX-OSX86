# Hardware roadmap

Updated on **27 October 2026**. The current official **v0.3.0 non-NVIDIA** baseline boots macOS from the internal Samsung NVMe alongside Windows. Native Wi-Fi, Intel graphics, input, audio and the SD reader have functional confirmations. **Official EFI status: Stable — known limitations.** The classification covers the tested Lenovo IdeaPad S540-15IWL GTX (81SW) running macOS Tahoe **26.7.1 (25G241)** with Intel UHD 620 and NVIDIA disabled. It applies to the confirmed functions and tested sleep/wake cycles; prolonged standby and hibernation remain unverified and deferred. Future macOS updates require validation. **The project remains in development.** Unsupported hardware and separate NVIDIA research retain the scope recorded below.

## Current work and limits

| State | Work | Scope |
|---|---|---|
| Preserve confirmed | Internal Intel-based boot and native Windows | Keep the working rEFInd/native-Windows route, OpenCore ScanPolicy 769 and private identity; update the OpenCore directory only |
| Confirmed in this milestone | O2Micro SD reader | Working from the updated internal non-NVIDIA EFI with the known 8 GB FAT32 card; insertion during an active macOS session, mounting/unmounting and availability after sleep are user-confirmed |
| Accepted working scope | SD reader coverage | SD operation is reconfirmed working; no further checks are requested for this milestone. Throughput, broader card/SDXC classes and write/data-integrity validation remain unmeasured evidence boundaries, not pending tasks |
| Preserve confirmed | Audio, network, touchpad and keys | Keep internal/wired/Bluetooth audio, native Wi-Fi, gestures, F1–F5/F7/F9 and non-NVIDIA brightness; F4/F7/F9 require the matching S540 Tasti macOS companion |
| Confirmed | F6 touchpad toggle | User reconfirmed touchpad enable/disable on 27 October; no further F6 test is pending |
| Not working / paused | F8 camera disablement | Firmware changes do not stop video capture; the user accepted this limitation and paused further work |
| Not working / work stopped | Fingerprint authentication | Goodix 27c6:55b4 enumerates on USB but macOS authentication is unavailable; investigation stopped by request |
| Unavailable in this EFI | NVIDIA acceleration | NVIDIA stays disabled with -wegnoegpu. Experimental NVIDIA implementation and target evidence remain separate from this release |
| Open / linked work | HDMI output and F10 display action | HDMI has no usable output established; F10 is tracked in the same workstream and depends on a working external display and the intended mode action |
| Native hardware limitation | USB-C video | The laptop does not provide native USB-C video output; USB data transfer works. This is not a pending EFI fix |
| Working / accepted telemetry limitation | Fans | Physical operation is user-confirmed; RPM is not readable in the current macOS configuration. Investigation is closed for this release by request; no further firmware collection, laptop tests or fan-control/driver change is included |
| Deferred by request | Prolonged sleep / standby and hibernation | Not verified; keep these checks suspended. Confirmed lid and idle sleep results remain valid |
| Optional / not a release requirement | Displayed Mac model label | The cosmetic 13-inch label change is not a priority; no test or EFI change is requested |
| Coverage boundary / not active work | Other long-duration behavior | Battery autonomy and sustained storage/cooling remain beyond the established short tests; no further tests are requested by this update |

## Confirmed baseline

| Area | Result | Boundary |
|---|---|---|
| Intel display | Accelerated UHD 620, internal Full HD panel, corrected startup backlight and F11/F12 brightness | Separate NVIDIA-test brightness behavior is not merged into the official EFI |
| Native Wi-Fi | Tested AirportItlwm 2.4.0, native menu and connectivity; recovery after restart/sleep confirmed | AirDrop and Continuity not claimed |
| Audio and camera | Speakers, internal/wired/Bluetooth microphones, headphone switching and webcam video work | VoodooHDA 3.6.10 is separately installed in macOS; F8 video disablement is not working |
| Sleep recovery | Lid and idle sleep/wake, Bluetooth-headset reconnection, internal audio after wake and SD availability after sleep confirmed | A 3,603-second lid cycle and 91-second idle cycle are observations, not overnight reliability or calibrated standby drain |
| USB | Nine-port map; tested USB-A and USB-C connectors at 5 Gb/s, both USB-C orientations and file access confirmed | Link rate is not a sustained throughput benchmark |
| CPU / battery | X86PlatformPlugin, reporting and discharge; Low Power Mode lowers observed estimated CPU package power/frequency in the retained short comparison | Not whole-laptop power, equal-work efficiency or measured runtime; user attributes modest autonomy to an aged battery |
| SD | Previous direct-match BigSurSDXC driver, known 8 GB FAT32 card, internal boot and the stated insertion/mount/sleep behaviors confirmed | Does not validate the separate 3V3 candidate or every card class |

## Development policy

Preserve confirmed functions and investigate a reported regression from its actual runtime evidence. Do not infer a hardware failure merely from an unmeasured feature or repeat completed laptop checks as routine coverage.

The [NVIDIA validation record](nvidia-validation.md) and package records retain source, native-build and target checkpoints. They have different scopes: compilation, a loaded image and a prepared device do not establish operational RM/GSP startup or graphics acceleration. NVIDIA experiments remain excluded from the official Intel release. This release neither resets those research checkpoints nor declares the project complete.

F8 and fingerprint work stay paused/stopped unless the user explicitly resumes them. Fan RPM investigation is closed for this release with working fans and unavailable macOS telemetry recorded separately. Do not introduce firmware provisioning, EC writes or unrelated driver changes as part of an ordinary EFI update.

## References

- [Current hardware results](hardware.md)
- [Function keys](../guides/function-keys.md)
- [SD and fingerprint](sd-fingerprint.md)
- [Battery and sleep](battery-sleep.md)
- [NVIDIA validation and grouped checkpoints](nvidia-validation.md)
- [v0.3.0 installation](../releases/v0.3.0/INSTALL.md)
