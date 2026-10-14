# Function keys and brightness

The brightness slider and direct F11/F12 brightness keys work with the BrightnessKeys companion package. Direct F1–F3 audio controls and F6 touchpad toggle also work. The remaining icon actions and ordinary Fn function-key behavior are the current task.

## Target mapping

The complete row follows the keyboard legends: direct presses perform the icon action; **Fn+F1–F12 deliver ordinary F1–F12 to applications**. macOS global shortcuts assigned to those ordinary keys must be removed or reassigned separately. The working direct controls are retained.

| Key | Direct icon action | Current status | With Fn |
|---|---|---|---|
| F1 | Mute speakers | Working | F1 |
| F2 | Decrease volume | Working | F2 |
| F3 | Increase volume | Working | F3 |
| F4 | Mute microphone | Pending | F4 |
| F5 | Reload the current browser page | Pending | F5 |
| F6 | Toggle touchpad | Working | F6 |
| F7 | Toggle airplane mode | Pending | F7 |
| F8 | Disable/enable the built-in camera | Pending | F8 |
| F9 | Lock screen | Pending | F9 |
| F10 | Choose external display mode | Pending | F10 |
| F11 | Decrease brightness | Working | F11 |
| F12 | Increase brightness | Working | F12 |

## Remaining key events

The first complete event report records the expected F1–F12 press and release for every Fn combination. Four existing macOS symbolic shortcuts consume plain F9/F10/F11/F12: IDs 32/33/36/62, with zero modifiers. Their [reversible preference setup](../../packages/function-keys-setup/README.md) disables only those enabled fields, preserving modified shortcuts and the F14/F15 bindings used by brightness.

Direct F5 and Fn+F5 both produce keycode 96 with the same flags. A global F5 reload mapping would also intercept the ordinary Fn+F5 path, so that mapping is deferred until a lower-level distinction is established. The first direct F9/F10 captures retain only Command modifier transitions; their other keys remain unconfirmed. The default input device exposes a writable master mute control, enabling an F4 action once its trigger is established.

Observer 1.0 marked all trials interrupted while still recording the positive key identities above. It reused a tap across intentional disable/enable operations, allowing queued disable notifications to affect the next trial. Version 1.1 creates a fresh tap per window, records genuine interruption reasons, and supports a seven-trial targeted capture. Missing events in the initial interrupted windows do not establish a missing firmware event.

Run the combined setup after extracting it into Downloads:

```bash
bash "$HOME/Downloads/S540-function-keys-setup/PREPARE-FUNCTION-KEYS.command"
```

Complete the targeted prompts, retain the private report ZIP on Desktop, and restart normally to refresh macOS shortcut consumers. The original configuration of the four preference fields can be restored through the included `RESTORE-FN-SHORTCUTS.command`. This operation does not load a new EFI component.

The [native event observer](../../packages/function-key-events/README.md) records separate direct and Fn trials for all twelve keys. Its native executable is built on macOS and needs no developer tools on the laptop. It observes only allowed function/media events during the requested trials and does not modify the EFI or keyboard preferences.

The event stream can establish distinct inputs for a mapping. A missing matching event cannot distinguish a scan code discarded by VoodooPS2 from a firmware/ACPI-only action. The physical Fn key may be handled by firmware; the macOS function modifier flag is not proof that physical Fn was held. No remapping is applied until the actual input path is identified.

The original S540 tables contain a Lenovo `VPC2004` device and a generic VPC notification path. The [firmware hotkey reference](../reference/firmware-hotkeys.md) records the verified methods and separates protocol queries from state-changing commands. The original dumps remain private.

F4 requires a writable Core Audio input-mute control and state verification; reducing input gain is not a substitute for mute. F5 will be restricted to browsers so Command-R does not accidentally invoke unrelated application actions. F9 uses the normal lock-screen action. F10 requires a working external display and an explicit choice of display mode.

F7 must verify both Wi-Fi and Bluetooth power state before claiming airplane mode. itlwm presents an Ethernet interface, so disabling that network service is not evidence that its radio is off. F8 needs a confirmed camera power/privacy path; merely opening privacy settings or closing a camera application is not camera disablement.

## Brightness diagnosis before the fix

The October 14 report contains four observations: F11, F12, Fn+F11 and Fn+F12. Brightness stays at 1024 and no brightness indicator appears. The reported range is 0–1024, so the panel was already at maximum; brightness-up alone is not a useful test at that level.

The initial runtime exposed an active AppleBacklightDisplay and the internal panel route `GFX0.DD1F`. `DD1F` and `DD02` were present beneath the integrated GPU. The mounted boot configuration already enabled SSDT-XOSI and the `_OSI → XOSI` rename. BrightnessKeys was absent from that initial report.

The [previous firmware analysis](../status/hardware.md) records `_Q8E`/`_Q8F` sending `0x86`/`0x87` notifications to `GFX0.DD1F`, subject to firmware conditions. These notifications match [BrightnessKeys 1.0.3](https://github.com/acidanthera/BrightnessKeys/tree/36820d11327f8aee859997c19f46e24d854ddee7). The runtime panel route also matches that driver's DD1F fallback. This supports an add-only test; the initial snapshots do not establish that the firmware emitted a notification.

## Reversible BrightnessKeys test

The `S540-brightness-keys-v2` package adds the official **BrightnessKeys 1.0.3 RELEASE** bundle and one enabled `Kernel → Add` entry to the current boot EFI. It retains the existing function-key mappings, Intel framebuffer, `-igfxblr`, audio, ACPI and identity settings. The personal configuration backup stays on the boot device.

The installer checks the driver manifest, OpenCore version, current and candidate configurations, and the private rollback snapshots. It stops if the configuration or owned files differ from the expected state. Brightness now works on the laptop; the first EFI release remains unchanged and does not include this companion driver.

Extract the package to Downloads and run:

```bash
bash "$HOME/Downloads/S540-brightness-keys-v2/TEST-BRIGHTNESS-KEYS.command"
```

The default boot directory is `/Volumes/240 GB`. If its mount point differs, pass the exact boot directory as the final argument.

After restarting through that boot device:

1. Set the brightness slider to approximately half.
2. Try the brightness-marked F11/F12 keys without Fn. Check both the indicator and the panel brightness.
3. Check that Fn+F11/F12 still produce ordinary function-key events. Remove or reassign conflicting macOS shortcuts so applications can use these keys.
4. Check F1–F3 mute and volume.
5. Run the included collector and keep the resulting private ZIP:

```bash
bash "$HOME/Downloads/S540-brightness-keys-v2/COLLECT-FUNCTION-KEYS.command"
```

Its BrightnessKeys snapshot can show `VersionInfo`, `BrightnessPanel` and `BrightnessKeyRouted`. The routing properties are written when the driver receives a supported notification. A loaded driver with no routed event requires a separate review of the firmware conditions; it does not justify a generic DSDT or ThinkPad patch.

To restore the exact previous configuration and remove the verified test bundle from active loading:

```bash
bash "$HOME/Downloads/S540-brightness-keys-v2/RESTORE-BRIGHTNESS-KEYS.command"
```

Restart after restoration. If the current configuration was edited after installing the test, the restore command stops to avoid overwriting those edits.

## Source and scope

BrightnessKeys uses the existing Lilu dependency; it has no additional Tahoe beta boot argument. Both direct brightness directions are reported working on the laptop. The companion package and its rollback backup are retained while the remaining function keys are addressed.

The ordinary Fn function-key path and working audio, touchpad and brightness controls remain the baseline for the rest of the row.

## FAT boot-volume metadata

Version 2 uses data-only copies for the configuration snapshots and recognizes validated AppleDouble sidecars and Finder metadata. It retains these metadata files. Real configuration, manifest and driver hashes, backup ownership and all rollback guards remain enforced.

The private backup format and driver payload are compatible with version 1. A valid interrupted backup can be resumed; keep `backup-function-keys` in place. Unexpected files still stop the operation, and the error now includes the filename.

