# S540 plain function-key shortcuts

This native macOS helper releases the four plain F9–F12 keys that the current-user event report found assigned to macOS actions. Fn already produces the correct F1–F12 keyboard events on this S540. The helper changes only the `enabled` field of existing symbolic shortcuts 32, 33, 36, and 62 after checking their recorded keycodes and zero modifier flags.

All other shortcut entries remain unchanged. This includes Shift variants, Control/Option/Command combinations, the working F14/F15 brightness bindings 53/54, and every value and parameter inside the four target entries. The helper does not change `fnState`, keyboard drivers, EFI, hardware actions, or system integrity settings.

## Commands

The distribution includes a precompiled Intel macOS executable. Xcode, Command Line Tools, Python, administrator privileges, Accessibility, and Input Monitoring permissions are not required for this preference operation.

```sh
bin/function-key-preferences --apply
bin/function-key-preferences --status
bin/function-key-preferences --restore
```

Run the executable as the user currently signed in to the desktop. Do not use `sudo`. Close Keyboard Shortcuts before applying or restoring, and do not edit shortcut settings while the helper runs. After a successful change, log out and sign in again, or restart, so macOS reloads its shortcut registrations. The helper does not restart system processes or invoke private refresh utilities.

## Journal and recovery

A private journal is kept at `~/Library/Application Support/S540FunctionKeys/shortcut-journal.plist`. It contains the original four entries, the IDs actually changed, the current account and exact preference scope, and the operation phase. It does not contain a full preference-domain snapshot. Keep it after applying and restoring.

Before a preference write, the helper saves and synchronizes a prepared journal. It then rechecks the fresh preference dictionary, merges the four enabled-field changes, writes through Core Foundation preference services, synchronizes, and checks the result. A prepared operation can resume if execution stops after the preference write. Rerun the same command. A pending restore must finish before another apply.

Restore reads the latest dictionary and restores only the enabled fields changed by this helper. Unrelated later edits survive. It refuses a changed or reassigned target rather than overwrite it. A completed restore is idempotent; the same journal can reapply the original change if those targets still match their original state.

The helper uses an advisory lock for its own instances. Core Foundation preferences do not provide an atomic compare-and-swap operation against other applications. Pre-write comparison and post-write read-back detect many concurrent changes, but cannot remove the small race with another preferences writer. Avoid concurrent editing.

The domain and symbolic IDs are an evidence-backed profile for this machine, not an Apple guarantee that those IDs have the same meaning on every macOS version. Missing, changed, managed, or current-host-overridden bindings are refused.

## Build and checks

Compile on an Intel macOS CI runner with the Foundation and Core Foundation frameworks. Ship the compiled executable; do not compile it on the user's laptop.

`--self-test` runs pure in-memory fixtures. It does not access preferences. Fixtures check preservation of other entries, working brightness bindings, modifier combinations, target parameters, idempotence, interrupted operations, selective restore, malformed journals, and restore conflicts.

The native preference backend uses `CFPreferencesCopyValue`, `CFPreferencesSetValue`, and `CFPreferencesSynchronize` for the exact current-user, any-host domain. It checks `CFPreferencesAppValueIsForced` and rejects a current-host override. It never edits a preferences backing plist or replaces the entire defaults domain.

## Apple references

- [Exact-domain preference reads](https://developer.apple.com/documentation/corefoundation/cfpreferencescopyvalue(_:_:_:_:))
- [Exact-domain preference writes](https://developer.apple.com/documentation/corefoundation/cfpreferencessetvalue(_:_:_:_:_:))
- [Preference synchronization](https://developer.apple.com/documentation/corefoundation/cfpreferencessynchronize(_:_:_:))
- [Managed preference values](https://developer.apple.com/documentation/corefoundation/cfpreferencesappvalueisforced(_:_:))
- [Preference caching and cross-application access](https://developer.apple.com/library/archive/documentation/Cocoa/Conceptual/UserDefaults/AccessingPreferenceValues/AccessingPreferenceValues.html)
