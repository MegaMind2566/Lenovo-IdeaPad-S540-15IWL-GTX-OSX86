# S540 function-key event probe

This read-only package records the actual macOS events produced by the two keyboard layers. It does not remap keys or install a service. The native Intel executable is built on macOS, so Xcode is not required on the laptop.

## Run

Extract the package into Downloads and run:

```sh
bash "$HOME/Downloads/S540-function-key-events/COLLECT-KEY-EVENTS.command"
```

The probe requests **Input Monitoring** only if it is missing. Allow the Terminal or probe entry requested by macOS under **System Settings > Privacy & Security > Input Monitoring**. Quit and reopen Terminal, then rerun the same command. Accessibility is not requested. The package does not reset privacy permissions or remove quarantine metadata.

There are 24 Enter-gated tests. First press each direct F1–F12 key. Then press Fn+F1–F12. After `CAPTURE` appears, press the requested key once and release it within three seconds. Return to Terminal before the next test if macOS switches the desktop or locks the screen. Save work first: the real key actions remain active, including airplane mode, camera controls, screen locking, and display changes.

For a targeted follow-up, run:

```sh
bash "$HOME/Downloads/S540-function-key-events/COLLECT-KEY-EVENTS.command" --targeted
```

This mode contains seven trials: direct F4, F5, F7, F8, F9, F10, then Fn+F5. It preserves the earlier report and does not repeat the full keyboard sequence. Close any dialog before starting the next trial.

The wrapper creates a private report folder and ZIP on Desktop. Attach the ZIP to the conversation. Nothing is uploaded automatically.

## Report scope

The report retains:

- F1–F20 key positions, press/release, repeat status, normalized modifier names and the complete numeric modifier flags.
- Modifier-key changes and media/control button subtype 8 events.
- Command+R or Control+R only during **direct F5**, Command+L only during **direct F9**, and Command+P only during **direct F10**. These exact chords are observations, not assumed mappings.
- The requested physical layer for each trial, matching-event count/status, and actual event-tap interruption reason/time.
- Read-only capabilities of the default input device: channel count and master/channel input mute availability, mutability, and current state. No audio is recorded.
- Existing F1–F20 symbolic shortcut preferences, filtered to numeric shortcut ID, enabled state, function key, keycode, and modifier flags. Absent defaults are not inferred, and character parameters are discarded.
- Existing macOS symbolic shortcuts assigned to F1–F20, including enabled state and modifier flags. Missing preferences are explicit; absent default assignments are not inferred.

Typed characters, other printable keys, mouse data, raw system-defined payloads, device names/UIDs, serial numbers, user names, host names, and personal paths are excluded. Recording is limited to each three-second window and stops when the process exits. Each trial retains at most 64 events.

The event modifier `secondary_fn_flag` is not proof that the physical Fn key was held. The trial label records the layer the user was asked to press. `NO MATCHING KEY EVENT` means that no event passed the report filter during that window. It does not prove that firmware, ACPI, or a device driver emitted nothing. Secure Input, lock transitions, permissions, and event routing can hide events.

Version 1.1.0 creates and closes a fresh passive event tap for each capture window. It does not manually disable/re-enable a shared tap, so intentional-disable notifications cannot contaminate the next trial. Real timeout or user-disabled notifications remain explicit, and positive events are retained even when a capture is interrupted. Earlier positive events are still useful despite version 1.0.0's incorrect interruption labels. Missing events from those earlier interrupted trials remain inconclusive.

If direct F5 and Fn+F5 produce identical keycodes and flags, this probe cannot establish a distinction between them. A global F5-to-refresh remap would affect both layers. The collector does not make that change.

## Native build and self-test

Build on an Intel macOS runner with Apple Command Line Tools:

```sh
mkdir -p bin
/usr/bin/clang -arch x86_64 -mmacosx-version-min=13.0 -O2 -fobjc-arc \
  -Wall -Wextra -Werror src/function_key_events.m \
  -framework AppKit -framework Foundation -framework CoreFoundation \
  -framework CoreGraphics -framework CoreAudio -o bin/function-key-events
/usr/bin/codesign --force --sign - --identifier org.s540.function-key-events bin/function-key-events
bin/function-key-events --self-test
```

The deterministic self-test exercises decoder, targeted trial selection, interruption reason, existing preference filtering, and outside-window privacy guards without creating an event tap, requesting permissions, querying devices, or posting synthetic events. The diagnostic build uses an ad-hoc signature; it is not notarized.

## API references

- [Apple: passive event tap](https://developer.apple.com/documentation/coregraphics/cgeventtapoptions/listenonly).
- [Apple DTS: CGEventTap and Input Monitoring](https://developer.apple.com/forums/thread/707680?answerId=716892022#716892022).
- [Apple: session event tap location](https://developer.apple.com/documentation/coregraphics/cgeventtaplocation/cgsessioneventtap).
- [Apple: NSEvent custom data](https://developer.apple.com/documentation/appkit/nsevent/data1).
- [Apple: media/control event subtype definitions](https://github.com/apple-oss-distributions/IOHIDFamily/blob/main/IOHIDSystem/IOKit/hidsystem/IOLLEvent.h).
- [Apple: media-key IDs](https://github.com/apple-oss-distributions/IOHIDFamily/blob/main/IOHIDSystem/IOKit/hidsystem/ev_keymap.h).
- [Apple: input mute selector](https://developer.apple.com/documentation/coreaudio/kaudiodevicepropertymute).
- [Apple: property mutability query](https://developer.apple.com/documentation/coreaudio/audioobjectispropertysettable(_:_:_:)).
