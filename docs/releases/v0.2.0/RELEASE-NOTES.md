# v0.2.0 — Stable Intel-graphics EFI for macOS Tahoe

This release packages the current official EFI for the **Lenovo IdeaPad S540-15IWL GTX (81SW)**, with Intel UHD 620 graphics, native-menu Intel Wi-Fi and corrected hardware names. It supersedes the older v0.1.0 EFI snapshot for this tested configuration.

The working installation boots macOS Tahoe from an **external Samsung 960 EVO over USB-C**. The internal **Samsung PM981a 512 GB** retains Windows. These results describe this laptop and storage arrangement; this is not a generic EFI for other Lenovo or Samsung hardware.

## Changes included

- Native-menu Wi-Fi through the tested **AirportItlwm 2.4.0** variant for Intel AC9560 on Tahoe; the previous `itlwm` path is not active.
- Corrected Intel Core i7-8565U, NVIDIA model and BOE NV156FHM-N61 panel labels, plus the expandable-memory description. A corrected NVIDIA name does not provide NVIDIA acceleration.
- The working Intel framebuffer, brightness companion, USB map, touchpad, Bluetooth and power-management configuration are retained.
- The obsolete `IONVMeFamily` block entry is removed. The internal SSD was already available in the captured runtime; this removes a stale configuration entry rather than claiming a new storage repair.
- NVIDIA diagnostic/initialization packages and SD-reader experiments are not enabled in the stable boot configuration.
- Public SMBIOS identity fields are placeholders. Personalize them before booting, as described in [INSTALL.md](INSTALL.md).

## Established on the source laptop

| Feature | Confirmed scope |
|---|---|
| Boot and Intel display | Independent external-SSD boot, Intel acceleration and the internal Full HD panel |
| Brightness | Slider and F11/F12 work with this non-NVIDIA EFI |
| Wi-Fi | Native menu, network selection and working connectivity; official Samsung EFI confirmed |
| Audio | Speakers, internal microphone, 3.5 mm headset output/input and switching, using the separately installed VoodooHDA setup |
| Bluetooth | Headset playback, microphone capture, disconnection and reconnection |
| Webcam | Video recording confirmed |
| F1–F3 | Audio controls working |
| Touchpad | ELAN0662 input and gestures; F6 remains within the current F4–F10 keyboard completion scope |
| CPU and battery | X86PlatformPlugin active, battery detection and battery power; historical telemetry responds to activity |
| Basic sleep/wake | Lid-close sleep and open-lid resume confirmed by the user |
| USB storage | Tested USB-A/USB-C connectors at 5 Gb/s; both USB-C orientations tested |
| Internal NVMe | PM981a detected at 512 GB, SMART reported verified and TRIM active |

“Confirmed” applies to these observations, not every peripheral, application or long-duration workload.

## Audio is a separate installed component

The working **VoodooHDA 3.6.10 S540 variant is installed in `/Library/Extensions` on macOS**, not in this EFI. Copying the EFI does not install the audio driver or recreate its private backups and approvals.

For the existing working installation, retain that driver and its backups. Audio preparation and the microphone/volume corrections are documented in the project’s [Tahoe audio guide](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/blob/main/docs/guides/tahoe-audio.md), [microphone correction guide](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/blob/main/docs/guides/microphone-fix.md) and [volume-control guide](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/blob/main/docs/guides/volume-control.md). Those procedures have prerequisites; this archive is not a complete fresh-install audio package.

## Remaining limitations

- **F4–F10 icon actions remain open.** Earlier F6 toggle observations are retained as history; they do not close the current completion group. Ordinary Fn+F1–F12 events were recorded, while application handling after the shortcut/session refresh remains tracked separately.
- **NVIDIA acceleration and HDMI output are not working.** NVIDIA operational development is paused. The separate NVIDIA-test brightness regression does not apply to the working non-NVIDIA brightness result above.
- **SD-card reading is unresolved and paused.** No successful macOS reading result is claimed.
- **Fingerprint authentication is unresolved.** No working macOS authentication support is established.
- USB-C video is unverified. Measured battery runtime, long standby, sustained thermal behavior and storage endurance remain unmeasured coverage.

## Validation boundary

The release is derived from the supplied official EFI with the consolidated configuration. Hardware results above come from the existing working laptop and its reports. Public-package preparation and static OpenCore validation are distinct from a new hardware test, a new native driver build or GPU initialization. This release does not claim those additional milestones.

Read [INSTALL.md](INSTALL.md) before replacing a boot EFI. Keep the known-working private EFI and the separate recovery/test boot route available.
