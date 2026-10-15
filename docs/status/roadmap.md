# Hardware roadmap

Goal: make all components of the Lenovo IdeaPad S540-15IWL GTX usable on macOS Tahoe. Each component requires testing on the device. NVIDIA research remains open and is planned after stabilising Intel graphics.

## Work order and retained backlog

The [CPU and sensor reports](cpu-thermal.md) confirm frequency/power response and complete temperature readings both at idle (45–48 °C) and during desktop activity (57–82 °C). The activity report retains a simultaneous maximum of 82 °C, estimated Intel package power 35.62 W and average system frequency 3.44 GHz, followed by a final 57 °C. Thermal pressure remains Nominal. Loaded SMC sensor drivers are 1.3.8. The earlier isolated load-temperature gap remains unexplained but did not recur in this continuous activity session; sustained cooling and fan RPM remain open, with no sensor patch inferred. Independent boot from the external 960 EVO is now confirmed after manual transfer of the private working EFI. The Samsung/RTL9210 connection reports 5 Gb/s in both USB-C connector orientations. Battery Power and discharge are reported after AC removal. Wired-headphone output, automatic return to speakers and wired-headset microphone input are confirmed. HDMI produces no image, and macOS enumerates only the internal panel. External-display work is paused by request. HDMI GPU routing remains unresolved, and USB-C video is not advertised in the exact GTX specification and cannot currently be tested. The subsequent two-port USB-A check reports the same Initio enclosure at 5 Gb/s on both tested connectors, while the Samsung remains enumerated at 5 Gb/s. File access was subsequently confirmed working on both USB-A connectors. External USB 2 device coverage, sustained storage reliability and measured battery runtime remain open. The remaining thermal and hardware items stay tracked below.

| Order | Work | Remaining scope |
|---|---|---|
| Now | NVIDIA Darwin OS adapter | Clock, ordinary-RAM primitives and unchanged NVIDIA atomic-header integration passed combined kernel compile/link/import and native userspace checks. No kernel runtime validation or CPU-only laptop package. Laptop tests combine components; full validation follows the implementation stages. Confirmed v0.3.0 transport unchanged. |
| Remaining | Graphics, power and thermals | Sustained Intel graphics use and cooling, fan telemetry and measured battery runtime. Continuous temperature readings during desktop activity and basic battery power/discharge reporting are confirmed. NVIDIA electrical power-off is deferred until after the driver-port attempt. |
| Complete / retained | Boot and EFI consolidation | Independent Samsung boot confirmed after manual EFI transfer. Keep the HDD as a recovery path and preserve the private working EFI. A later sanitized release remains separate from v0.1.0. |
| 3 | Storage and USB reliability | USB-C at 5 Gb/s in both orientations and both tested USB-A connectors at 5 Gb/s are confirmed. File reads on both USB-A connectors are confirmed. External USB 2 devices, sustained SSD stability, shutdown and reboot remain separate checks. Move the system SSD cable only after shutdown. |
| Complete / retained | Quiet output volume | Full DAC-range correction reported working during YouTube playback on October 15. Retain the correction; equalisation remains deferred. |
| Recorded | Network performance | Concurrent baseline 15.751/63.036 Mb/s down/up; sequential 78.762/81.610 Mb/s. Sequential responsiveness: uplink Low (684.383 ms), downlink Medium (144.830 ms). The cause of the path delay is unresolved; retain the working Wi-Fi driver. |
| Paused | External displays | HDMI produces no image and macOS lists only the internal panel. A Windows GPU-routing check is retained for when this work resumes. USB-C video cannot currently be tested; hardware capability remains unverified. |
| 6 | Other peripherals | O2Micro SD reader and fingerprint-reader support. |
| Later | Deferred refinements | Remaining F4/F5/F7/F8/F9/F10 icon actions, Fn behavior after session refresh, audio equalization, lid/sleep/wake and peripheral recovery. NVIDIA electrical power-off follows the driver-port attempt. |
| Research | Open compatibility work | Native macOS Wi-Fi integration and the NVIDIA Linux-driver port. Neither is treated as completed or discarded. |

The October 14 disk listing shows the source HDD as a 240.1 GB external GUID disk with one Microsoft Basic Data partition. The Samsung is a separate 250.1 GB external GUID disk with an existing 209.7 MB EFI system partition and APFS. The current private EFI was copied manually, and independent Samsung boot is confirmed following the HDD-disconnected procedure. The [transfer helper](../guides/ssd-boot.md) stopped at its initial mounted-target guard before backup or copy; that helper is on hold pending identification of the failed condition.

Windows on the internal PM981a is retained. The current backlight, Intel framebuffer, audio/microphone and BrightnessKeys corrections are the baseline for subsequent work. Small verification tasks should be grouped around each implementation rather than repeatedly requesting unrelated diagnostic archives.

Priorities updated on 13 October 2026: the panel being off during boot is **resolved in the -igfxblr test, with the wait reduced from approximately two minutes to zero**. The current EFI is retained. On 14 October 2026, operation with Bluetooth headphones and HeliPort was also confirmed. The Photo Booth test shows an image and records voice; the gain defect led to the [microphone fix v2](../guides/microphone-fix.md), with a positive report after the reboot. Internal, Bluetooth and wired-headset microphones are now confirmed working; further audio refinement is deferred. Wi-Fi/Bluetooth disconnection and reconnection and Wi-Fi network switching are confirmed working. The first concurrent Internet-path baseline is recorded below; isolated Wi-Fi throughput and the cause of the loaded delay remain unresolved. The procedure is in [Boot and network](../guides/boot-network.md). Battery data and counters are [archived](battery-sleep.md); further sleep tests and equalisation are deferred. Remaining keyboard icon actions are deferred while core storage, boot, USB and display support take priority. Working audio, touchpad and brightness keys, together with the configured Fn shortcuts, are retained.

## Status and criteria

| Component | Current status | Required test |
|---|---|---|
| Tahoe boot | Independent boot from the external Samsung, with OpenCore on its EFI partition; boot blackout corrected by -igfxblr | Retain the working EFI and verify repeatable shutdown/reboot in use |
| Intel UHD 620 | IntelAccelerator detected, Metal 3 exposed, shared memory up to 1536 MB; boot without VESA | Metal load and sustained use without freezes or artefacts |
| Keyboard | Direct F1–F3, F6 and F11/F12 working | Map the six remaining icon actions and preserve ordinary Fn+F1–F12 for applications |
| ELAN touchpad | F6 toggle and gestures confirmed working in use | Retain the current configuration; recovery after sleep remains part of the deferred wake checks |
| Intel AC9560 Wi-Fi | itlwm 2.3.0 and HeliPort working; disconnection, reconnection and network switching confirmed; Ethernet on en0 is expected with this driver | Internet baseline recorded; sequential result 78.762 Mb/s down / 81.610 Mb/s up with Low uplink and Medium downlink responsiveness. Isolated Wi-Fi throughput and native Tahoe integration remain separate |
| Intel Bluetooth | Headphone playback, microphone, disconnection and reconnection confirmed; firmware loaded, correct NVRAM, IntelBTPatcher 2.4 excluded | Retain the current drivers; recovery after sleep belongs to the deferred wake checks |
| ALC257 audio | Speaker/headphone output, automatic switching, wired-headset input and F1–F3 confirmed; internal microphone fix v2 retained; quiet-volume correction confirmed during YouTube playback | Retain the full DAC-range correction; equalisation and resume checks deferred |
| USB-A and USB-C | 9-port map verified; Samsung/RTL9210 at 5 Gb/s in both USB-C orientations; Initio enclosure at 5 Gb/s on both tested USB-A connectors | External USB 2 devices and sustained storage use; SuperSpeed links and file reads are confirmed for both USB-A connectors |
| External Samsung 960 EVO | Independent boot confirmed; current enclosure link 5 Gb/s | Sustained storage use without disconnections and measured throughput; resume remains part of deferred wake checks |
| Internal PM981a NVMe | Visible in Recovery; retained for Windows | Check for any effects on macOS stability |
| Display and brightness | Internal 1920×1080 panel, brightness slider and direct F11/F12 working | Retain the BrightnessKeys companion fix; panel resume remains pending |
| CPU, battery and fans | X86PlatformPlugin active; idle temperatures 45–48 °C and median estimated Intel package power 1.05 W. Activity session: 15/15 valid temperatures, 57–82 °C; simultaneous recorded maximum 82 °C, 35.62 W and 3.44 GHz; final 57 °C. Nominal pressure throughout. SMC drivers 1.3.8 loaded. Battery Power at 100%, discharging after AC removal | Fan telemetry, sustained cooling, dGPU status and measured battery runtime; the earlier isolated missing load sample remains unexplained |
| Sleep | pmset records Sleep Count 1, User Wake Count 1 and Dark Wake Count 0; [data retained](battery-sleep.md) | Tests deferred: peripheral recovery, lid behaviour and extended sleep still to be verified |
| Webcam | Working; image capture confirmed alongside the internal microphone | Retain the current configuration; recovery after sleep remains part of the deferred wake checks |
| O2Micro SD reader | Identified; support to be assessed | Applicable driver and reading a card |
| Fingerprint reader | Internal USB port mapped; support to be assessed | Assess drivers and macOS integration |
| HDMI | No image; macOS display report lists only the internal panel | Identify the connected external display's owning GPU in Windows before selecting a fix |
| USB-C video | No video test available; video capability and routing not verified; USB data works | Check hardware capability from documentation; keep separate from the observed HDMI failure |
| NVIDIA GTX 1650 Max-Q | Probe 0.1.0 attachment, 0.2.0 BOOT_0 read and 0.3.0 two-read/local HAL table match confirmed; no HAL instance or initialized GPU | Clock, memory and atomic combined GitHub checks passed; continue OS-adapter development in GitHub. Confirmed transport unchanged. Kernel runtime, stop/unload, resource-manager integration, DMA, startup, execution and graphics integration remain separate |

Recovery test results are not automatically extended to the installed system. Incomplete items remain open until a documented result is available.

## Deferred function-key work

Complete **all function keys** according to the [keyboard mapping](../guides/function-keys.md). Direct audio, touchpad toggle and brightness controls work. All twelve Fn identities and the remaining targeted session events are recorded. Further driver-level investigation is deferred; no global remapping is applied.

Fn+F1–F12 must remain ordinary application function keys. Remove or reassign only the macOS shortcuts that consume those keys. F7 requires verified Wi-Fi and Bluetooth state; F8 needs a confirmed camera disable path. EFI v0.1.0 remains the earlier snapshot; the working BrightnessKeys companion package is retained separately.

## Deferred audio work

**ALC257 equalisation:** to be reviewed later. Both the earlier mute-only defect and the later excessively loud quiet end are resolved. The [full DAC-range correction](../guides/volume-control.md) was reported working during YouTube playback and is retained. Tonal refinement remains deferred.

## NVIDIA research

The [pinned source assessment](../reference/nvidia-port-assessment.md) is complete. It records release 615.78.08, the concrete Linux-to-Darwin boundaries and acceptance criteria. The [native PCI inventory](../../packages/nvidia-pci/README.md) now confirms an active `10DE:1F91` service, subsystem `17AA:3806`, revision `A1`, below `RP05`, with `-wegnoegpu` absent and no warnings. The earlier report found no target with the argument present. The automatic [visibility helper](../../packages/nvidia-visibility/README.md) stopped at its `Mounted` check before changes; the argument was subsequently removed manually. The latest reports establish visibility without auditing the full current EFI. The helper is superseded for this reached milestone.

The bounded IOKit PCI attachment prototype 0.1.0 returns `attached`, `complete=true` and no warnings on the laptop. Its reporter verifies the actual `IOPCIDevice` provider: `10DE:1F91`, subsystem `17AA:3806`, revision `A1`, display class `030000`, with `-wegnoegpu` absent. Fixed configuration reads and assigned resource descriptors are confirmed. The descriptors report 16 MiB, 256 MiB, 32 MiB and 128 bytes; they do not establish usable VRAM or MMIO access.

On October 15, version 0.2.0 returned `identified`, `complete=true` and no warnings on the laptop. The format-2 snapshot records exactly one 32-bit read of the documented read-only `NV_PMC_BOOT_0` register at BAR0 offset zero, with architecture `0x16`, implementation `0x07` and reason `tu117-identified`. This confirms that single identification read, not GPU initialization or general register access.

On October 15, version 0.3.0 returned `hal_matched`, `complete=true` and no warnings on the laptop. It completed one BOOT_0 and one BOOT_42 read, two total. Both decode to architecture `0x16` and implementation `0x07`; BOOT_42 chip `0x167` matches the pinned local table for TU117 variant `41`. This confirms two read-only identification loads and local table matching. It does not instantiate NVIDIA's HAL, integrate its resource manager or initialize the GPU.

The next stage is the separate CPU-only Darwin OS adapter. The confirmed v0.3.0 transport is unchanged, and no additional GPU register or operation is selected. All build and CPU behavior checks run in GitHub; laptop tests are reserved for combined integration milestones. DMA, firmware loading and acceleration remain unimplemented. Runtime stop/unload remains untested. Intel display operation and the recovery EFI are retained.

The [OS foundations](../../packages/nvidia-os-adapter/README.md) retain the validated clock backend and add ordinary-RAM copy/set/compare hooks, four adapted release-profile memory callers with 64-bit chunk bridges, and the unchanged NVIDIA atomic-header closure under GNU C11 and C++17. [Combined GitHub checks passed](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/actions/runs/38696607911): kernel compile/link with both atomic language consumers, exact import audit, native callers, C/C++ atomic semantics and multithreaded checks, and instrumented memory-backend execution. No buffers larger than 4 GiB are executed; only their chunk-plan boundaries are checked. Allocation, user-copy and GPU operations remain outside this component. Kernel runtime, suspend behavior and resource-manager integration remain unvalidated; clock deadlines cannot make a stalled MMIO load recoverable.

The GTX 1650, PCI `10DE:1F91`, is listed among the GPUs compatible with NVIDIA's open source kernel modules. The repository contains operating system independent parts and Linux-specific interfaces. The modules also require GSP firmware and userspace driver components of the same version.

Mesa/NVK provides an open Vulkan driver for NVIDIA, but its current implementation requires Linux. Both foundations need assessment: neither is already a macOS driver for the GTX 1650.

The proposed path is a technical assessment, not an already validated port:

1. Source assessment complete: pinned Linux dependencies, firmware/userspace requirements and candidate reusable code are recorded in the assessment.
2. PCI visibility, probe 0.1.0 attachment/configuration/resource reads, 0.2.0 BOOT_0 identification and 0.3.0 BOOT_42/local HAL table matching complete on the laptop. Develop and validate the CPU-only OS-adapter components in GitHub; reserve laptop checks for combined milestones before widening scope. Stop/unload remains untested; DMA and interrupts require separate work.
3. Test GPU initialisation and execution of a minimal command, with observable results on the laptop.
4. Assess the userspace component and the path towards Vulkan or other experimental functions.
5. Address Metal integration, the macOS graphics system, power management and video outputs separately.

A successful kernel prototype does not demonstrate desktop acceleration. The laptop's hybrid GPU configuration also requires verification of panel and output connections. Experimental tests will use an EFI separate from the one stabilised with Intel.

The EFI used for initial operation retained `-wegnoegpu`; the latest inventory confirms it is absent in the visibility boot. Electrical power-off of the NVIDIA GPU and porting its driver are separate tasks. By request, electrical power-off work is deferred until after the driver-port attempt. The optional SSDT that calls `_OFF` must stay disabled for transport work; the latest inventory does not audit ACPI table configuration. The [firmware review](../reference/acpi-patch-review.md) identifies an unbounded wait for `LNKS=0` before the power-gate writes, plus a separate conditional power-resource sequence. A correct method path and absent GPU IOService do not establish safe execution or electrical power-off.

## References

- [NVIDIA: open GPU kernel modules and compatible GPUs](https://github.com/NVIDIA/open-gpu-kernel-modules)
- [Mesa: NVK, hardware support and Linux requirements](https://docs.mesa3d.org/drivers/nvk.html)
- [Acidanthera: WhateverGreen](https://github.com/acidanthera/WhateverGreen)
- [Dortania: Tahoe notes](https://dortania.github.io/OpenCore-Install-Guide/extras/tahoe.html)

## Function-key investigation retained for later

The BrightnessKeys companion fix now provides working direct F11/F12. F1–F3 audio controls and F6 touchpad toggle also work. F4/F5/F7/F8/F9/F10 remain open for a later keyboard stage. The configured ordinary Fn+F1–F12 path is retained. Event collection is read-only; unobserved scan codes or ACPI events will not be assigned speculative mappings.

All twelve Fn key identities are recorded. The [Fn shortcut setup](../../packages/function-keys-setup/README.md) has disabled the four existing plain F9–F12 macOS bindings; application behavior is pending the laptop's normal session refresh. Observer 1.1.1 completed seven targeted windows without interruption: direct and Fn F5 have identical complete session events, direct F9 sends Command-L, direct F10 sends Command-P, and direct F4/F7/F8 have no retained event.

The bounded driver collector stopped after three empty F4/F5/Fn+F5 windows because its F5 positive controls did not verify log visibility. Logging restoration is confirmed. This result does not identify any missing hardware event or justify a key mapping. Additional keyboard diagnostics are deferred. Only a demonstrated input distinction can justify a global remap. Browser-specific F5 Reload is also possible without changing its ordinary function-key identity; no browser override has been applied. Missing PS/2 observations would lead to a separate guarded VPC investigation, not a guessed ACPI patch.

