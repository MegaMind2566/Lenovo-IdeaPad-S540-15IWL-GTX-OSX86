# Intel test after cursor trails

**Update after reinstallation:** the [received unified logs](unified-log-analysis.md) contain two boots still using `-igfxvesa`. WindowServer uses the software compositor and Language Chooser fails to create the welcome texture. The next test is to reapply **TEST-INTEL.cmd to the current EFI**, keeping IntelBTPatcher disabled. The previous test without VESA concerned the earlier installation; the new archive contains no normal boot of the new installation.

During the attempt from “Machintosh SSD”, a cursor appeared without windows. Trails during movement were reported. This is consistent with a screen-redraw problem, but does not identify the driver, framebuffer, or memory as its cause.

The 02:45 log confirmed both parameters; the subsequent panic photograph showed only `-igfxvesa`. The new `opencore-2026-10-13-063718.txt` log, received after disabling IntelBTPatcher, confirms that `-igfxvesa` remains active and `-x` is absent. Later logs `103339` and `103615` confirm that both flags are now absent and IntelBTPatcher is not injected. The test was applied correctly, but the interface has not yet been reached: the next step is to [collect reports from the Data volume in Recovery](gui-diagnostics.md), temporarily restoring the Intel test if needed for access. This test checks the local EFI and removes **only these two parameters**, if present. `-x` requests safe boot; `-igfxvesa` disables Intel acceleration. Removing them allows normal boot with the prepared UHD 620 configuration. It does not guarantee that Metal works.

After the Bluetooth test, keep IntelBTPatcher disabled and run this program against the current configuration. The Intel test preserves the Bluetooth change; old full restorations may be rejected because they belong to an earlier state.

## Apply from Windows

Use the test on the macOS volume. If **macOS Installer** is still in the OpenCore menu, complete that phase first.

1. Boot Windows from the Lenovo menu.
2. Extract `S540-test-Intel.zip` **to the root of the HDD containing the EFI used for boot**. `TEST-INTEL.cmd` must sit beside `EFI`, with `tools/test_safe_boot.py` in the `tools` folder on the same HDD. Accept replacement of this script if it came from the earlier safe boot package.
3. Run **TEST-INTEL.cmd**. It requires the same Python 3 used for Recovery.
4. Read the result. On successful activation, the program lists the parameters it removed. If it reports that they are absent, it does not edit the file: capture the window text before proceeding with other changes.
5. After a successful change, reboot OpenCore from the same HDD and select **Machintosh SSD**.

The backup is `EFI/OC/config.before-intel-test.plist`. SMBIOS identifiers, Intel properties, kexts, ACPI, and other settings are preserved. The Wi-Fi profile remains in its own kext. The entire EFI is not overwritten and no disks are erased.

## Interpret the result

- If macOS Setup Assistant appears, continue to the desktop and collect the data below.
- If boot stops, capture the new screen. After returning to Windows, **RIPRISTINA-INTEL.cmd** restores the exact configuration present before this test.
- If cursor trails continue, the effective boot arguments, logs, and applied framebuffer will be needed. Trails do not automatically prove that DVMT is set to 32 MB.

From the desktop, open Terminal and run:

```sh
sysctl -n kern.bootargs
system_profiler SPDisplaysDataType
```

Use this test's own restore command, **RIPRISTINA-INTEL.cmd**. Earlier tests' backups remain separate. The scripts refuse restoration if additional changes have been made, avoiding their removal.

## References

- [WhateverGreen 1.7.1: -igfxvesa](https://github.com/acidanthera/WhateverGreen/blob/1.7.1/README.md#intel-hd-graphics)
- [OpenCore 1.0.8: -x and safe boot](https://github.com/acidanthera/OpenCorePkg/blob/1.0.8/Docs/Configuration.tex)
- [Dortania: UHD 620 on Coffee Lake and Whiskey Lake](https://dortania.github.io/OpenCore-Install-Guide/config-laptop.plist/coffee-lake.html#deviceproperties)
