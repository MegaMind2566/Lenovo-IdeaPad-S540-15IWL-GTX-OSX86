# Targeted Intel framebuffer memory test

The panic received after direct tracing was located in the AppleIntelCFLGraphicsFramebuffer driver actually loaded. The minimum stolen-memory requirement exceeds the value calculated by the driver from firmware. This test lowers that requirement using documented WhateverGreen properties while retaining the Whiskey Lake pair already applied.

## Device result: October 13, 2026

After applying the correction, Tahoe Setup Assistant and the desktop were reached. The temporarily black panel then displayed the interface without further EFI changes. The powermetrics sample identifies IntelAccelerator and boot arguments without VESA or safe mode; system_profiler reports Metal 3, dynamic shared graphics memory up to 1536 MB, and the internal panel online at 1920×1080. The reported `0x3ea5` identifier is consistent with the applied Whiskey Lake pair.

The previous framebuffer memory-check failure was passed in the observed boot. Sustained Metal load, repeated boots, brightness, sleep, and other hardware features remain to be checked. Preserve the current EFI before further tests, as described in [Intel graphics](../../../docs/guides/intel-graphics.md).

## Evidence from the pre-correction dump

The archive contains the driver's Mach-O dump and the original, normal-test, and Recovery configs. The config hashes and both original kext hashes are valid. The `0900A53E` / `A53E0000` pair is present in all configs. The normal config contains neither VESA nor framebuffer memory properties. The Recovery config in that archive is byte-for-byte identical to the expected snapshot.

The first panic line is not visible in the photograph, but the dump allows its cause to be reconstructed through both return addresses:

| Driver-relative location | Finding |
|---|---|
| `0x357bf` | Call to the error routine; the next address `0x357c4` matches GetUnifiedMemorySize in the photograph |
| `0x92eb7` | Routine printing the assertion `minStolenSize <= fStolenMemorySize`, AppleIntelController.cpp, line 29505 |
| `0x92ef3` | Panic call; the next address `0x92ef8` matches FramebufferTerminate in the photograph |
| `0x353fa` / `0x353fd` | Comparison of available memory with the required minimum; the unsigned lower-than branch reaches the error call |

The WHL profile in the dump declares 57 MB stolen and a 1 MB reserve in the driver's calculation, giving a 58 MB requirement. The driver calculates the available value from PCI GGC at offset 0x50. The error proves that the result is below the requirement. A value of 32 MB minus 4 KB is an inference consistent with that calculation for a nonzero allocation, not an independent BIOS measurement.

The photograph's uptime is about 51.098 seconds. The earlier five-second reading was incorrect. The driver file is present; the Lilu log expected after 60 seconds is absent. The reports contain no new complete panic.

## Applied correction

Only these four-byte Data properties are added under `DeviceProperties/Add/PciRoot(0x0)/Pci(0x2,0x0)`:

| Property | Data | Purpose |
|---|---|---|
| framebuffer-patch-enable | `01000000` | Enables semantic patching |
| framebuffer-stolenmem | `00003001` | Sets the stolen-memory requirement to 19 MB |
| framebuffer-fbmem | `00009000` | Reserves 9 MB for the framebuffer |

This is the combination specified by the Coffee Lake/Whiskey Lake guide for limited preallocated memory. The normal test removes VESA and safe mode. It does not change platform-id, device-id, ACPI, connectors, unifiedmem, identity, Bluetooth, Wi-Fi, or Booter settings. It does not write BIOS registers or change the firmware allocation: it lowers the driver's requirement.

## Apply and restore

The following procedure documents the tools used. It need not be reapplied to the EFI that has already reached the desktop with Metal 3 reported.

1. From Windows, extract **S540-memoria-Intel.zip** to the root of the OpenCore HDD, beside EFI. Accept replacement of the included tools.
2. Run **TEST-MEMORIA-INTEL.cmd**. If it finds a valid previous trace, the program automatically restores the original Lilu, WhateverGreen, and config, then saves a separate backup and applies the memory test. The trace need not be restored manually before this command.
3. Boot through the same OpenCore and select **Machintosh SSD** on the Samsung. The test uses Intel acceleration. If Setup Assistant appears, continue; Metal acceleration must be verified after reaching the desktop.
4. If a new panic occurs, preserve its first line and a photograph. To reopen Recovery from Windows, use **RECOVERY-MEMORIA-INTEL.cmd**: it keeps the memory properties and adds VESA.
5. To cancel the test, use **RIPRISTINA-MEMORIA-INTEL.cmd**: it restores the saved post-trace config byte for byte. Later config changes are detected and automatic restoration is refused.

Old tracing commands remain associated with their earlier backup. Use the three MEMORIA-INTEL commands for this test. If the system remains stuck, the included collector can also collect memory-test configs from Recovery; reinstalling macOS is unnecessary to apply these properties.

The backup is `EFI/OC/config.before-intel-memory.plist`, accompanied by a JSON manifest and two snapshots, `config.intel-memory.normal.plist` / `config.intel-memory.recovery.plist`. Preserve these four files. The collector includes them when present; any previous framebuffer dump remains data from the old trace. WhateverGreen also writes its dump before patching, so an original table in that file does not prove that a later patch was ignored.

The correction is justified by the specific panic, and desktop boot with the Intel accelerator is now confirmed on the laptop. Further work will assess stability and remaining features.

## Tool validation

Nine test groups passed, covering application, automatic trace restoration, preservation of other fields, Recovery, exact restoration, later edits, incomplete or altered backups, and write failures. A separate test against the delivered EFI copy, with the backups and Recovery config from the latest archive, verified the complete DEBUG → original kexts → memory patch transition. The generated normal and Recovery configs pass ocvalidate 1.0.8; restoration returns the exact pre-trace config and kext bytes. The collector also copies all four private memory-test files. Automated tests ran on Linux. The laptop result was subsequently reported: Setup Assistant, desktop, and Metal 3 support. Windows program launch was not performed directly in the verification environment.

## Primary references

- [WhateverGreen 1.7.1, custom framebuffer patching](https://github.com/acidanthera/WhateverGreen/blob/1.7.1/Manual/FAQ.IntelHD.en.md#custom-patching).
- [Dortania, Coffee Lake/Whiskey Lake, properties for limited DVMT](https://dortania.github.io/OpenCore-Install-Guide/config-laptop.plist/coffee-lake.html#deviceproperties).
- [WhateverGreen 1.7.1, framebuffer table structure](https://github.com/acidanthera/WhateverGreen/blob/1.7.1/Manual/IntelFramebuffer.bt).
