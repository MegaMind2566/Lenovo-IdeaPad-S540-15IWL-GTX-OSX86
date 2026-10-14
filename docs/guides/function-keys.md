# Function keys and brightness

The brightness slider works. F11/F12 do not currently change brightness. With Fn, the normal F11/F12 events reach macOS and can activate its Desktop or Mission Control shortcuts. F1–F3 mute and volume controls work.

## Diagnostic result

The October 14 report contains four observations: F11, F12, Fn+F11 and Fn+F12. Brightness stays at 1024 and no brightness indicator appears. The reported range is 0–1024, so the panel was already at maximum; brightness-up alone is not a useful test at that level.

The runtime exposes an active AppleBacklightDisplay and the internal panel route `GFX0.DD1F`. `DD1F` and `DD02` are present beneath the integrated GPU. The mounted boot configuration already enables SSDT-XOSI and the `_OSI → XOSI` rename. BrightnessKeys is absent.

The [previous firmware analysis](../status/hardware.md) records `_Q8E`/`_Q8F` sending `0x86`/`0x87` notifications to `GFX0.DD1F`, subject to firmware conditions. These notifications match [BrightnessKeys 1.0.3](https://github.com/acidanthera/BrightnessKeys/tree/36820d11327f8aee859997c19f46e24d854ddee7). The runtime panel route also matches that driver's DD1F fallback. This supports an add-only test; the initial snapshots do not establish that the firmware emitted a notification.

## Reversible BrightnessKeys test

The `S540-brightness-keys` package adds the official **BrightnessKeys 1.0.3 RELEASE** bundle and one enabled `Kernel → Add` entry to the current boot EFI. It retains the existing function-key mappings, Intel framebuffer, `-igfxblr`, audio, ACPI and identity settings. The personal configuration backup stays on the boot device.

The installer checks the driver manifest, OpenCore version, current and candidate configurations, and the private rollback snapshots. It stops if the configuration or owned files differ from the expected state. The first EFI release remains unchanged while this driver is under evaluation.

Extract the package to Downloads and run:

```bash
bash "$HOME/Downloads/S540-brightness-keys/TEST-BRIGHTNESS-KEYS.command"
```

The default boot directory is `/Volumes/240 GB`. If its mount point differs, pass the exact boot directory as the final argument.

After restarting through that boot device:

1. Set the brightness slider to approximately half.
2. Try the brightness-marked F11/F12 keys without Fn. Check both the indicator and the panel brightness.
3. Check that Fn+F11/F12 still produce their ordinary function-key shortcuts.
4. Check F1–F3 mute and volume.
5. Run the included collector and keep the resulting private ZIP:

```bash
bash "$HOME/Downloads/S540-brightness-keys/COLLECT-FUNCTION-KEYS.command"
```

Its BrightnessKeys snapshot can show `VersionInfo`, `BrightnessPanel` and `BrightnessKeyRouted`. The routing properties are written when the driver receives a supported notification. A loaded driver with no routed event requires a separate review of the firmware conditions; it does not justify a generic DSDT or ThinkPad patch.

To restore the exact previous configuration and remove the verified test bundle from active loading:

```bash
bash "$HOME/Downloads/S540-brightness-keys/RESTORE-BRIGHTNESS-KEYS.command"
```

Restart after restoration. If the current configuration was edited after installing the test, the restore command stops to avoid overwriting those edits.

## Source and scope

BrightnessKeys uses the existing Lilu dependency; it has no additional Tahoe beta boot argument. Its absence of a version gate is not a hardware compatibility result. The test remains pending until the laptop confirms driver loading and both brightness directions.

Other function keys will be handled in the same hardware workstream after their actual behavior is recorded. The ordinary Fn function-key path and working audio controls remain the baseline.
