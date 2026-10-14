# Safe boot test from Macintosh SSD

During the attempt from the “Macintosh SSD” volume, the log reports `WindowServer: Job state = running`, AppleKeyStore errors in requests from `bluetoothd`, activity from `com.apple.fskit.msdos`, and `AppleActuatorDevice ... returned error 0xe00002c7`. The final code means that a function is unsupported. The log continues after the error and shows no explicit kernel panic. The volume name appearing and the WindowServer process starting do not confirm that installation is complete or that graphics work.

These messages alone do not identify why the graphical screen fails to appear. This test adds **only `-x`**, which requests safe boot. It does not disable individual kexts or replace the entire configuration. Other boot arguments, including `-igfxvesa` if present, remain unchanged.

## When to use this test

Use this test for the macOS volume when boot remains on the text screen without progressing. If **macOS Installer** still appears in the menu, complete that phase first. Keep the power adapter, boot HDD, and external SSD connected.

## From Windows

1. Download `S540-avvio-sicuro.zip` and boot Windows from the Lenovo menu.
2. Extract the contents **to the root of the HDD containing the current EFI**. `AVVIO-SICURO.cmd` must sit beside `EFI`, with `tools/test_safe_boot.py` in the `tools` folder on the same HDD.
3. Run **AVVIO-SICURO.cmd**. It uses Python 3, already used for Recovery. Wait for the message confirming that the test is enabled and only `-x` was added.
4. Reboot through the same OpenCore and select **Macintosh SSD**.
5. If Setup Assistant appears, continue to the desktop and collect the data below. If boot stops, capture the new screen and record the elapsed time.

The backup is `EFI/OC/config.before-safe-boot.plist`. The script preserves SMBIOS identifiers, ACPI, Intel properties, disk settings, and the Wi-Fi profile. It checks boot-argument rewriting in NVRAM and `EnableSafeModeSlide`, already present in the initial EFI. It does not write partitions, download kexts, or send data.

## Desktop data, if reached

```sh
sysctl -n kern.bootargs
system_profiler SPDisplaysDataType
```

Safe boot can limit services and performance. Success narrows the investigation, but does not identify a specific driver or demonstrate Metal support. Failure alone does not rule out a software problem either.

## Restore

From Windows, run **RIPRISTINA-AVVIO.cmd** on the same HDD. It restores the exact previous plist and keeps the backup. If further changes have been made, the script refuses automatic restoration.

This test's backup and the earlier graphics test's backup are separate. Restore the safe boot test first; any removal of `-igfxvesa` will be assessed after reviewing data from the installed system.

## References

- [OpenCore 1.0.8: safe mode, -x, and EnableSafeModeSlide](https://github.com/acidanthera/OpenCorePkg/blob/1.0.8/Docs/Configuration.tex)
- [Apple: IOKit codes, including kIOReturnUnsupported](https://github.com/apple-oss-distributions/xnu/blob/main/iokit/IOKit/IOReturn.h)
