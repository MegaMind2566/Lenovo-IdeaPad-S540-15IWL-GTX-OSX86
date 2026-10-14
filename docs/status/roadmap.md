# Hardware roadmap

Goal: make all components of the Lenovo IdeaPad S540-15IWL GTX usable on macOS Tahoe. Each component requires testing on the device. NVIDIA research remains open and is planned after stabilising Intel graphics.

## Test order

1. Retain a private copy of the current EFI: the Tahoe desktop has been reached on the external 960 EVO.
2. Complete UHD 620 stability tests following [Intel graphics](../guides/intel-graphics.md); IntelAccelerator and exposed Metal 3 support are already confirmed.
3. Verify peripherals, networking, USB and audio in the installed system.
4. Complete brightness, power management, sleep and reboot checks.
5. Transfer the current EFI to the 960 EVO and test booting without the HDD, retaining the working boot medium as a fallback.
6. Start NVIDIA research and verify video outputs according to the identified hardware paths.

Priorities updated on 13 October 2026: the panel being off during boot is **resolved in the -igfxblr test, with the wait reduced from approximately two minutes to zero**. The current EFI is retained. On 14 October 2026, operation with Bluetooth headphones and HeliPort was also confirmed. The Photo Booth test shows an image and records voice; the gain defect led to the [microphone fix v2](../guides/microphone-fix.md), with an initial positive report after the reboot on 14 October 2026. The verification report and comparison recordings still need to be collected. Network speed and reconnection remain unresolved. The procedure is in [Boot and network](../guides/boot-network.md). Battery data and counters are [archived](battery-sleep.md); further sleep tests are deferred, together with the previously recorded function key work and equalisation.

## Status and criteria

| Component | Current status | Required test |
|---|---|---|
| Tahoe boot | Desktop on the 960 EVO; panel delay eliminated in the test using only -igfxblr, reported wait zero | Retain the fix and verify repeatable shutdown/reboot in use |
| Intel UHD 620 | IntelAccelerator detected, Metal 3 exposed, shared memory up to 1536 MB; boot without VESA | Metal load and sustained use without freezes or artefacts |
| Keyboard | Works in Recovery | Use in the installed system and function keys |
| ELAN touchpad | Drivers present; the reported “mouse” does not identify the device | Pointing, clicking, scrolling and gestures |
| Intel AC9560 Wi-Fi | itlwm 2.3.0 loaded, Ethernet on en0 is expected with this driver; HeliPort reported working | Speed, network switching and reconnection; native Tahoe Wi-Fi integration is separate |
| Intel Bluetooth | Operation with headphones confirmed; firmware loaded, correct NVRAM, IntelBTPatcher 2.4 excluded | Headphone microphone and reconnection still to be tested; retain the current drivers |
| ALC257 audio | Playback, gradual volume adjustment and F1–F3 confirmed; microphone fix v2 received an initial positive report after reboot | Collect the verification report and recordings at different levels; equalisation deferred, jack and resume behaviour still to be documented |
| USB-A and USB-C | 9-port map verified; 960 EVO detected | USB 2/3, both USB-C connector orientations and reconnection |
| External Samsung 960 EVO | Enclosure connection restored; Tahoe reached the desktop | Sustained use without disconnections and resume from sleep |
| Internal PM981a NVMe | Visible in Recovery; retained for Windows | Check for any effects on macOS stability |
| Display and brightness | Internal 1920×1080 panel and brightness slider working; F11/F12 do not work in the reported test | F11/F12 deferred to the function key batch; panel resume still to be tested |
| CPU, battery and fans | X86PlatformPlugin active; idle 45–46 °C and estimated Intel power of 0.80–0.95 W; fan quiet. Battery detected at 100% on AC. Incomplete SMC telemetry | Temperatures under load, dGPU status, switching to battery power and battery runtime |
| Sleep | pmset records Sleep Count 1, User Wake Count 1 and Dark Wake Count 0; [data retained](battery-sleep.md) | Tests deferred: peripheral recovery, lid behaviour and extended sleep still to be verified |
| Webcam | Image present in the Photo Booth test of 14 October 2026 | Sustained use and resume still to be verified |
| O2Micro SD reader | Identified; support to be assessed | Applicable driver and reading a card |
| Fingerprint reader | Internal USB port mapped; support to be assessed | Assess drivers and macOS integration |
| HDMI and USB-C video | Operation and routing not verified | Identify the GPU connected to each output and test an external monitor |
| NVIDIA GTX 1650 Max-Q | Linux port retained as research; no usable driver in the EFI | Milestones for initialisation, GPU execution and graphics integration |

Recovery test results are not automatically extended to the installed system. Incomplete items remain open until a documented result is available.

## Function keys: next diagnostic batch

Verify and fix **all function keys** together, including F11/F12 for brightness, Fn behaviour and the other functions available on the keyboard. This work was deferred on 13 October 2026. Following the first EFI release, the next step is the [read-only function-key collector](../../packages/function-keys/README.md), beginning with F11/F12 and preserving the working audio keys. No additional EFI patch has been applied.

F1–F3 for mute and volume are already reported working and must be preserved. The macOS brightness slider works. Fn+F11/F12 and possible ACPI handling with BrightnessKeys will be assessed in the complete batch before choosing the required changes.

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
