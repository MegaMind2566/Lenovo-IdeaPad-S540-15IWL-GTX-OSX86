# Keyboard driver scan-code diagnostic

This companion records ten short driver trace windows for the S540 keyboard:
F4, F5, Fn+F5, F7, F8, F9, F10, ordinary Command+L, ordinary Command+P, and Fn alone.
It helps compare driver-level identities before choosing any key mapping.

The initial laptop report did not confirm trace visibility; the F5 controls
stopped the collection after three empty windows. Logging restoration was
verified. Further keyboard diagnostics are deferred, and no mapping is inferred
from this report.

The package changes no EFI files, ACPI tables, key maps, symbolic shortcuts, audio
settings, or firmware settings. Nothing is installed and no restart is needed.

## Run

Extract `S540-function-key-scancodes.zip` into Downloads. Run:

```bash
bash "$HOME/Downloads/S540-function-key-scancodes/COLLECT-SCAN-CODES.command"
```

The administrator password is requested before logging starts. No Xcode or Input
Monitoring permission is needed. After each prompt, press ENTER, wait for NOW,
press only the requested keys, and release every key within three seconds. Fn
and Command must be pressed inside the window, not held before NOW. Wait for OFF
before typing again. Attach `FUNCTION-KEY-SCANS-*.zip` from the Desktop.

## Scope and restoration

Only a unique `ApplePS2Keyboard` service with numeric `LogScanCodes = 0` is accepted.
The loaded driver must be `as.acidanthera.voodoo.driver.PS2Keyboard` version 2.3.7,
x86_64, started, with the verified official RELEASE Mach-O UUID
`efa883f4-7558-3e98-a352-e202cb3dfaaf`. The corresponding binary SHA256 is
`b55758219af1b12b1c0e5e116ff1ee65dc5d8484086e5231103c242a5858a1e5`.
An on-disk EFI copy alone is not used as proof that this driver is loaded.
Missing or mismatched loaded metadata stops the diagnostic before capture.

A privileged logging owner alone changes `LogScanCodes` to numeric 2 for each
window and restores the original numeric 0 with readback before OFF. Its independent
three-second timer keeps the active window bounded even if the guardian hangs or
dies. The guardian records the filtered stream and requests numbered windows;
it cannot enable logging. Logging stays off while waiting for a prompt. The
guardian has a nine-minute hard session deadline. The separate logging owner
also restores after guardian pipe EOF, a termination signal, or its own ten-minute
deadline. An exclusive root-owned lock prevents another copy starting until the
logging owner finishes. The empty lock file can remain under `/var/run`.
No setting survives a normal reboot.

Do not run other keyboard diagnostics or change `LogScanCodes` concurrently.
An unexpected value is treated as a conflict, not overwritten. The final report
states whether restoration was verified. Killing every privileged helper or a
kernel failure is outside the watchdog guarantee; reboot restores the stock
driver default if restoration cannot be verified.

## Privacy and interpretation

The driver emits scan-code traces into the macOS unified system log during each
window. These numeric transitions can encode any keys pressed then. Press no
passwords or unrelated text. The private report keeps at most 128 numeric
raw/mapped/ADB transitions per trial; it does not copy full system log records,
process paths, registry dumps, device identifiers, or account information.

Only the exact audited `ApplePS2Keyboard: sending key` trace grammar is accepted.
Each trace must have a parseable source timestamp inside its enabled window;
delivery time alone never assigns a trace to a trial. Missing source timestamps,
clock changes, truncation, or an interrupted capture are reported and prevent
reliable interpretation. The F5 trials are positive controls for log visibility;
the remaining prompts are skipped if both controls fail to show an attributed
ADB `0x60` press and release pair.
Empty traces cannot prove that the firmware sends no PS/2 event.

This is a driver scan-code trace, not a raw firmware packet dump. Upstream logging
occurs after macro inversion and several special handling paths. Identical traces
must not be remapped globally on a timing guess. Other keys and shortcuts must be
preserved, including normal Command+L and Command+P.

The build runs pure parser, loaded identity, restoration decision, protocol,
deadline and privacy fixtures. Actual trace availability on Tahoe and hardware
key behavior require the laptop report.

## Primary references

- [VoodooPS2Keyboard 2.3.7 source](https://github.com/acidanthera/VoodooPS2/blob/bdbf80639936701337f4574bae8c3ea25bb8dd3d/VoodooPS2Keyboard/VoodooPS2Keyboard.cpp)
- [Official 2.3.7 release](https://github.com/acidanthera/VoodooPS2/releases/tag/2.3.7)
- [Apple public KextManager loaded metadata API](https://github.com/apple-oss-distributions/IOKitUser/blob/main/kext.subproj/KextManager.h)

The helper is original MIT-licensed userspace code. No upstream driver code is
copied into or distributed with this package.
