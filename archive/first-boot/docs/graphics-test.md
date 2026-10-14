# Graphics test for the Recovery stall

In the first two attempts, Recovery loaded the kernel and ran user services, but did not display its graphical screen. The photographs show `IOG flags 0x3 (0x51)` and launchd messages. They show no kernel panic and do not identify a single cause. The boot disk is a USB HDD; no disk activity and maximum fan speed were reported.

This test adds **only `-igfxvesa`** to the boot arguments. WhateverGreen uses this option to disable Intel graphics acceleration. It checks whether Recovery can display its interface in basic mode. This is not the final configuration for macOS use.

## Apply the test from Windows

1. Boot Windows from the Lenovo menu.
2. Extract `S540-test-grafica.zip` **to the root of the HDD used to boot Recovery**, where `EFI` and `com.apple.recovery.boot` already exist.
3. `TEST-GRAFICA.cmd` must sit beside `EFI`, with `tools/test_graphics.py` in the `tools` folder on the same disk.
4. Double-click **TEST-GRAFICA.cmd**. It requires the same Python 3 used to download Recovery. Wait for the graphics-test activation message.
5. Reboot OpenCore and select Recovery again. If macOS Utilities appears, report the result and stop before erasing the destination disk.

The script edits the disk's existing `config.plist`, preserving SMBIOS identifiers and all other settings. The Wi-Fi profile remains in its own kext. The backup is `EFI/OC/config.before-graphics-test.plist`.

To return to the previous configuration, run **RIPRISTINA-GRAFICA.cmd**. Restoration refuses to overwrite a configuration containing further changes.

## Interpret the result

- If the graphical interface appears, the result narrows the investigation to the accelerated graphics path. DVMT, framebuffer platform, and UHD 620 properties will be checked next.
- If boot still stops, provide a photograph of the final lines and the `opencore-*.txt` log from the boot disk's root. That log covers OpenCore and injected extensions; it does not replace the complete macOS log.
- The test must not format a disk or download Recovery again. Graphics performance may be low because acceleration is temporarily disabled.

Reference: [WhateverGreen 1.7.1, Intel options](https://github.com/acidanthera/WhateverGreen/blob/1.7.1/README.md#intel-hd-graphics).
