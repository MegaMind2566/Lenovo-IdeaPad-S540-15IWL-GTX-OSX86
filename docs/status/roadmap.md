# Hardware roadmap

Status updated on **October 20, 2026**. The official EFI on the external Samsung 960 EVO is the working Intel-based configuration. The separate 240 GB test EFI remains available; NVIDIA and SD-reader experiments are paused by request. The next focused hardware work is the remaining function-key actions.

Hotkey update, **October 24, 2026**: F4, F7 and F9 are confirmed. **F8 camera disablement is non-working and paused at the user’s request.** This update does not resume other paused work.

The user reconfirms that USB operation was already checked; no repeat USB test is requested. Battery runtime is described as modest and attributed by the user to an aged battery. Autonomy measurement is not an active task, and no macOS power-management repair is inferred from that report. The current routine-verification round is closed; paused items remain paused.

A subsequent user concern about Low Power Mode was checked with one battery OFF–ON–ON–OFF CPU comparison on 24 October. The mode had been disabled; after enabling it for battery use, both ON phases show about 11.4 W estimated package power and 2.4 GHz active frequency, versus 34.4–36.5 W and 3.89–4.00 GHz OFF. The original battery-on / AC-off preferences were restored. This closes the requested CPU-response check; it does not reopen autonomy measurement or establish equal-work efficiency. OFF phases contain thermal/performance-limit flags despite Nominal pressure; detailed evidence and limits are in [Battery and sleep](battery-sleep.md#low-power-mode-under-cpu-load--24-october-2026).

The user resumed SD-reader investigation before consolidating the **non-NVIDIA EFI** and then specified that **all SD tests use the external EFI**. The internal EFI is not the SD test target. The SD-only test/rollback package was checked against the supplied external EFI. The October 24 target report confirms direct O2Micro attachment and card detection, but no published SD media or disk; the candidate has not fixed reading. The user explicitly retained its existing NVIDIA experiment: config.plist, boot arguments, ACPI and bootloader files remain unchanged. Fingerprint authentication is now explicitly recorded as **NOT WORKING**, with further investigation stopped by request. NVIDIA, HDMI and F8 remain outside the active work.

## Current work order

| Order | Work | Scope |
|---|---|---|
| Retain confirmed | Function-key actions | Preserve F1–F3, non-NVIDIA F11/F12, and user-confirmed F4 microphone mute, F7 radio control and F9 screen lock. Other retained observations remain in the [function-key guide](../guides/function-keys.md). |
| Paused | F8 camera disablement | NOT WORKING: the firmware camera flag changes but video capture continues after reopening Photo Booth. The user accepts this limitation; no additional F8 tests or builds are planned unless explicitly resumed. |
| Consolidated | Official EFI | Native Wi-Fi, hardware names, USB mapping, CPU/battery reporting and the existing audio stack are retained. The config removing the old NVMe-block entry has been delivered; a subsequent boot with that final cleanup has not yet been explicitly confirmed. |
| Paused | NVIDIA implementation and target tests | v9 diagnostic startup and the complete-image idle-loader ABI have passed. Group the next original RM/transport/GSP work into one operational checkpoint after its admission gates; do not rerun completed milestones. |
| Active investigation | O2Micro SD reader | Resumed by request on 24 October; **external test EFI only, preserving its existing NVIDIA experiment**. The direct-match candidate attached and detected the inserted card on October 24, but no SD media/disk appeared. The card is user-confirmed 8 GB FAT32 and readable under Windows; the >32 GB limitation does not explain this failure. Identify the first initialization error before another functional patch. No card-reading success is claimed. See [SD and fingerprint scope](sd-fingerprint.md). |
| Paused | External displays | HDMI has no confirmed image; physical GPU routing remains unresolved. USB-C video capability/operation is unverified. |
| Later, if needed | Reliability and refinements | Measured battery runtime, extended sleep/peripheral recovery, sustained storage/cooling, fan RPM and audio equalisation remain separate from basic confirmed operation. No new patch is inferred from missing measurements. |
| Not working / work stopped | Fingerprint reader | Goodix `27c6:55b4` enumerates on HS02, but macOS fingerprint authentication is not working. Further fingerprint investigation stopped by user request on 24 October. Retain the [technical findings](sd-fingerprint.md); no further fingerprint test or build is requested. |

## Confirmed official-configuration baseline

| Component | Confirmed result | Remaining boundary |
|---|---|---|
| Boot and Intel display | Independent external Samsung boot, accelerated UHD 620/internal Full HD panel; startup blackout corrected with `-igfxblr` | Preserve the working framebuffer. The brightness regression in the separate NVIDIA-test EFI remains paused. |
| Wi-Fi | Native menu/network operation with AirportItlwm 2.4.0; itlwm disabled in the official config | Keep the exact working kext/config pair. Earlier HeliPort-only notes are historical. |
| Audio, microphone and webcam |Internal camera and microphone verified together by recorded video; speaker/headphone playback, Bluetooth headset microphone and 3.5 mm headset output/input confirmed; built-in speakers and internal microphone also work after waking and disconnecting the Bluetooth headset, confirmed on 24 October 2026 | Audio uses the existing VoodooHDA installation in `/Library/Extensions`; the EFI alone does not install it. Further equalisation is deferred. |
| Bluetooth | Headphone playback, microphone, disconnection and reconnection confirmed; playback and headset microphone also work after reconnection following sleep/wake, confirmed on 24 October 2026 | Automatic versus manual reconnection was not specified. IntelBluetoothFirmware and BlueToolFixup retained; IntelBTPatcher remains disabled. |
| Keyboard and touchpad | F1–F3 audio, non-NVIDIA F11/F12 brightness, ELAN gestures, F4 microphone mute, F7 radio control and F9 screen lock confirmed | F8 camera disablement is non-working and paused. Other retained observations remain in the keyboard guide. |
| USB | Applied 9-port map; internal Bluetooth/camera/fingerprint connections classified internal. USB-C 5 Gb/s in both orientations and both tested USB-A connectors 5 Gb/s/file reads confirmed | External USB 2 coverage and sustained throughput/reliability are separate measurements. |
| Internal PM981a | Runtime 512 GB NVMe, PCIe x4, SMART verified and TRIM active; Windows retained | Removing the obsolete config block is cleanup, not a claim that the previously available disk has just been repaired. |
| CPU and battery | X86PlatformPlugin active, 12 GB DDR4-2400 correctly described, battery detected with 296 cycles and health Good in the retained report | Capacity/reporting does not establish measured autonomy; sustained cooling and fan RPM remain open. |
| Lid, stop and wake | User confirms entering stop on lid close and resuming when opened | Ordinary lid behavior is confirmed; prolonged sleep, standby power and every peripheral's recovery are not measured by that statement. No repeat basic lid test is requested. |

Detailed evidence and dates remain in [Hardware](hardware.md), [CPU and thermals](cpu-thermal.md) and [Battery and sleep](battery-sleep.md). Working functions are not reopened merely because a later passive snapshot did not exercise them.

## Bundled NVIDIA development

The [single NVIDIA validation record](nvidia-validation.md) consolidates the completed checkpoints, exact source/native-run/package evidence and remaining admission gates. Counts are cumulative per checkpoint, not a sum of every version.

- **v9:** 486 target-kernel startup checks (258 CPU + 132 preparation + 96 services), complete cleanup and no warnings. Its 15 firmware-file checks are separate userspace evidence.
- **Idle loader ABI, October 20:** exact image load 0, valid idle snapshot and normal unload 0; original calls, provider preparations and PM registrations stayed zero. This does not establish original RM/GSP startup or runtime callback execution.
- **Next operational block, when resumed:** callback/target ABI closure, resource and allocation lifetime, thread/IRQ stack budgets, cancellation and cleanup within the real PM deadline, then actual original RM/GSP startup and ordered shutdown in one package/report.

The [idle-image workflow](../../.github/workflows/build-nvidia-idle-image.yml) is the default native workflow for its closed-loader milestone. The [extended development workflow](../../.github/workflows/check-nvidia-execution-development.yml) already groups its source/contract/fault/lifecycle/stack checks in one manual native job. Do not start another wrapper-specific laptop test or duplicate paid workflow; finished v4–v9 and idle checkpoints remain recorded without separate reruns. This status update launches no native CI or target test.

After a successful original adapter/GSP checkpoint, real GPU-command completion/readback is a distinct milestone. Graphics/userspace and Metal remain later work. No GPU acceleration is currently claimed.

## Function-key completion

Use the [existing keyboard mapping and evidence](../guides/function-keys.md), rather than assigning guessed scan codes or ACPI events. F1–F3 are working and complete, and F11/F12 brightness works in the non-NVIDIA EFI. F4, F7 and F9 have since been confirmed working with the companion. F8 is non-working and paused by request. The earlier F6 result remains historical evidence; this update requests no repeat test. Ordinary Fn+F1–F12 must remain available to applications.

The retained session-event investigation recorded all twelve Fn identities; direct/Fn F5 produced identical complete session events, direct F9 sent Command-L and direct F10 sent Command-P, while direct F4/F7/F8 produced no retained session event. The later bounded driver collection did not establish event-log visibility, so its empty windows do not prove absent hardware events or justify an ACPI remap. The guide keeps the exact per-key status and unresolved shortcut/session refresh boundary. These earlier diagnostic observations do not reopen F4/F7/F9 or the paused F8 investigation. Preserve the confirmed controls without repeating their completed checks.

## Retained refinements

The full DAC-range correction resolved quiet-output behavior during YouTube playback. Tonal equalisation remains deferred. Historical Internet-path results (concurrent 15.751/63.036 Mb/s down/up; sequential 78.762/81.610 Mb/s) remain in [Boot and network](../guides/boot-network.md); they do not isolate Wi-Fi radio throughput or establish a cause of loaded delay.

The old SSD-transfer helper stopped before backup/copy at its mounted-target guard. Manual EFI transfer and independent Samsung boot subsequently succeeded; that stopped helper is not the current operating procedure. Keep private identifiers, Wi-Fi credentials and original diagnostic archives outside the repository.

## References

- [NVIDIA validation and grouped checkpoints](nvidia-validation.md)
- [Pinned Linux-to-Darwin source assessment](../reference/nvidia-port-assessment.md)
- [Hardware status](hardware.md)
- [Function keys](../guides/function-keys.md)
