# Intel Whiskey Lake profile test

This compatibility test was prepared after reviewing config.plist and the two normal boots `170135` and `170413`. It is not yet a confirmed fix on the device. The collected hardware data identifies Whiskey Lake UHD 620, PCI 8086:3EA0.

| Intel property, four-byte Data type | Received config | Test |
|---|---|---|
| AAPL,ig-platform-id | `00009B3E` | `0900A53E` |
| device-id | `9B3E0000` | `A53E0000` |

The manual included with WhateverGreen 1.7.1 explicitly specifies A53E0000 for the Whiskey Lake UHD 620 device-id and 0x3EA50009 as the default laptop framebuffer. The earlier profile is a mobile baseline proposed by Dortania; the difference between these recommendations justifies a test, but does not by itself prove the cause of the black screen.

The **S540-test-WhiskeyLake.zip** package, delivered in the chat, contains a test config, an exact backup of the received config, and instructions. To keep the machine identity private, these plists are absent from the repository. The builder keeps the earlier settings until the test produces a verified result.

## Apply and revert

1. From Windows, extract the ZIP to a regular folder.
2. Copy config.plist and config.before-whiskey-lake.plist to EFI/OC on the HDD of the same OpenCore used for the latest boots. Replace config.plist.
3. Boot OpenCore and select **Machintosh SSD** on the external Samsung. If the welcome screen appears, continue through Setup Assistant.
4. If the result does not improve, copy the backup to another folder, rename that copy config.plist, and replace EFI/OC/config.plist with it. Keep the backup.

Only the two Intel properties changed. The backup is byte-for-byte identical to the received file. Plist parsing, semantic differences, and ZIP CRCs are verified. IntelBTPatcher remains disabled, and VESA and safe boot remain absent. No other value, including SMBIOS identity, is changed.

Both profiles declare 58 MB of stolen memory. The test does not change DVMT, add memory or connector patches, or demonstrate acceleration. If the interface starts, verify [Intel and Metal](../../../docs/guides/intel-graphics.md). After further reported attempts without an interface, the [ACPI review](../../../docs/reference/acpi-patch-review.md) found no inconsistent patch; the latest tracev3 files are empty. The next step is [direct Intel tracing](intel-trace.md), preserving the current pair. The OpenCore log ending at EXITBS:START does not locate the subsequent stall.

The new tracing collection confirms the Whiskey Lake pair in the configs and contains the actual driver. Panic addresses identify a stolen-memory requirement above the memory calculated from firmware. A [memory test](intel-memory-test.md) was therefore prepared while retaining this same GPU pair.

## Log received after test delivery: 173430

The new OpenCore log selects Machintosh SSD on the USB Samsung. MBA:NV and MBA:OUT contain no VESA, safe boot, or bsdmgroot; Lilu 1.7.2 and WhateverGreen 1.7.1 are injected successfully, and IntelBTPatcher remains absent. Prelinked status is Success. The sequence has no new errors compared with log 170413.

Both Intel properties are set successfully, but OpenCore does not print their values: the log alone does not confirm that the test pair was read. The file ends at EXITBS:START at 17:34:34 according to the booter clock and contains no subsequent system events. This is not interpreted as proof of a stall at that point. The visible screen result after this attempt has not yet been reported.

## References

- [WhateverGreen 1.7.1: Intel manual](https://github.com/acidanthera/WhateverGreen/blob/1.7.1/Manual/FAQ.IntelHD.en.md), CFL/CML sections, Recommended framebuffers, and the Whiskey Lake recommendation.
- [Dortania: Coffee Lake and Whiskey Lake laptops](https://dortania.github.io/OpenCore-Install-Guide/config-laptop.plist/coffee-lake.html#deviceproperties), UHD 620 baseline and conditional DVMT patch.
