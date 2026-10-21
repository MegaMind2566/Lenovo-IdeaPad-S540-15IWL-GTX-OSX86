# Function keys and brightness

Status reviewed **October 21, 2026**, against the official non-NVIDIA EFI. The user has now confirmed **F5 browser reload and F6 touchpad toggling**, in addition to the working F1–F3 controls and F11/F12 brightness. F6 disables and re-enables the touchpad, while Fn+F6 leaves it enabled. Direct F7 changes neither Wi-Fi nor Bluetooth power state, and direct F8 has no observed camera effect. F4, F7, F8 and F9 remain open; F10 awaits a working external display. The brightness slider also works with the official non-NVIDIA EFI and the BrightnessKeys companion driver. The separate NVIDIA-test brightness regression remains deferred; it is not a failure of this official EFI.

The remaining function-row work concerns the unconfirmed icon actions and application use of ordinary function keys after the macOS shortcut refresh. No new keyboard map, BIOS setting, ACPI patch or kext is justified by the current reports.

## Target mapping

The complete row follows the keyboard legends: direct presses perform the icon action; **Fn+F1–F12 deliver ordinary F1–F12 to applications**. macOS global shortcuts assigned to those ordinary keys must be removed or reassigned separately. The working direct controls are retained.

| Key | Direct icon action | Current status | With Fn |
|---|---|---|---|
| F1 | Mute speakers | Working; reconfirmed October 20 | F1 |
| F2 | Decrease volume | Working; reconfirmed October 20 | F2 |
| F3 | Increase volume | Working; reconfirmed October 20 | F3 |
| F4 | Mute microphone | Pending; trigger not established | F4 |
| F5 | Reload the current browser page | User confirmed after browser-specific shortcut setup; direct and Fn inputs remain indistinguishable | F5 |
| F6 | Toggle touchpad | Reconfirmed October 21: disable, re-enable, and Fn+F6 leaves it enabled | F6 |
| F7 | Toggle airplane mode | October 21: neither Wi-Fi nor Bluetooth changes state; trigger/action still unresolved | F7 |
| F8 | Disable/enable the built-in camera | October 21: no observed effect during camera preview; trigger/action still unresolved | F8 |
| F9 | Lock screen | Pending; observed Command-L must be distinguished from ordinary Command-L | F9 |
| F10 | Choose external display mode | Pending; trigger and working external-display prerequisite unresolved | F10 |
| F11 | Decrease brightness | Working with the official non-NVIDIA EFI | F11 |
| F12 | Increase brightness | Working with the official non-NVIDIA EFI | F12 |

## Remaining verification scope

The current completion scope is direct **F4, F7, F8 and F9**, plus application handling of ordinary **Fn+F9–F12** after the normal session refresh. F5 and F6 are functionally confirmed and need no repeat test. The full Fn row has already produced its expected key events; it does not need another twelve-key event capture. F10 remains recorded as pending until a working external display is available, rather than requesting an inconclusive display-mode check. This status update requests no new F6 test.

Keep the working F1–F3 audio controls, brightness slider and direct F11/F12 keys out of this repeat-check scope. No new collector or driver trace is needed merely to reconfirm those controls. A pending icon action is not implemented simply because its physical key emits an event: the target state must change as described below. If an action remains unavailable, retain its existing evidence and identify a distinct input path before changing a map.

## Verified key events

The complete event report records the expected F1–F12 press and release for every Fn combination. The subsequent seven-trial report confirms that the [reversible preference setup](../../packages/function-keys-setup/README.md) disabled the four plain F9/F10/F11/F12 bindings: IDs 32/33/36/62, with zero modifiers. The journal is applied. Modified shortcuts and the F14/F15 brightness bindings remain enabled. A normal restart refreshes macOS shortcut consumers; application behavior after that refresh still requires confirmation.

Observer 1.1.1 completed all seven targeted windows without interruption:

| Physical press | Observed session event | Consequence |
|---|---|---|
| Direct F4 | No matching retained event | Inspect the driver/firmware path before assigning microphone mute |
| Direct F5 and Fn+F5 | F5, keycode 96, numeric flags 8388864, matching down/up | The two presses are indistinguishable in this session capture |
| Direct F7 | No matching retained event | Inspect the driver/firmware path before assigning airplane mode |
| Direct F8 | No matching retained event | Inspect the driver/firmware path before assigning camera control |
| Direct F9 | Command-L, matching down/up | A global chord replacement would also affect normal Command-L |
| Direct F10 | Command-P, matching down/up | A global chord replacement would also affect normal Command-P |

The input device exposes a writable master mute control, enabling an F4 action once its trigger is established. An empty session window does not establish that firmware produced no event. The complete modifier flags do not prove physical Fn state.

The [driver diagnostic](../../packages/function-key-scancodes/README.md) was prepared to compare VoodooPS2Keyboard traces for these keys and ordinary Command-L/Command-P. Its laptop report stopped after three empty F4/F5/Fn+F5 windows: trace visibility was not confirmed by the positive controls, and logging restoration is verified. No raw key identity can be inferred from this report. Further keyboard diagnostics are deferred. Distinct raw sequences can justify a narrow keyboard mapping; identical sequences cannot safely be separated by a global chord replacement. The driver's trace is not a complete PS/2 wire capture. If a key has no retained trace, both earlier driver handling and the verified Lenovo VPC path remain candidates requiring their own evidence.

F5 can also be assigned to a browser's own Reload menu command through macOS [App Shortcuts](https://support.apple.com/guide/mac-help/mchlp2271/mac). This preserves the F5 key identity received by other applications and applies equally to direct F5 and Fn+F5 inside that browser. The exact localized menu title must be checked, and assigning its new equivalent can replace the existing Command-R equivalent. The user confirmed F5 reload after the browser-specific setup on October 21. This does not establish a distinct physical Fn signal.

Observer 1.0 marked all trials interrupted while still recording the positive key identities above. It reused a tap across intentional disable/enable operations, allowing queued disable notifications to affect the next trial. Version 1.1 creates a fresh tap per window, records genuine interruption reasons, and supports a seven-trial targeted capture. Missing events in the initial interrupted windows do not establish a missing firmware event.

### Passive HID observation checkpoint

The current `hidutil help` has no monitoring subcommand. `hidutil list` exposes two `IOHIDKeyboardEventDevice` devices, including one with PS2 transport, plus separate consumer/vendor services. Enumeration alone is not evidence of event delivery. The [passive HID observer](../../packages/hid-key-observer/README.txt) uses public IOHIDManager input-value callbacks, records device identities separately and checks a same-device/element F5 press and release before any target trial. Failure of that control stops the capture as inconclusive. It neither seizes devices nor changes keyboard properties, preferences, drivers or the EFI. Native compilation/self-tests and the laptop's actual capture remain separate checkpoints. A missing HID event cannot establish absent PS/2 activity or absent ACPI VPC notifications.

### Existing diagnostic and rollback tools

The setup below is retained as the record of the already-applied four-shortcut change and for recovery. It is not a request to repeat the completed seven-trial capture for the current laptop. Its original invocation after extraction into Downloads is:

```bash
bash "$HOME/Downloads/S540-function-keys-setup/PREPARE-FUNCTION-KEYS.command"
```

The setup's targeted prompts produce a private report ZIP on Desktop. A normal restart refreshes macOS shortcut consumers. The original configuration of the four preference fields can be restored through the included `RESTORE-FN-SHORTCUTS.command`. This operation does not load a new EFI component. The current remaining check concerns application behavior after that refresh, not replaying the capture.

The [native event observer](../../packages/function-key-events/README.md) records separate direct and Fn trials for all twelve keys. Its native executable is built on macOS and needs no developer tools on the laptop. It observes only allowed function/media events during the requested trials and does not modify the EFI or keyboard preferences.

The event stream can establish distinct inputs for a mapping. A missing matching event cannot distinguish a scan code discarded by VoodooPS2 from a firmware/ACPI-only action. The physical Fn key may be handled by firmware; the macOS function modifier flag is not proof that physical Fn was held. No remapping is applied until the actual input path is identified.

The original S540 tables contain a Lenovo `VPC2004` device and a generic VPC notification path. The [firmware hotkey reference](../reference/firmware-hotkeys.md) records the verified methods and separates protocol queries from state-changing commands. The original dumps remain private.

F4 requires a writable Core Audio input-mute control and state verification; reducing input gain is not a substitute for mute. F5 reload must be owned by the browser or use a proven distinct input. F9 uses the normal lock-screen action after its trigger is distinguished from ordinary Command-L. F10 requires a working external display and an explicit choice of display mode, without consuming ordinary Command-P.

F7 must verify both Wi-Fi and Bluetooth power state before claiming airplane mode. The official EFI now uses the working native-menu Wi-Fi configuration; a service label or network-service enablement is still not evidence that the radio is off. F8 needs a confirmed camera power/privacy path; merely opening privacy settings or closing a camera application is not camera disablement.

## Brightness diagnosis before the fix

The October 14 report contains four observations: F11, F12, Fn+F11 and Fn+F12. Brightness stays at 1024 and no brightness indicator appears. The reported range is 0–1024, so the panel was already at maximum; brightness-up alone is not a useful test at that level.

The initial runtime exposed an active AppleBacklightDisplay and the internal panel route `GFX0.DD1F`. `DD1F` and `DD02` were present beneath the integrated GPU. The mounted boot configuration already enabled SSDT-XOSI and the `_OSI → XOSI` rename. BrightnessKeys was absent from that initial report.

The [previous firmware analysis](../status/hardware.md) records `_Q8E`/`_Q8F` sending `0x86`/`0x87` notifications to `GFX0.DD1F`, subject to firmware conditions. These notifications match [BrightnessKeys 1.0.3](https://github.com/acidanthera/BrightnessKeys/tree/36820d11327f8aee859997c19f46e24d854ddee7). The runtime panel route also matches that driver's DD1F fallback. This supports an add-only test; the initial snapshots do not establish that the firmware emitted a notification.

## Earlier BrightnessKeys installation and rollback

This section preserves the original companion installation and recovery procedure. Brightness is already working on the official EFI; the procedure is not the next test for that configuration.

The `S540-brightness-keys-v2` package adds the official **BrightnessKeys 1.0.3 RELEASE** bundle and one enabled `Kernel → Add` entry to the current boot EFI. It retains the existing function-key mappings, Intel framebuffer, `-igfxblr`, audio, ACPI and identity settings. The personal configuration backup stays on the boot device.

The installer checks the driver manifest, OpenCore version, current and candidate configurations, and the private rollback snapshots. It stops if the configuration or owned files differ from the expected state. Brightness now works on the laptop; the first EFI release remains unchanged and does not include this companion driver.

Extract the package to Downloads and run:

```bash
bash "$HOME/Downloads/S540-brightness-keys-v2/TEST-BRIGHTNESS-KEYS.command"
```

The default boot directory is `/Volumes/240 GB`. If its mount point differs, pass the exact boot directory as the final argument.

For the original companion installation, validation after restarting through that boot device consisted of:

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

The recorded ordinary Fn function-key path and working audio and brightness controls remain the baseline. The touchpad toggle has now also been reconfirmed on the current installation; retain it while the remaining direct actions are addressed.

## FAT boot-volume metadata

Version 2 uses data-only copies for the configuration snapshots and recognizes validated AppleDouble sidecars and Finder metadata. It retains these metadata files. Real configuration, manifest and driver hashes, backup ownership and all rollback guards remain enforced.

The private backup format and driver payload are compatible with version 1. A valid interrupted backup can be resumed; keep `backup-function-keys` in place. Unexpected files still stop the operation, and the error now includes the filename.



