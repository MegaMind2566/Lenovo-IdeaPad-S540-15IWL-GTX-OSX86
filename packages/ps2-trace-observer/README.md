# Bounded PS/2 trace transport for the S540

The completed HID report captures Fn+F5, captures no HID events for direct
F4/F7/F8, and shows the same HID sequence for F9 and ordinary Command+L.
This diagnostic checks the driver's earlier trace point without a Linux USB.
It does not implement a key mapping or establish absent firmware events.

The original `function-key-scancodes --failsafe` executable is reused unchanged
from workflow run `38614049964`, artifact `11918499219`, source commit
`b8461368dac069de2d8f8b7911e29cd206b6bbc3`. Its original native build passed
64 fixtures. No new native build is requested or needed for assembly.

The shell keeps the root failsafe's identity checks, lock, three-second windows,
and restoration protocol. A separate `log stream` uses a broader predicate,
preserves errors, and binds numeric records to the actual registry service name
and source timestamps. Only a valid Fn+F5 control authorizes the remaining five
windows. Raw trace files remain temporary. F10, NVIDIA, and the SD reader are
outside this diagnostic.

Local validation comprises the pure parser fixtures, a Foundation-shaped JXA
adapter stub, and eight isolated Linux PTY shell scenarios. These checks do not
establish execution on macOS or hardware trace visibility. The package runs its
guard and parser self-tests on the laptop before any logging mutation; Fn+F5
then checks the actual transport. The runtime JXA bridge and trace visibility
still require that target run.

```sh
node packages/ps2-trace-observer/test-parser.js
python3 packages/ps2-trace-observer/tests/run_shell_fixture.py
python3 builders/assemble_ps2_trace.py \
  --source packages/ps2-trace-observer \
  --original-artifact /absolute/path/to/original-scancodes-artifact.zip \
  --output-dir /absolute/path/to/new-output
```

Assembly pins the GitHub artifact digest, checks the original package manifest,
and preserves the original ad-hoc signature. The resulting ZIP includes its
own complete manifest, source, native build provenance, and Italian instructions.
See `CONTRACT.md` for parser validation and report semantics.
