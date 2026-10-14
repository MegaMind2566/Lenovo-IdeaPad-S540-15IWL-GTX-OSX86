# USB/Bluetooth panic: trial without IntelBTPatcher

## Information from the screenshot received on October 13, 2026

The photograph shows a kernel panic with the following readable information:

| Item | Value |
|---|---|
| Process associated with the current thread | `bluetoothd` |
| Extensions in the backtrace | `com.apple.iokit.IOUSBHostFamily`, `com.zxystd.IntelBTPatcher (2.4)` |
| Visible USB path | `IOUSBHostDevice::deviceRequest`, `IOUSBHostUserClient::controlRequest` |
| Kernel | Darwin `25.6.0` |
| macOS build | `25G241` |
| Diagnostic graphics argument | `-igfxvesa` present |
| Safe boot | `-x` absent from the displayed boot arguments |

The first `panic(...)` line and the beginning of the backtrace are outside the frame. The photograph identifies the Bluetooth/USB path and makes IntelBTPatcher the first component to isolate; it does not yet prove the exact cause of the panic. This is not simply frozen boot text.

## Difference between the included release and updated source

The initial EFI included IntelBluetoothFirmware/IntelBTPatcher **v2.4.0**, published on February 27, 2024. IntelBTPatcher source in that tag declares Sonoma as the maximum kernel version; `-ibtcompatbeta` allowed it to load on later versions without updating the USB patch logic.

The official project subsequently corrected HCI memory descriptor preparation for Sequoia and later:

- [Correction from June 24, 2024](https://github.com/OpenIntelWireless/IntelBluetoothFirmware/commit/50e971c524081a1d97a72794db2640aa0136e284).
- [Restriction of the correction to Sequoia and later](https://github.com/OpenIntelWireless/IntelBluetoothFirmware/commit/01cc1806d71f5cc64c464851b9f4811a3e7b4791).
- [Source with declared Tahoe support, pinned to commit a414375](https://github.com/OpenIntelWireless/IntelBluetoothFirmware/blob/a414375505fa3b014be32f8fca31b5bbfdf9f10f/IntelBTPatcher/IntelBTPatcher.cpp).
- [Release v2.4.0](https://github.com/OpenIntelWireless/IntelBluetoothFirmware/releases/tag/v2.4.0).

The code difference is verified. Whether it caused this particular panic remains a hypothesis to check with the trial. Correct the initial EFI by disabling the old patcher; enabling it again would require an official build of the updated source and a device check.

## Next boot

1. Return to Windows. If safe boot was undone with `RIPRISTINA-AVVIO.cmd` but the VESA trial remains, complete the restore now with **RIPRISTINA-GRAFICA.cmd**. `-igfxvesa` is still present in the photograph. If **TEST-INTEL.cmd** has already been used on the current EFI, skip the older restore commands.
2. Extract **S540-test-Bluetooth.zip** to the root of the HDD that boots OpenCore, alongside the `EFI` folder.
3. Run **TEST-BT.cmd**. It must confirm that only `IntelBTPatcher.kext` was disabled and a backup saved. If it reports an error, keep the message and stop the trial.
4. Shut down and turn the laptop back on. Boot the same OpenCore and select **Machintosh SSD**.
5. Report whether the panic returns or the interface appears. A successful boot allows a return to Intel verification, followed by comparison with an updated patcher version.

The trial only sets `Kernel → Add → IntelBTPatcher.kext → Enabled = false`. It preserves IntelBluetoothFirmware, BlueToolFixup, and itlwm. Bluetooth behavior without the patcher still needs to be checked: the trial does not guarantee that all Bluetooth features remain available.

## Restore

**RIPRISTINA-BT.cmd** restores the exact bytes of `EFI/OC/config.before-bt-test.plist`. Restore refuses to overwrite changes made after the trial. If several trials were applied, undo them in reverse order.

Alternatively, using a plist editor, the trial consists of setting `Enabled = false` only for the `IntelBTPatcher.kext` entry in `Kernel/Add`. Do not delete the entry or the kext file.

## Program verification

The program is checked against the already delivered EFI configuration: it changes one Boolean only, preserves other values, can run twice, restores the original bytes, and rejects backups from another state or subsequent changes. It also rejects configurations where the entry is missing, duplicated, or has an incorrectly typed `Enabled` value. The laptop result remains to be collected.

## Result reported after the trial

With IntelBTPatcher disabled, one boot passed the panic. A black screen with a pointer and no windows remains; disk activity was reported. This result separates the Bluetooth panic from the interface issue but does not prove full Bluetooth compatibility or identify a specific graphics error.

Keep the patcher disabled. Use **TEST-INTEL.cmd** on the current EFI to check and, if necessary, remove only `-x` and `-igfxvesa`. Compatibility between the two programs was checked against the delivered configuration: the Intel trial preserves the disabled IntelBTPatcher entry. If both flags are already absent, the program does not write the file; collect its message and the new OpenCore log. If it reports a backup from another state, keep the error without deleting backups.

After TEST-BT, do not perform a full restore of the old graphics trial: it belongs to a state preceding the Bluetooth change, and the restore protection may reject it. If TEST-BT is applied first and TEST-INTEL second, undo them by running RIPRISTINA-INTEL first and RIPRISTINA-BT second.
