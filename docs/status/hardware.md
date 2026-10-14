# Hardware verified from the lenovo.HTM report

Report received on 12 October 2026. Only data relevant to the project is included.

| Item | Reported data | macOS status |
|---|---|---|
| Model | Lenovo IdeaPad S540-15IWL GTX, 81SW family | Tahoe reached the desktop on the external 960 EVO |
| Motherboard | Lenovo LNVNB161216 | DSDT and 12 SSDTs analysed |
| BIOS | BWCN19WW, 26 May 2021 | UEFI present; Secure Boot disabled in the report |
| CPU | Intel Core i7-8565U, Whiskey Lake-U, 4 cores / 8 threads | X86PlatformPlugin active; two idle samples with low estimated Intel power consumption and CPU temperature of 45–46 °C |
| RAM | 12 GB DDR4-2400, 8 and 4 GB modules | Sufficient for the first test |
| iGPU | Intel UHD 620, PCI 8086:3EA0 | IntelAccelerator detected and Metal 3 exposed; sustained load still to be tested |
| dGPU | NVIDIA GTX 1650 Max-Q 4 GB, PCI 10DE:1F91 | Driver disabled in the EFI; Linux port retained in the roadmap; electrical power-off still to be verified |
| Display | BOE NV156FHM-N61, 1920×1080 | Panel, brightness slider and direct F11/F12 working; boot blackout delay eliminated with -igfxblr |
| NVMe | Samsung MZVLB512HBJQ-000L2, 512 GB, firmware 3L1QEXF7 | Problematic PM981a family; compatibility is not assumed |
| Wi-Fi | Intel Wireless-AC 9560, PCI 8086:9DF0 | itlwm 2.3.0 loaded and HeliPort reported working; Ethernet presentation is expected with this driver; speed and reconnection still to be tested |
| Bluetooth | Intel, USB 8087:0AAA | Operation with headphones confirmed; firmware loaded, correct NVRAM and IntelBTPatcher excluded; headphone microphone and reconnection still to be tested |
| Audio | Intel cAVS 8086:9DC8; Realtek ALC257, 10EC:0257 | Playback, gradual volume adjustment and F1–F3 confirmed with VoodooHDA 3.6.8 and the v3 fix; microphone fix v2 received an initial positive report after reboot; verification report and comparison recordings still to be collected; equalisation deferred, jack operation still to be documented |
| Keyboard | PS/2 | VoodooPS2; direct F1–F3, F6 and F11/F12 working; remaining icon keys and Fn app-key behavior in progress |
| Touchpad | ELAN0662, I2C HID; Intel 8086:9DE8 controller | Confirmed path: `_SB.PCI0.I2C0.TPD0`; F6 toggle working; gestures remain to be documented |
| SD reader | O2Micro SD Host Controller | Support still to be verified; different from the reader in the lucatek project |
| Webcam | TwinHan Integrated Camera USB | Image present in the Photo Booth test; sustained use and resume still to be verified |

The Windows integrated graphics driver name reports UHD 610, but the chip and PCI ID in the report identify UHD 620. The configuration will be based on the actual chip.

## Data collected after the report

- One DSDT, 12 SSDTs and 7 other relevant tables: all checked for length, checksum and SHA-256.
- Realtek ALC257 audio on Intel SST, `INTELAUDIO\\FUNC_01&VEN_10EC&DEV_0257`.
- ELAN0662 touchpad at `_SB.PCI0.I2C0.TPD0`.
- dGPU: `_SB.PCI0.RP05.PXSX`; native `_OFF` method present in SSDT9.
- Internal NVMe: PCI `PciRoot(0x0)/Pci(0x1D,0x0)/Pci(0x0,0x0)`, consistent with `_SB.PCI0.RP09.PXSX`.
- Samsung 960 EVO for the macOS test: external USB-C connection confirmed; capacity not stated in the received documentation.

## Data still needed

- USB-C SuperSpeed operation and both connector orientations: a 9-port map has been received and verified.
- Component test results in the [roadmap](roadmap.md).

Tahoe reached the desktop on the external Samsung 960 EVO after the framebuffer memory fix. IntelAccelerator and exposed Metal 3 support are confirmed; sustained graphics load, audio, battery runtime, sleep and HDMI remain to be verified. No overall compatibility rating is assigned before testing.

## Desktop and Intel graphics: 13 October 2026

The graphics report from the installed system exposes UHD 620 with device-id `0x3ea5`, Metal 3 and dynamic shared graphics memory up to 1536 MB. The internal panel is online at 1920×1080. The powermetrics sample detects IntelAccelerator and boot-args without `-igfxvesa` or `-x`. The fix and the limits of the checks are documented in [Intel framebuffer memory](../../archive/first-boot/docs/intel-memory-test.md) and [Intel graphics](../guides/intel-graphics.md).

A sample lasting approximately one second reports a CPU temperature of 50 °C and estimated Intel package power of 0,98 W. This is an instantaneous measurement: it does not verify NVIDIA status, fan operation or battery runtime. Electrical power-off of the dGPU remains unresolved.

## CPU power management and idle samples: 13 October 2026

IORegistry shows X86PlatformPlugin as registered, matched and active. After the request to leave the laptop idle, two powermetrics samples were provided, each covering a five-second interval:

| Item | First sample | Second sample |
|---|---|---|
| Estimated Intel package power, CPU + iGPU + system agent | 0,95 W | 0,80 W |
| CPU temperature reported at the end of the interval | 46 °C | 45 °C |
| Reported average system frequency | 947,43 MHz | 965,75 MHz |
| Reported active iGPU frequency | 300 MHz | 300 MHz |

The CPU power management driver is therefore active, and the samples show low estimated Intel power consumption at idle. The temperatures are instantaneous readings at the end of each interval. The GPU figure of 100% is relative to the stated nominal frequency of 300 MHz; it is not a measurement of 100% GPU utilisation.

The report still contains Invalid key detected and does not report fan RPM: SMC telemetry remains incomplete. It was subsequently reported that the fan had been quiet for some time, so the idle behaviour is also supported by observation of the laptop. These data do not verify temperatures under load, NVIDIA power consumption or electrical power-off, battery operation or sleep. The plugin's LastSleepType fields do not constitute evidence of successful sleep.

## Panel fix and Bluetooth status: 13 October 2026

The test using only `-igfxblr` eliminated the boot blackout in the reported result: from approximately two minutes to zero. The configuration is retained, preserving Intel memory settings, audio and SIP. The report preceding the test shows the same framebuffer UUID and Loginwindow ready approximately 31,3 seconds after the kernel. The [diagnosis](../guides/boot-network.md) distinguishes the panel delay from the system boot time.

Bluetooth status is On, FirmwareLoaded is Yes and the transport is connected; BlueToolFixup 2.7.2 and IntelBluetoothFirmware 2.4 are loaded, while IntelBTPatcher is absent. The two required NVRAM variables are present with the correct values: one zero byte and fourteen zero bytes. The stack starts scanning and receives BLE devices. On 14 October 2026, operation with Bluetooth headphones was reported, together with HeliPort operation for Wi-Fi network management. The current drivers and NVRAM are retained. This result does not verify the headphone microphone, the internal ALC257 microphone, the analogue jack or reconnection after sleep.

## Webcam and voice capture: 14 October 2026

In the suggested Photo Booth test, it was reported that the image was visible and voice was recorded. Microphone gain was too high: subsequent adjustment abruptly changed it from too high to too low. The selected input and mixer controls need to be checked before making a change. The webcam therefore works in this test; the audio input level has not yet been confirmed as correct. This result predates the microphone fix described below.

## Microphone fix: 14 October 2026

On 14 October 2026, after testing the **S540-microfono-fix-v2** package and rebooting, an initial positive result was reported. The verification report and comparison recordings have not yet been collected. This version is retained together with the backup of the previous driver; equalisation and function keys remain deferred.

The [test](../guides/microphone-fix.md) uses VoodooHDA 3.6.9, S540 variant: the input slider controls the ADC's 64 levels, microphone boost remains at 0 dB and the speaker PCM volume retains the v3 fix. The v2 package removes the installer's dependency on Xcode tools. CI checks for format, integrity, signature and restoration passed; the initial usage report is not extended to the jack or recovery after sleep.

## Battery and sleep counters: 13 October 2026

The pmset sample shows an internal battery present, 100%, charged and AC Power supply. The system counters are Sleep Count 1, User Wake Count 1 and Dark Wake Count 0. Settings and limitations are retained in [Battery and sleep](battery-sleep.md): switching to battery power, battery runtime and full peripheral recovery have not yet been verified. Further sleep tests are deferred, with priority given to the panel being off during boot, Bluetooth and Wi-Fi management.

## Panel and brightness keys: 13 October 2026

The macOS slider actually adjusts panel brightness. F11/F12 do not work in the reported test; the result with Fn has not yet been specified. Backlight control therefore works, and no new PNLF or framebuffer patches are added solely for the key issue.

The original DSDT contains H_EC._Q8E and _Q8F methods that send ACPI notifications 0x86 and 0x87 to the GFX0.DD1F panel, with firmware conditions that may suppress some events. At the user's request, work on F11/F12 has been deferred to a single batch with the other function keys. That stage will check Fn behaviour and the generated events, then assess BrightnessKeys as a targeted candidate; it has not been applied. Working F1–F3 and the brightness slider are preserved. The _Q methods are not renamed in advance.

## Function-row mapping: 14 October 2026

The keyboard image and reported actions establish the complete target in [Function keys](../guides/function-keys.md). Direct F1 mute, F2/F3 volume, F6 touchpad toggle and F11/F12 brightness are working. F4 microphone mute, F5 page reload, F7 airplane mode, F8 camera disable, F9 lock screen and F10 display selection remain pending.

Fn+F1–F12 must deliver ordinary function keys to applications. macOS Desktop or Mission Control activation is not the desired Fn behavior. Distinct direct/Fn input events and relevant macOS shortcut assignments will be recorded before changing mappings. The BrightnessKeys companion fix is retained; EFI v0.1.0 remains the earlier published snapshot without this driver.

## Audio from the desktop: 13 October 2026

`system_profiler SPAudioDataType` exposes no devices. Of the searched kexts, only Lilu 1.7.2 is loaded: AppleALC and AppleHDA are absent from the list. The configuration excludes AppleALC beyond Darwin 24; Tahoe removed AppleHDA. A [reversible VoodooHDA 3.6.8 test](../guides/tahoe-audio.md) was prepared in Library/Extensions, with layout 11 included for ALC257. After correcting the SIP check, audio playback and F1–F3 operation were reported. The initial volume defect, with a noticeable change only at zero/mute, was resolved after the v3 test with VoodooHDAEnableVolumeChangeFix=true. A positive result was reported for playback and gradual adjustment. Equalisation is recorded for later refinement; jack, microphone and resume behaviour remain to be documented. Restoring AppleHDA to the system volume remains a later strategy.

The following sections describe attempts made before reaching the desktop.

## Result of the first Recovery test

On 13 October 2026, reaching the language selection screen and operation of the mouse, keyboard and Wi-Fi in Recovery were reported. It was not specified whether the reported mouse was the touchpad or a USB device: the ELAN touchpad still needs separate verification.

The result was reported after the proposed `-igfxvesa` test. The actual boot-args were not collected, so the result cannot yet be attributed to that parameter with certainty. Reaching Recovery does not demonstrate Metal acceleration or full compatibility of the installed system. The [Intel checks](../guides/intel-graphics.md) start from these data after installation.

## External drive detection and preference for the internal drive

The 960 EVO did not appear because the M.2 module had come loose inside its enclosure. After it was reseated, drive detection was reported. This result resolves the observed detection issue; it does not yet confirm SuperSpeed operation or both USB-C connector orientations.

The internal drive was reported visible in Recovery: exclusion through the NVMe driver block was not verified in this test. The user requested that the Windows drive remain in place and that work proceed on the external 960 EVO. No initialisation or partition changes were performed on the internal drive. Subsequent tests will assess any stability issues.

## OpenCore log from 02:45

The log from 13 October 2026 confirms selection of the external USB volume, named **Machintosh SSD**, and the presence of `-igfxvesa` and `-x`. OpenCore reports successful injection of Lilu 1.7.2 and WhateverGreen 1.7.1 and the application of Intel properties. The log does not confirm driver initialisation in the kernel or Metal support. The desktop had not yet been reached in that attempt.

The [log analysis](../../archive/first-boot/docs/boot-log-analysis.md) also records the Apple path with a BaseSystem image, the absence of the MAT table and the limitations of the NVMe block. The original file and SMBIOS identifiers are not added to the repository.

## Subsequent USB/Bluetooth panic

The photograph received afterwards shows an actual panic with the `bluetoothd` process, IOUSBHostFamily and IntelBTPatcher 2.4 extensions in the backtrace, Darwin 25.6.0 and macOS build 25G241. The visible boot-args do not include `-x`, while `-igfxvesa` remains. The panic header is outside the frame, so the precise cause still needs confirmation.

The [Bluetooth test](../guides/bluetooth.md) excludes only IntelBTPatcher from the current EFI. Version 2.4 predates the official USB memory descriptor handling fix for Sequoia and later; the builder excludes it from new EFIs. Intel firmware, BlueToolFixup and itlwm remain present. The laptop test passed the panic and reached a black screen with the pointer. Drive activity was reported, without any windows appearing. The log from this attempt was received: it confirms that `-igfxvesa` is active and `-x` is absent. It contains no IntelBTPatcher injection; Intel firmware and BlueToolFixup are still injected. Lilu/WhateverGreen injection succeeds, but does not demonstrate graphics initialisation in the kernel. Two subsequent logs, `103339` and `103615`, confirm removal of VESA and safe boot while keeping IntelBTPatcher excluded. A new photograph shows the text stalled with service, code signature and DriverKit errors, without a panic line. Loading Lilu/WhateverGreen does not prove Metal support. The subsequent [collection of system reports from Recovery](../../archive/first-boot/docs/gui-diagnostics.md) preceded diagnosis of the Intel panic and the memory fix. Comparison with an updated patcher build and Bluetooth functions remain to be verified.

## First collection of reports in Recovery

Recovery opened the interface and Terminal and read Machintosh SSD - Data. The APFS report shows a 249.8 GB container on the external drive, the System volume sealed and Data mounted without FileVault. The collection contains an old Bluetooth panic and installation logs that reach the Hello welcome screen; initial setup had not yet been completed in that collection. This is not verification of Metal support or Bluetooth operation.

