# Complete verification of the delivered EFI

Verification dated 13 October 2026. The complete first-delivery ZIP, the config.plist supplied after the Bluetooth change, and the Whiskey Lake test config were examined. Known subsequent changes were considered. The EFI on the laptop was not replaced. Any Wi-Fi profile saved after delivery remains in the current EFI.

## Result

No missing files, mixed OpenCore versions, executables with the wrong architecture, incorrectly ordered kext dependencies or SSDTs with invalid checksums were found. The delivered EFI contains 55 files, approximately 35.75 MB. All 55 SHA-256 values match the manifest. Both delivery ZIPs pass CRC verification.

ocvalidate was downloaded from the official OpenCore 1.0.8 DEBUG release. The archive size and SHA-256 match the release metadata. The program was run on the available configs and those generated for the tests:

| Checked config | ocvalidate 1.0.8 result |
|---|---|
| Supplied file, IntelBTPatcher excluded and VESA absent | No issues found, exit code 0 |
| Prepared Whiskey Lake pair | No issues found, exit code 0 |
| Direct Intel trace, normal boot | No issues found, exit code 0 |
| Direct Intel trace, VESA Recovery without automatic dumps | No issues found, exit code 0 |
| Intel memory test, normal boot | No issues found, exit code 0 |
| Intel memory test, VESA Recovery | No issues found, exit code 0 |

Validation confirms the structure and rules checked by the program, not hardware acceleration on the device.

## OpenCore and drivers

BOOTx64.efi, OpenCore.efi, HfsPlus.efi and OpenRuntime.efi have valid PE headers, x64 architecture and PE32+ format. Their PE roles are consistent: EFI applications for the first two, a boot-service driver for HfsPlus and a runtime driver for OpenRuntime. No mixed releases were identified in the delivery.

The config enables only OpenRuntime and HfsPlus. It uses the built-in picker without Misc.Tools entries. This picker does not require OpenCanopy, Resources or additional tools. Logs ending at EXITBS:START describe the handover out of firmware services; they do not show subsequent macOS operation.

## Kexts and dependencies

The 20 Kernel.Add entries have unique identifiers and valid PlistPath/ExecutablePath values. All 19 executables include x86_64; UTBMap correctly has no executable. External non-Apple dependencies are present, precede their clients and have versions compatible with their plist requirements.

| Component | Delivered version | Expected state on Darwin 25.6 |
|---|---|---|
| Lilu | 1.7.2 | Enabled |
| VirtualSMC | 1.3.8 | Enabled |
| SMCProcessor | 1.3.8 | Enabled |
| SMCBatteryManager | 1.3.8 | Enabled |
| WhateverGreen | 1.7.1 | Enabled |
| RestrictEvents | 1.1.6 | Enabled |
| AppleALC | 1.9.8 | Excluded by MaxKernel 24.99.99 |
| USBToolBox | 1.2.0 | Enabled |
| UTBMap | 1.1 | Enabled, plist only |
| VoodooInput, I2C plug-in | 1.1.6 | Enabled |
| VoodooI2CServices | 1 | Enabled |
| VoodooGPIO | 1.1 | Enabled |
| VoodooI2C | 2.9.1 | Enabled |
| VoodooI2CHID | 1 | Enabled |
| VoodooPS2Controller | 2.3.7 | Enabled |
| VoodooPS2Keyboard | 2.3.7 | Enabled |
| IntelBluetoothFirmware | 2.4.0 | Enabled |
| IntelBTPatcher | 2.4.0 | Disabled after the panic |
| BlueToolFixup | 2.7.2 | Enabled |
| itlwm | 2.3.0 | Enabled |

With the config limits and Bluetooth patcher exclusion, 18 entries apply to Darwin 25.6. This count does not establish that every device works. The I2C components with version number 1 are part of the official package and do not indicate mixed releases. The included Lilu and WhateverGreen changelogs declare macOS 26 support; no additional beta flag is added for those two components.

## ACPI and configuration

Five SSDTs are enabled and SSDT-DGPU-OFF is disabled. All six have SSDT signatures, correct declared lengths and valid checksums. The Add entries and four-byte _OSI-to-XOSI replacement match the reference. Structural verification does not replace testing their ACPI effects on hardware.

The supplied config differs from the reference only by disabling IntelBTPatcher. Booter, UEFI, ACPI, the USB map, kext limits and machine identity are preserved. The Whiskey Lake test changes only AAPL,ig-platform-id and device-id; other settings remain unchanged. The USB map has nine ports and XhciPortLimit is disabled. The booted Samsung uses USB; the internal PM981a remains installed for Windows.

AppleALC does not apply to Tahoe because of its version limit. Bluetooth with the patcher excluded and electrical NVIDIA power-off still require testing at this stage. These are known functional limitations, not new structural defects. No changes to Booter, firmware, signatures or IOVersatile were introduced solely on the basis of the last visible line.

## Semantic patch verification

The [comparison with OEM DSDT and SSDTs](acpi-patch-review.md) is complete. CPU, EC, RTC, XOSI, PNLF, GPU paths and _DSM methods are consistent with the custom patches. No static error was identified that would justify a new ACPI or framebuffer-memory patch. Joint iasl resolution has a limitation involving a possible conditional OEM overlap; this is not treated as an EFI-introduced error.

## Evidence still needed to explain the stall

OpenCore log 173430 shows the same sequence as the earlier 170413 log, with normal boot arguments and no new errors. Following the attempt, stationary text mentioning IOVersatile and a second incompletely transcribed message was reported. In the previous unified archive, IOVersatile errors were followed by a running WindowServer and an active Language Chooser; both boots used VESA. That does not establish the cause of the new stall.

The new Intel pair did not produce a visible interface in the reported test. In the latest unified collection, the twelve new tracev3 files are empty, while the five nonempty files match those already analyzed. New timesync records confirm further boots but add no driver messages. The subsequent [direct Intel trace](../../archive/first-boot/docs/intel-trace.md) produced the driver dump. Correlating the panic addresses identified the insufficient stolen-memory check. The [memory test](../../archive/first-boot/docs/intel-memory-test.md) reduces the framebuffer requirement through three documented properties. Static EFI consistency does not establish acceleration; the device outcome still requires verification at this stage.

## Boot-disk organization

The delivered EFI is already compact. Cleanup concerns OpenCore logs and old test packages and tools at the HDD root. The [organization procedure](../guides/boot-maintenance.md) archives them on the Windows Desktop, verifies the copy, and then removes them from the HDD. It preserves the current EFI, Recovery files and unified collector. It does not change the Intel profile or kexts.

Unrecognized files remain on the disk and are listed in the report. Cleanup is not presented as a fix for the graphics stall. The Desktop backup retains the files and instructions for restoring their original locations.

## References

- [OpenCore 1.0.8: official release](https://github.com/acidanthera/OpenCorePkg/releases/tag/1.0.8).
- [ocvalidate: checks and limitations](https://github.com/acidanthera/OpenCorePkg/blob/1.0.8/Utilities/ocvalidate/README.md).
- [Lilu 1.7.2: changelog](https://github.com/acidanthera/Lilu/blob/1.7.2/Changelog.md).
- [WhateverGreen 1.7.1: changelog](https://github.com/acidanthera/WhateverGreen/blob/1.7.1/Changelog.md).
- [Analysis of the supplied unified collection](../../archive/first-boot/docs/unified-log-analysis.md).

