# S540 Fn shortcut setup and targeted key events

All twelve Fn combinations already emit their ordinary F1–F12 events. The uploaded event report identifies four enabled macOS shortcuts that consume unmodified F9, F10, F11 and F12. This package disables those four bindings and captures the remaining direct-key inputs.

## Run

Extract the built package into Downloads. Close Keyboard Shortcuts settings and run:

```sh
bash "$HOME/Downloads/S540-function-keys-setup/PREPARE-FUNCTION-KEYS.command"
```

The native preference helper changes only the `enabled` fields of the four verified bindings. It keeps a private rollback journal under `~/Library/Application Support/S540FunctionKeys/`. No administrator password, developer tools or new EFI driver is required.

The observer then requests seven intentional presses: direct F4, F5, F7, F8, F9, F10, and Fn+F5. Press Enter for each step, then press and release the indicated key during its three-second capture window. Existing key actions remain active. Return to Terminal and close any opened dialog before the next step.

If Input Monitoring is requested, allow the Terminal/probe entry named by macOS, quit and reopen Terminal, then rerun the same command. The preference step is idempotent and the private journal is retained.

The private `FUNCTION-KEY-TARGETS-*.zip` report is saved on Desktop. Attach it to the conversation, then restart normally. Preference synchronization verifies saved values; logout/login or restart refreshes macOS's shortcut consumers. The helper does not terminate applications or force a logout.

## Exact preference scope

| Binding ID | Ordinary key | Change |
|---|---|---|
| 32 | F9, keycode 101, modifiers 0 | Disable its macOS global action |
| 33 | F10, keycode 109, modifiers 0 | Disable its macOS global action |
| 36 | F11, keycode 103, modifiers 0 | Disable its macOS global action |
| 62 | F12, keycode 111, modifiers 0 | Disable its macOS global action |

All other entries are preserved, including F14/F15 brightness bindings, Shift variants and Control/Option/Command combinations. `fnState`, EFI, ACPI, graphics, drivers and power settings are not edited. The actual runtime binding structures must match the recorded keycodes and zero modifiers before mutation.

The helper uses user-scoped CFPreferences calls, rejects managed/ByHost conflicts and different console/root users, and checks for concurrent edits before and after writing. Its advisory lock serializes its own instances. CFPreferences does not provide an atomic interprocess compare-and-swap; do not edit Keyboard Shortcuts settings concurrently.

## Restore

```sh
bash "$HOME/Downloads/S540-function-keys-setup/RESTORE-FN-SHORTCUTS.command"
```

Restart afterward. Restore merges only the changed original enabled values into fresh preferences. Unrelated edits survive; reassigned or externally altered target bindings stop restoration. The journal remains available for interrupted-operation recovery.

## Remaining mappings

The direct and Fn F5 trials currently share the same macOS event. A global F5-to-refresh rule would also intercept Fn+F5. F5 stays unmodified until a lower-level distinction is established.

The first F9/F10 report retained only their Command modifier transitions. The targeted observer now permits exact Command-L during direct F9 and Command-P during direct F10, without recording other printable keys or typing. Their identities remain pending until that report is reviewed.

The VoodooHDA default input exposes a writable master mute control. F4 still requires a confirmed triggering event. F7/F8 require their Lenovo firmware event paths and verified radio/camera behavior. This package does not claim those actions are implemented.

The observer uses a fresh passive event tap for each window, avoiding queued notifications from deliberate tap disabling. Positive events from the original report remain useful; missing events in its interrupted windows are inconclusive.
