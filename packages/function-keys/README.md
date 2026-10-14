# Function-key diagnosis

This read-only collector prepares the deferred function-key batch. It keeps the current EFI, graphics/backlight configuration, audio driver and working F1-F3 controls intact.

Run it in macOS Terminal:

```bash
bash "$HOME/Downloads/S540-function-keys/COLLECT-FUNCTION-KEYS.command"
```

The current boot HDD configuration is read only if `/Volumes/240 GB/EFI/OC/config.plist` is mounted. To read another mounted EFI explicitly, add `--efi-config "/absolute/path/config.plist"`. The disk does not need to be mounted for the device snapshots or manual observations to work.

The collector records panel and keyboard metadata, loaded kexts, and four explicit observations: **F11**, **F12**, **Fn+F11** and **Fn+F12**. Click the desktop before pressing each key. Click Terminal afterwards and press Enter, then answer whether the brightness indicator appeared and the panel brightness changed. Keep the existing BIOS Hotkey Mode, Fn Lock, macOS keyboard settings and brightness-slider position while taking the observations. The initial and final brightness values are retained where macOS exposes them.

The collector does not install an event tap or monitor typed keys. It does not enable keyboard scancode logging. It does not change EFI, NVRAM, SIP, drivers, BIOS settings or registry properties. Your manual brightness-key presses may change brightness through the normal system controls.

Results are saved as a private ZIP on the Desktop. The expanded directory is retained. **Do not commit or publish the report.** Only selected ACPI and component metadata are copied from the optional config; its PlatformInfo and NVRAM sections and the complete configuration are excluded.

For a metadata-only run without the four observations, use `--snapshots-only`. `--output-dir "/absolute/existing/directory"` changes the report destination. No Xcode, Python, administrator privileges or additional driver is required.

## Evidence and limits

The [recorded firmware analysis](../../docs/status/hardware.md) identifies `H_EC._Q8E` and `_Q8F` sending brightness notifications `0x86`/`0x87` to `GFX0.DD1F`, subject to firmware conditions. This is previously recorded evidence; the original OEM tables were not re-read while preparing this collector.

The current EFI already loads SSDT-XOSI and enables the `_OSI → XOSI` OEM rename. The existing wrapper covers Windows queries through 2015. BrightnessKeys is currently absent.

[BrightnessKeys 1.0.3](https://github.com/acidanthera/BrightnessKeys/tree/36820d11327f8aee859997c19f46e24d854ddee7) consumes panel ACPI notifications `0x86` (up) and `0x87` (down). It recognises but does not implement `0x85` (cycle), `0x88` (zero) or `0x89` (display off). It locates ACPI panel devices using display addresses, with `DD1F`/`DD02` fallbacks. It does not map the physical F11/F12 keys directly or consume every vendor-specific Lenovo event.

The read-only snapshots show runtime device matching and exposed brightness changes. **They cannot prove that an ACPI Notify event was emitted when a key was pressed.** A missing change alone does not justify renaming `_Q` methods or adding a ThinkPad-specific NBCF patch to this IdeaPad.

After reviewing the report, a separate, guarded BrightnessKeys-only test is a candidate if the recorded panel route is present. The separate [guarded test guide](../../docs/guides/function-keys.md) describes the BrightnessKeys package. The driver has not yet been confirmed on the laptop or added to the released EFI. Broader Fn remapping requires observed keycodes or a confirmed firmware event path. It will preserve the existing F1-F3 volume behaviour.

Primary source references:

- [BrightnessKeys source and notification definitions, release 1.0.3](https://github.com/acidanthera/BrightnessKeys/tree/36820d11327f8aee859997c19f46e24d854ddee7/BrightnessKeys)
- [BrightnessKeys README](https://github.com/acidanthera/BrightnessKeys/blob/36820d11327f8aee859997c19f46e24d854ddee7/README.md)
- [VoodooPS2 2.3.7 keyboard source](https://github.com/acidanthera/VoodooPS2/blob/bdbf80639936701337f4574bae8c3ea25bb8dd3d/VoodooPS2Keyboard/VoodooPS2Keyboard.cpp)

## BrightnessKeys test package

The separate `S540-brightness-keys` package contains `TEST-BRIGHTNESS-KEYS.command` and `RESTORE-BRIGHTNESS-KEYS.command`, plus this collector. Follow the [test and rollback guide](../../docs/guides/function-keys.md). When using that package, run the collector from `Downloads/S540-brightness-keys`, rather than the original `Downloads/S540-function-keys` folder. Start the brightness checks near the middle of the slider range.
