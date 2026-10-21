# S540 Tasti 0.1.1 — companion contract

Intel macOS 13 or later. This user-session companion uses the unchanged
`S540HotkeysVPC` **0.1.0** driver. App 0.1.1 fixes the decoding of its unsigned
32-bit registry fields and implements the requested direct F9 screen lock.
No developer tools are needed on the target machine.

Install `/Applications/S540Tasti.app`; the package's `org.s540.Hotkeys`
LaunchAgent starts it as the logged-in user. Bundle identifier:
`org.s540.Hotkeys`; executable: `Contents/MacOS/S540Tasti`; LSUIElement.
One instance per user is enforced by a private advisory lock. The menu-bar title
is **S540**. The app waits for driver approval/restart and attaches when Ready.

| Key | Action and confirmation |
| --- | --- |
| F4, driver mask bit 8 | Toggle the default CoreAudio input's master mute property. Requires property availability, writability and readback. No recording or gain changes. Missing writable master mute is reported in the menu. |
| F7, driver mask bit 13 | Turn Wi-Fi and the Bluetooth controller off, then restore their previous combination. Both actual power states are read back. This controls the two radios, without asserting a global macOS airplane-mode flag. |
| F8, driver mask bit 7 | The driver handles the firmware camera command. The app displays its actual firmware state/readback result. |
| F9 directly, or Command+L | Request screen lock using Apple's Control+Command+Q shortcut. F9 emits Command+L on this S540, so **Command+L also locks the screen globally, including on other keyboards**. Its previous browser-address action is replaced as explicitly requested. |
| Fn+F9 | No app mapping or listener. It remains an ordinary F9 event. |

F9 uses a user-session active CGEventTap. Only L keycode 37 with Command and
without Control, Option or Shift starts ownership. Its down and corresponding
up are consumed, including repeats; one physical down requests one lock.
Other combinations pass through. A release is consumed only if its down was
consumed. Adding Command while plain L is already held does not capture that
press. No text, raw event stream, or keyboard history is printed or saved.
All hardware actions run on the serial action queue, outside the event callback.

Existing `EnableFnF9=true` or `EnableLockKeys=true` is migrated once to
`EnableF9=true`. The old Fn+F9 listener is removed. The same app bundle reuses
available **Monitoraggio input** and **Accessibilità** permissions; if macOS
requires renewed access, the menu reports it. **Abilita F9 / ⌘+L per il blocco…**
requests these permissions. **Disabilita F9 / ⌘+L per il blocco** removes the tap
and cancels queued requests. Startup and `--status` never prompt. F4/F7/F8 do
not depend on these permissions. There is no second login-item registration.

The screen-lock status says **request sent**, rather than claiming independent
verification that the screen is locked. The system Control+Command+Q shortcut
must retain its normal lock action. The tap resets its held state and event
baseline after a system disable, permission refresh, or wake. Timeout,
disabling and opt-out reset ownership and recover without claiming old key
presses. Events lost during that interval are never replayed as a later lock.

Bluetooth uses the private exported
`IOBluetoothPreferenceSetControllerPowerState(int)` symbol resolved with
`dlsym`, then reads `IOBluetoothHostController.powerState`, not discoverability.
If that control is unavailable, F7 reports the limitation without changing
Wi-Fi. Wi-Fi uses CoreWLAN `setPower:error:` and can be refused by system policy.
The previous radio combination is saved before changes; a save failure prevents
the action. Failed attempts restore only components changed by that attempt
whose observed state still equals its requested target. Restoration is read
back. An unresolved timeout is reported as unconfirmed even if the current
state still reads as the original state. Quitting preserves intentional
radio-off choices.

Only numeric driver values and fixed feature-status strings are stored under
`~/Library/Application Support/S540Tasti`, mode 0700: a radio snapshot, runtime
status, and an instance lock. No audio, text, passwords or device names are
collected.

## Driver contract and the 0.1.1 fix

Match exactly one IOService class `S540HotkeysVPC` with explicit
`CFBundleIdentifier=org.s540.HotkeysVPC`. Obtain its registry ID and copy the
single immutable `Snapshot` property every 200 ms. Never combine its top-level
aliases. The app makes no EC calls. Required fields:

```
Schema: integer 1
Version: string "0.1.0" (driver version, distinct from app version)
CFG: uint32 bit pattern 0xFE0D0014
State: string Ready | Fault | Stopping
Ready: Boolean
Awake: Boolean
EventSequence: unsigned integer
EventRing: chronological array, max 32 dictionaries {seq, mask, time_ns}
CameraState: uint32 0 | 1 | 0xffffffff (unknown)
LastCameraResult: integer
```

Apple's IOKit deserializer creates a signed CFNumberSInt32 for OSNumber values
with width up to 32. Consequently CFG can arrive as `-32702444` and unknown
CameraState as `-1`. `UInt32Bits` accepts only non-Boolean integer CFNumbers,
requires lossless conversion to signed 64-bit, bounds the value to
`INT32_MIN..UINT32_MAX` with mathematical NSNumber comparisons before any
scalar conversion, and converts that range to its uint32 bit pattern. This
prevents an unsigned NSNumber such as UINT64_MAX from wrapping to signed -1.
Only CFG and CameraState use this decoder. Sequence/time decoding stays strict
and unsigned. Boolean, floating-point, string and oversized values are rejected.
Contract failures identify the field, such as `driver-contract-CFG-type-invalid`
or `driver-contract-Version-mismatch`, in the menu and read-only status.

Ring sequence IDs must increase strictly. New IDs must be contiguous through
EventSequence. Startup, wake, a different registry ID, or becoming Ready creates
a new baseline and ignores historical events. A gap or invalid ring discards
pending actions and reports an error. No action is automatically retried.
F4/F7 have a 300 ms quiet debounce per bit, updated on every repeat. Driver and
screen-lock requests older than three seconds are discarded. Driver event age
uses `mach_absolute_time`, matching its uptime clock; Quartz event timestamps
are nanoseconds since startup. Sleep and termination immediately set an atomic
cancel flag. An already-submitted radio setter gets its bounded readback window
before recovery; cancellation prevents new actions and the next component.
Recovery can finish a confirmed owned change. Wake cannot clear a newer sleep
or termination request.

Camera results: 0 not requested, 1 unsupported, 2 changed and verified,
3 debounced, 4 invalid state, 5 readback mismatch, 6 protocol failure,
7 firmware already changed and read back. Results 2/3/7 display confirmed state
only for CameraState 0 or 1. The driver owns camera control and debounce.

## Build and validation

Native build with an existing macOS SDK on the build machine:

```
clang -fobjc-arc -arch x86_64 -mmacosx-version-min=13.0 \
  -Wall -Wextra -Werror S540Tasti.m -o S540Tasti \
  -framework Cocoa -framework Foundation -framework CoreAudio \
  -framework CoreWLAN -framework IOBluetooth -framework IOKit \
  -framework ApplicationServices
```

The supplied Info.plist belongs in Contents and the binary in Contents/MacOS.
The parent builder signs and validates the app; it reuses the previously built
driver 0.1.0 unchanged. No additional assets or target-side compilation are
needed.

`S540Tasti --self-test` checks pure policies, real signed CFNumberSInt32 fixtures
for CFG and unknown CameraState, invalid types/ranges, driver-version separation,
and direct-lock pass/consume ownership. Each assertion is named and evaluated
independently. Failure JSON includes expected/actual results and fixed fixture
values, CF/Objective-C types and scalar-conversion results. No live data enters
these diagnostics. It prints JSON and exits 0 on success.
No hardware access, files, permission checks, prompts, tap creation or actions
are performed. Portable policy fixtures:

```
cc -std=c11 -Wall -Wextra -Werror policy_tests.c -o policy-tests
./policy-tests
```

`S540Tasti --status` is read-only JSON: schema, app_version,
expected_driver_version, driver_found, driver_ready, driver_status, permissions,
f9_enabled, command_l_locks_screen, fn_f9_enabled=false, valid driver_snapshot,
master-mute availability, current radio availability/power, and same-version
fixed feature statuses when available. It creates no files, toggles nothing,
and does not require a running app instance. Normal launch refuses root/setuid
execution. SIGTERM waits for the current serialized operation and then exits.

The 40 portable fixtures pass on the packaging host. Native compilation and
`--self-test` are validated by the parent app-only build; no additional user
collector or repeated hardware test is required by this fix.

Primary API references:

- https://github.com/apple-oss-distributions/IOKitUser/blob/main/IOCFSerialize.c#L1309-L1322
- https://github.com/apple-oss-distributions/IOKitUser/blob/main/IOCFUnserialize.yacc#L1016-L1033
- https://developer.apple.com/documentation/coregraphics/cgeventtapcallback
- https://developer.apple.com/documentation/coregraphics/cgeventtimestamp
- https://developer.apple.com/documentation/coregraphics/cgpreflightlisteneventaccess()
- https://developer.apple.com/documentation/corewlan/cwinterface/setpower(_:)
- https://developer.apple.com/documentation/iobluetooth/iobluetoothhostcontroller/powerstate
- https://github.com/toy/blueutil/blob/main/blueutil.m
- https://support.apple.com/102650 (Control+Command+Q)
