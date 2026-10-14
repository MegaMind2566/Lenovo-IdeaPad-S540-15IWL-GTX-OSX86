# Hardware roadmap

Goal: make all components of the Lenovo IdeaPad S540-15IWL GTX usable on macOS Tahoe. Each component requires testing on the device. NVIDIA research remains open and is planned after stabilising Intel graphics.

## Work order and retained backlog

The [CPU and passive sensor reports](cpu-thermal.md) confirm frequency/power response and fifteen consecutive valid idle temperatures at 45–48 °C. Loaded SMC sensor drivers are 1.3.8. The earlier load temperature gap remains unexplained; immediate repeat stress is deferred, and no sensor patch is inferred. The next implementation task is independent boot from the external 960 EVO using the current private working EFI. The remaining thermal and hardware items stay tracked below.

| Order | Work | Remaining scope |
|---|---|---|
| 1 | Graphics, power and thermals | Sustained Intel graphics use, temperatures under load, NVIDIA electrical power-off, incomplete SMC sensors, switching to battery and runtime. Electrical power-off is separate from driver-port research. |
| 2 | Boot and EFI consolidation | Preserve a private copy of the current working EFI, copy it to the external SSD's EFI partition, and establish boot without the HDD. Keep the HDD as a recovery path. Document a later release of the current configuration without replacing v0.1.0. |
| 3 | Storage and USB reliability | External SSD stability, USB-A/USB-C SuperSpeed, both USB-C orientations, reconnection, shutdown and reboot. |
| 4 | Audio peripherals and network throughput | Analog audio jack and Wi-Fi transfer-speed measurement. Wi-Fi network switching, Wi-Fi/Bluetooth disconnection and reconnection, and the Bluetooth headset microphone are confirmed working. Retain the working internal microphone correction. |
| 5 | External displays | HDMI and USB-C video operation and actual GPU routing before choosing display fixes. |
| 6 | Other peripherals | O2Micro SD reader and fingerprint-reader support. |
| Later | Deferred refinements | Remaining F4/F5/F7/F8/F9/F10 icon actions, Fn behavior after session refresh, audio equalization, lid/sleep/wake and peripheral recovery. |
| Research | Open compatibility work | Native macOS Wi-Fi integration and the NVIDIA Linux-driver port. Neither is treated as completed or discarded. |

The October 14 disk listing shows the source HDD as a 240.1 GB external GUID disk with one Microsoft Basic Data partition. The Samsung is a separate 250.1 GB external GUID disk with an existing 209.7 MB EFI system partition and APFS. The [SSD boot helper](../guides/ssd-boot.md) prepares the private working BOOT/OC transfer with backup and verification. The actual transfer and boot with the HDD disconnected remain pending.

Windows on the internal PM981a is retained. The current backlight, Intel framebuffer, audio/microphone and BrightnessKeys corrections are the baseline for subsequent work. Small verification tasks should be grouped around each implementation rather than repeatedly requesting unrelated diagnostic archives.

Priorities updated on 13 October 2026: the panel being off during boot is **resolved in the -igfxblr test, with the wait reduced from approximately two minutes to zero**. The current EFI is retained. On 14 October 2026, operation with Bluetooth headphones and HeliPort was also confirmed. The Photo Booth test shows an image and records voice; the gain defect led to the [microphone fix v2](../guides/microphone-fix.md), with an initial positive report after the reboot on 14 October 2026. The verification report and comparison recordings still need to be collected. Wi-Fi/Bluetooth disconnection and reconnection and Wi-Fi network switching are confirmed working. Network transfer speed remains unmeasured. The procedure is in [Boot and network](../guides/boot-network.md). Battery data and counters are [archived](battery-sleep.md); further sleep tests and equalisation are deferred. Remaining keyboard icon actions are deferred while core storage, boot, USB and display support take priority. Working audio, touchpad and brightness keys, together with the configured Fn shortcuts, are retained.

## Status and criteria

| Component | Current status | Required test |
|---|---|---|
| Tahoe boot | Desktop on the 960 EVO; panel delay eliminated in the test using only -igfxblr, reported wait zero | Retain the fix and verify repeatable shutdown/reboot in use |
| Intel UHD 620 | IntelAccelerator detected, Metal 3 exposed, shared memory up to 1536 MB; boot without VESA | Metal load and sustained use without freezes or artefacts |
| Keyboard | Direct F1–F3, F6 and F11/F12 working | Map the six remaining icon actions and preserve ordinary Fn+F1–F12 for applications |
| ELAN touchpad | F6 toggle and gestures confirmed working in use | Retain the current configuration; recovery after sleep remains part of the deferred wake checks |
| Intel AC9560 Wi-Fi | itlwm 2.3.0 and HeliPort working; disconnection, reconnection and network switching confirmed; Ethernet on en0 is expected with this driver | Transfer speed remains unmeasured; native Tahoe Wi-Fi integration is separate |
| Intel Bluetooth | Headphone playback, microphone, disconnection and reconnection confirmed; firmware loaded, correct NVRAM, IntelBTPatcher 2.4 excluded | Retain the current drivers; recovery after sleep belongs to the deferred wake checks |
| ALC257 audio | Playback, gradual volume adjustment and F1–F3 confirmed; microphone fix v2 received an initial positive report after reboot | Collect the verification report and recordings at different levels; equalisation deferred, jack and resume behaviour still to be documented |
| USB-A and USB-C | 9-port map verified; 960 EVO detected | USB 2/3, both USB-C connector orientations and reconnection |
| External Samsung 960 EVO | Enclosure connection restored; Tahoe reached the desktop | Sustained use without disconnections and resume from sleep |
| Internal PM981a NVMe | Visible in Recovery; retained for Windows | Check for any effects on macOS stability |
| Display and brightness | Internal 1920×1080 panel, brightness slider and direct F11/F12 working | Retain the BrightnessKeys companion fix; panel resume remains pending |
| CPU, battery and fans | X86PlatformPlugin active; CPU frequency/power response confirmed. Latest passive session: 15/15 valid temperatures, 45–48 °C; median estimated Intel package power 1.05 W. SMC sensor drivers 1.3.8 loaded. Earlier brief load 3.62 GHz and 43.83 W ended on a missing temperature reading. Battery detected at 100% on AC | Reliable load-temperature readings, fan telemetry, sustained cooling, dGPU status, switching to battery and runtime |
| Sleep | pmset records Sleep Count 1, User Wake Count 1 and Dark Wake Count 0; [data retained](battery-sleep.md) | Tests deferred: peripheral recovery, lid behaviour and extended sleep still to be verified |
| Webcam | Working; image capture confirmed alongside the internal microphone | Retain the current configuration; recovery after sleep remains part of the deferred wake checks |
| O2Micro SD reader | Identified; support to be assessed | Applicable driver and reading a card |
| Fingerprint reader | Internal USB port mapped; support to be assessed | Assess drivers and macOS integration |
| HDMI and USB-C video | Operation and routing not verified | Identify the GPU connected to each output and test an external monitor |
| NVIDIA GTX 1650 Max-Q | Linux port retained as research; no usable driver in the EFI | Milestones for initialisation, GPU execution and graphics integration |

Recovery test results are not automatically extended to the installed system. Incomplete items remain open until a documented result is available.

## Deferred function-key work

Complete **all function keys** according to the [keyboard mapping](../guides/function-keys.md). Direct audio, touchpad toggle and brightness controls work. All twelve Fn identities and the remaining targeted session events are recorded. Further driver-level investigation is deferred; no global remapping is applied.

Fn+F1–F12 must remain ordinary application function keys. Remove or reassign only the macOS shortcuts that consume those keys. F7 requires verified Wi-Fi and Bluetooth state; F8 needs a confirmed camera disable path. EFI v0.1.0 remains the earlier snapshot; the working BrightnessKeys companion package is retained separately.

## Deferred audio work

**ALC257 equalisation:** to be reviewed later. The positive result of 13 October 2026 confirms audio and volume after the v3 fix. The working configuration is retained for now; tonal refinement will be a separate test, without reopening the volume issue.

## NVIDIA research

The GTX 1650, PCI `10DE:1F91`, is listed among the GPUs compatible with NVIDIA's open source kernel modules. The repository contains operating system independent parts and Linux-specific interfaces. The modules also require GSP firmware and userspace driver components of the same version.

Mesa/NVK provides an open Vulkan driver for NVIDIA, but its current implementation requires Linux. Both foundations need assessment: neither is already a macOS driver for the GTX 1650.

The proposed path is a technical assessment, not an already validated port:

1. Study Linux dependencies, firmware and parts reusable on Darwin/IOKit.
2. Prepare a prototype for the PCI device, memory and interrupts on Intel macOS.
3. Test GPU initialisation and execution of a minimal command, with observable results on the laptop.
4. Assess the userspace component and the path towards Vulkan or other experimental functions.
5. Address Metal integration, the macOS graphics system, power management and video outputs separately.

A successful kernel prototype does not demonstrate desktop acceleration. The laptop's hybrid GPU configuration also requires verification of panel and output connections. Experimental tests will use an EFI separate from the one stabilised with Intel.

The EFI used for initial operation retains `-wegnoegpu`. Electrical power-off of the NVIDIA GPU and porting its driver are separate tasks. The optional SSDT that calls `_OFF` remains disabled until the firmware method's behaviour has been verified.

## References

- [NVIDIA: open GPU kernel modules and compatible GPUs](https://github.com/NVIDIA/open-gpu-kernel-modules)
- [Mesa: NVK, hardware support and Linux requirements](https://docs.mesa3d.org/drivers/nvk.html)
- [Acidanthera: WhateverGreen](https://github.com/acidanthera/WhateverGreen)
- [Dortania: Tahoe notes](https://dortania.github.io/OpenCore-Install-Guide/extras/tahoe.html)

## Function-key investigation retained for later

The BrightnessKeys companion fix now provides working direct F11/F12. F1–F3 audio controls and F6 touchpad toggle also work. F4/F5/F7/F8/F9/F10 remain open for a later keyboard stage. The configured ordinary Fn+F1–F12 path is retained. Event collection is read-only; unobserved scan codes or ACPI events will not be assigned speculative mappings.

All twelve Fn key identities are recorded. The [Fn shortcut setup](../../packages/function-keys-setup/README.md) has disabled the four existing plain F9–F12 macOS bindings; application behavior is pending the laptop's normal session refresh. Observer 1.1.1 completed seven targeted windows without interruption: direct and Fn F5 have identical complete session events, direct F9 sends Command-L, direct F10 sends Command-P, and direct F4/F7/F8 have no retained event.

The bounded driver collector stopped after three empty F4/F5/Fn+F5 windows because its F5 positive controls did not verify log visibility. Logging restoration is confirmed. This result does not identify any missing hardware event or justify a key mapping. Additional keyboard diagnostics are deferred. Only a demonstrated input distinction can justify a global remap. Browser-specific F5 Reload is also possible without changing its ordinary function-key identity; no browser override has been applied. Missing PS/2 observations would lead to a separate guarded VPC investigation, not a guessed ACPI patch.

