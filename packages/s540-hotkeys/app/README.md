# S540 Tasti 0.1.0 — companion contract

Intel macOS 13 or later. This is the functional user-session companion for
`S540HotkeysVPC` 0.1.0, not a key logger or a test collector. No developer tools
are needed on the target machine. Install `/Applications/S540Tasti.app` and
let the package's `org.s540.Hotkeys` LaunchAgent start the binary as the logged-in
user. The application does not register a second login item. It stays running
while the driver is pending approval or a restart and attaches when Ready.

Bundle: `org.s540.Hotkeys`; executable: `Contents/MacOS/S540Tasti`; LSUIElement.
One running instance per user is enforced by a private advisory file lock.
The menu-bar title is **S540** and the five status rows show actual outcomes.

| Key | Action and confirmation |
| --- | --- |
| F4, driver mask bit 8 | Toggle the default CoreAudio input's master mute property. Requires `AudioObjectHasProperty`, `AudioObjectIsPropertySettable` and readback. No recording and no gain changes. If the audio driver does not expose writable master mute, the menu reports this limitation. |
| F7, driver mask bit 13 | Turn Wi-Fi and the Bluetooth controller off, then restore their original combination on the next press. CoreWLAN `setPower:error:` and the Bluetooth controller's actual `powerState` are read back. This controls the two radios; it does not assert a global macOS airplane-mode flag. |
| F8, driver mask bit 7 | The kernel driver handles the firmware camera command. The companion displays firmware state/readback failures; it does not simulate camera privacy by changing an icon or permission. |
| Fn+F9, HID page 7 usage 0x42 | Optional screen-lock request using Apple's Control+Command+Q shortcut. Requires the menu action **Abilita Fn+F9…** and the macOS permissions below. The menu confirms that the request was sent, not that the screen is independently verified as locked. |

Direct F9 on the confirmed S540 setup emits the same Command+L sequence as
ordinary application input. That sequence is deliberately left alone. Fn+F9
uses the actual F9 HID usage. The HID manager asks only for F9 values from a
PS/2 keyboard with vendor 0x05ac/product 0xffff, matching `ApplePS2Keyboard`
ancestry and exactly one eligible HID service. No other key values are
processed, printed or saved.

F4/F7/F8 do not depend on Input Monitoring or Accessibility. Fn+F9 is disabled
until the user enables it from the S540 menu. That action requests **Monitoraggio
input** and **Accessibilità** for S540 Tasti. If macOS requires the app to be
reopened after granting access, reopen it or use the installed LaunchAgent;
otherwise choose **Rileggi permessi Fn+F9**. Permission checks at startup and
`--status` never prompt. There is no event tap, Terminal-key logging, or system
keyboard mapping. Synthetic Control+Command+Q follows the current macOS
shortcut configuration and can fail if the shortcut has been reassigned.
**Disabilita Fn+F9** stops its HID listener and preserves the other functions.

The Bluetooth setter is the private exported
`IOBluetoothPreferenceSetControllerPowerState(int)` symbol, resolved with
`dlsym`. The actual `IOBluetoothHostController.powerState` is read back, not
discoverability. This API may be unavailable on a particular macOS/controller;
F7 then reports that radio control is unavailable without changing Wi-Fi.
Wi-Fi changes may also be refused by system policy. Failed attempts restore
only components changed by that attempt whose observed state still equals the
requested target. Readback verifies recovery; a partial result is shown as an
error. A timed-out request whose target was never observed is reported as
unconfirmed, even when the current state still reads as the original state.
The original mix is saved before either radio is changed; a save failure
prevents the change. Quitting does not undo intentional radio-off choices.

Only numeric driver data and fixed feature-status strings are persisted under
`~/Library/Application Support/S540Tasti`, mode 0700: a radio-state snapshot,
runtime status, and an instance lock. No audio, text, passwords, device names,
or key history is collected. Menu/status output is local.

## Driver snapshot contract

Match exactly one IOService class `S540HotkeysVPC`, with its explicit
`CFBundleIdentifier` equal to `org.s540.HotkeysVPC`. Obtain the registry ID and
copy the single immutable `Snapshot` property every 200 ms; do not combine
top-level aliases. The companion makes no EC calls. Required fields:

```
Schema: integer 1
Version: string "0.1.0"
CFG: integer 0xFE0D0014
State: string Ready | Fault | Stopping
Ready: Boolean
Awake: Boolean
EventSequence: unsigned integer
EventRing: chronological array, max 32 dictionaries {seq, mask, time_ns}
CameraState: 0 | 1 | 0xffffffff (unknown)
LastCameraResult: integer
```

Ring sequence IDs must be strictly increasing and all unconsumed IDs must be
contiguous through EventSequence. Startup, wake, a different registry ID, or a
driver becoming Ready establishes a new baseline and ignores historical events.
An invalid ring or sequence gap discards pending actions and reports an error.
No action is retried automatically. A single serial queue handles driver events
and radio/microphone actions. F4/F7 use a 300 ms quiet debounce per bit, with
every observed repeat advancing its debounce timestamp.
Events older than three seconds are discarded, including Fn+F9 requests queued
behind a radio operation. Event age uses `mach_absolute_time`, matching the
kernel's uptime clock. Sleep and termination set an immediate atomic cancel
flag. A submitted radio setter is given its bounded readback window before
recovery; cancellation prevents new actions and the next radio component.
Recovery ignores that flag so a confirmed change can be restored safely.

Camera results: 0 not requested, 1 unsupported, 2 changed and verified,
3 debounced, 4 invalid state, 5 readback mismatch, 6 protocol failure,
7 firmware already changed and read back. Results 2/3/7 display confirmed state
only for CameraState 0 or 1. Awake=false suspends consumption; AppKit workspace
sleep/wake notifications also reset the baseline. The driver owns firmware
camera debounce and actual camera control.

## Build and validation

Native build (an existing macOS SDK is required on the build machine):

```
clang -fobjc-arc -arch x86_64 -mmacosx-version-min=13.0 \
  -Wall -Wextra -Werror S540Tasti.m -o S540Tasti \
  -framework Cocoa -framework Foundation -framework CoreAudio \
  -framework CoreWLAN -framework IOBluetooth -framework IOKit \
  -framework ApplicationServices
```

Copy the supplied Info.plist into Contents and the binary into Contents/MacOS;
the parent package's build script signs and validates the complete app bundle.
No resource files, dynamic helpers, or third-party executable are required.

`S540Tasti --self-test` checks pure policies and strict numeric decoding,
prints JSON and exits 0 only on success. It does not inspect hardware, create
files, prompt, or perform actions. The broader portable policy fixtures are:

```
cc -std=c11 -Wall -Wextra -Werror policy_tests.c -o policy-tests
./policy-tests
```

`S540Tasti --status` prints read-only JSON with `schema`, `app_version`,
`driver_found`, `driver_ready`, `driver_status`, permission flags,
`fn_f9_enabled`, `driver_snapshot` when valid, microphone mute availability,
radio availability/current power states, and saved fixed feature statuses.
It performs no toggle and does not require a running app instance. The normal
application refuses root or setuid launch; the package must launch it in the
user GUI session. SIGTERM waits for the current serialized operation and quits.

The 30 portable policy fixtures pass on the packaging host. Native compilation,
native `--self-test`, bundle/signature checks, and the one final S540 functional
check are tracked by the parent package build rather than claimed here.

Primary API references:

- https://developer.apple.com/documentation/coreaudio/audioobjecthasproperty(_:_:)
- https://developer.apple.com/documentation/coreaudio/audioobjectispropertysettable(_:_:_:)
- https://developer.apple.com/documentation/corewlan/cwinterface/setpower(_:)
- https://developer.apple.com/documentation/iobluetooth/iobluetoothhostcontroller/powerstate
- https://github.com/toy/blueutil/blob/main/blueutil.m
- https://developer.apple.com/documentation/applicationservices/1459186-axisprocesstrustedwithoptions
- https://support.apple.com/102650 (Control+Command+Q)
