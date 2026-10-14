# Unified logs after reinstallation

The LOG-UNIFICATI-e8VM9n collection contains diagnostics and uuidtext, five tracev3 files, one timesync, and two DSC files. All 496 files have valid CRCs; their uncompressed size is approximately 220.6 MB. Original archives, UUIDs, and other identifiers are not published.

The data was decoded offline with the official Mandiant macos-UnifiedLogs 0.7.0 binary, verified against the release checksum and digest. The two directories' contents were combined in a working folder, preserving the original copy. This produced 106,966 events from two boots. Some messages are private and the parser reports unresolved UUID references: an event's absence does not prove the absence of a problem.

## Recorded boots

The following times are UTC according to timesync data, not the photograph's local times.

| Boot | Event interval | Effective parameters |
|---|---|---|
| First | October 13, 2026, 10:39:49–10:40:48 | `-igfxvesa` and `-bsdmgroot`; `-x` absent |
| Second | October 13, 2026, 10:41:00–10:43:25 | `-igfxvesa`; `-x` and `-bsdmgroot` absent |

In the second boot, launchd and the kernel report the same boot arguments. The VESA flag is therefore applied in the running system, rather than merely present in an old config. This archive contains no non-VESA boot of the new installation.

## Interface during the second boot

| UTC time | Process | Result |
|---|---|---|
| 10:41:29.492 | WindowServer | Intel `8086:3e9b`, IGPU path, `IONDRVFramebuffer`, null accelerator |
| 10:41:29.530–29.550 | WindowServer | `AppleIntelFramebuffer = 0` and `isAcc=NO` |
| 10:41:29.711 | WindowServer | `Software compositor activated.` |
| 10:41:32.959 | iconservicesagent | `No Metal renderer available.` |
| 10:41:35.293 | Language Chooser, com.apple.macbuddy | Sets the welcome background data |
| 10:41:35.294 | Language Chooser, com.apple.macbuddy | `Fail to create texture!` |

WindowServer and Language Chooser continue recording events after the error. No explicit termination was identified in the sample. A visible cursor does not demonstrate that the welcome texture is drawn.

WhateverGreen 1.7.1 source reads `-igfxvesa` and prevents IntelAccelerator from starting. Missing acceleration in these boots is consistent with that diagnostic choice. The texture failure is a concrete interface error during VESA use; it does not alone prove the cause of earlier non-VESA attempts.

Lilu and WhateverGreen produce load notifications, as does AppleIntelCFLGraphicsFramebuffer. A load notification does not demonstrate a working accelerator. Injected properties expose the expected Intel device-id, but the native framebuffer and Metal remain to be verified. IntelBTPatcher does not appear in events, whereas Intel firmware and BlueToolFixup do; the next test must preserve the patcher's exclusion.

No DVMT/stolen-memory diagnosis was identified to justify new patches. AMFI context errors and DriverKit errors are not automatically interpreted as graphics errors.

## Next step

From Windows, run **TEST-INTEL.cmd on the HDD containing the EFI used for these boots**. It removes only `-igfxvesa` and any `-x`, preserving the Bluetooth change and other settings. The program and restoration command are already available in the previous Intel package; its code matches the current source.

After successful Intel-test activation, check that `-igfxvesa` is listed as removed, then boot through the same OpenCore and select **Machintosh SSD**. This is the new installation's normal test. Non-VESA logs `103339` and `103615` belonged to the earlier installation; the new collection neither replaces nor contradicts them.

If the program reports that the parameters are already absent or rejects the backup, retain the message: verify which EFI is actually being used before further changes. If the screen remains black after successful removal, the OpenCore log from that attempt and a new unified-data collection are needed. Earlier logs remain on Data: compare by boot and boot arguments, rather than assuming the entire ZIP describes the latest test.

## Subsequent test after the manual change

Manual removal of `-igfxvesa` from config.plist was reported. The new attempt's photograph shows extension-collection loading and repeated com.apple.driver.IOVersatile dependency errors with code `0xdc00800e`. DockChannelSerial reports `has crashed 0 time(s)`. No panic line is visible and effective boot arguments are not shown.

The same IOVersatile error was already present in the earlier archive with VESA active. After those errors, WindowServer was running and Language Chooser continued. In that sample, DockChannelSerial also recorded successful startup. The photograph's last line therefore does not alone identify what prevents the interface. The error is not new evidence of corruption or Intel failure.

The next comparison requires the OpenCore log just created by this attempt and the edited config.plist. Runtime absence of VESA must be confirmed before interpreting a new collection. No IOVersatile block or new graphics parameter is applied based only on the photograph.

## Non-VESA boot confirmed: 170135 and 170413

Both new October 13, 2026 OpenCore logs select Machintosh SSD on the USB Samsung and show `MBA:NV` and `MBA:OUT` without `-igfxvesa`, `-x`, or `-bsdmgroot`. Lilu 1.7.2 and WhateverGreen 1.7.1 are injected successfully; IntelBTPatcher is absent from the injections. AAPL,ig-platform-id and device-id properties are set with a Success result, but their values are not printed.

The files end at EXITBS:START at 17:01:41 and 17:04:18 according to the booter clock. They contain no subsequent macOS events: this log ending does not locate the stall. Manual removal is effective for both attempts. NVRAM messages about a value already present are consistent with boot arguments matching the desired values.

The earlier unified ZIP contained VESA boots and does not document Intel operation during these attempts. Config.plist was subsequently received and reviewed, as described below. Persistent normal-boot events remain necessary to verify the accelerator. The already-absent parameter is not removed again.

## Received configuration and Whiskey Lake test

The file opens correctly as a plist. Comparison with the reference configuration shows only IntelBTPatcher disabled; other values are preserved. Both Intel properties are four-byte Data: AAPL,ig-platform-id `00009B3E` and device-id `9B3E0000`, under PciRoot(0x0)/Pci(0x2,0x0). Static structure and types were compared with the official OpenCore 1.0.8 Sample.plist; ocvalidate was not run.

The current profile is mobile and is not connectorless. Dortania's Coffee/Whiskey Lake guide proposes it for UHD 620. WhateverGreen 1.7.1's manual instead specifies the fake device-id `A53E0000` and default laptop framebuffer 0x3EA50009 for Whiskey Lake UHD 620, written as Data `0900A53E`.

After the two normal attempts, a test of this specific pair was prepared by changing only those two values. The private package contains the test config and a backup byte-for-byte identical to the received config. Plist parsing, comparison of the two changes only, and ZIP CRCs are verified; the laptop result is not yet available. The complete config and backup are not published in the repository.

The [procedure](whiskey-lake-test.md) preserves boot arguments, Bluetooth state, and machine identity. Both framebuffers declare 58 MB of stolen memory: this test neither fixes nor establishes a possible DVMT limit. No memory or connector patches are added without a diagnosis. If the result does not change, the next collection must include events from the normal test and this test, distinguished by boot.

## Complete review requested after the test

After attempt 173430, stationary text mentioning IOVersatile and a second incompletely transcribed message was reported. A review of the already-delivered EFI, accounting for the few known changes, was requested before selecting further changes. The [complete review](../../../docs/reference/efi-review.md) confirmed files, architectures, dependencies, and ACPI; ocvalidate 1.0.8 was run on both available configs with the result No issues found. These checks led to no new graphics change. A [verified-archive procedure](../../../docs/guides/boot-maintenance.md) is available to organize old logs and tests on the disk.

## References

- [Mandiant: official release 0.7.0](https://github.com/mandiant/macos-UnifiedLogs/releases/tag/v0.7.0).
- [Mandiant: manual collection structure](https://github.com/mandiant/macos-UnifiedLogs/blob/v0.7.0/RUNNING.md).
- [WhateverGreen 1.7.1: meaning of -igfxvesa](https://github.com/acidanthera/WhateverGreen/blob/1.7.1/README.md).
- [WhateverGreen 1.7.1: disableAccel and wrapAcceleratorStart handling](https://github.com/acidanthera/WhateverGreen/blob/1.7.1/WhateverGreen/kern_igfx.cpp).
