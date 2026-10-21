# Parser contract

`parse-trace.js` is self-contained JavaScript. `require()` exports the pure core
for Node tests; `osascript -l JavaScript` calls the `run(argv)` JXA entry point.
No driver state, shell process, permission or EFI setting is changed by it.

```text
osascript -l JavaScript parse-trace.js self-test
osascript -l JavaScript parse-trace.js check RAW PROTOCOL PREFIX [TRIAL_INDEX]
osascript -l JavaScript parse-trace.js report RAW PROTOCOL PREFIX OUTPUT_JSON [STATUS_REASON]
node test-parser.js
```

All file arguments must be absolute paths. Inputs are UTF-8 NDJSON, at most 4MiB
each and newline-terminated. RAW may have one leading `Filtering the log data
using ...` header for exactly `eventMessage CONTAINS "sending key"`, including
the tool's canonical `composedMessage` spelling and quoted display. That header
is only counted and discarded. Midstream, repeated or different-predicate headers
remain invalid. The report writer refuses an existing output file.
The enclosing shell owns private directory permissions, process supervision,
temporary raw-file removal and invoking `sudo` before any logging window.

The literal readiness state emitted by the frozen helper is `failsafe-ready`.
Only this spelling is accepted. Follow it with sequential `armed` / `window-off`
pairs, trial indices 0 through 5, then one `failsafe-restored` with
`logging_restored:true`. Trial IDs are fixed:

| Index | Trial |
|---|---|
| 0 | Fn-F5 positive control |
| 1 | direct-F4 |
| 2 | direct-F7 |
| 3 | direct-F8 |
| 4 | direct-F9 |
| 5 | ordinary-Command-L |

`armed` requires `trial` and positive Unix-seconds `source_start`. `window-off`
requires matching `trial`, `source_end`, `elapsed`, `logging_restored:true` and
`window_complete:true`. Both measured duration and wall-clock interval must be
within 3s +/-0.5s, with their difference at most 0.25s. Overlapping windows,
duplicate messages and messages after the final state are invalid. A live
checkpoint after trial 0 does not require the final restoration message yet.
A final complete report requires all six windows and the final restoration.

`PREFIX` must match `[A-Za-z0-9_. -]{1,80}` and come from the verified runtime
service name. Only the audited message grammar is retained:

```text
PREFIX: sending key HEX=HEX down|up
PREFIX: sending key HEX=HEX, HEX=HEX down|up
```

The middle pair in the remapped form must agree. ADB values are bytes. Scan
normalization permits the driver's extended `e0xx` form and literal index `100`
(the source formatter uses `>256`, not `>=256`). Records contain numeric
`raw_scan`, `mapped_scan`, `adb_code`, `source_offset_ms`, plus boolean `down`.
No `eventMessage`, process path, arbitrary prefix, status text or unrelated raw
JSON property is copied into the report.

Source timestamps accept ISO timestamps with a space or `T`, optional 1-9 digit
fraction, and `Z` or an explicit timezone offset. Calendar dates are validated.
Second/nanosecond pairs preserve sub-millisecond precision. The original decimal
protocol field lexeme is retained for time comparison, including exponent form.
Events are assigned only in `[source_start, source_end)`, without tolerance.
Earlier/later records are excluded and counted, never moved into a window.
Matching traces without attributable timestamps invalidate the source. Kernel
identity is required when process metadata is present; contradictory metadata
invalidates the source. The runtime log predicate is deliberately broad;
the parser applies the verified prefix and available kernel identity afterward.

At most 128 records are retained per trial; exceeding this count invalidates
that trial. Protocol records mixed into RAW are a duplicate-channel failure.
Unknown trace prefixes, malformed matching messages, malformed/truncated NDJSON
and timestamp-order errors are separately counted. No offending text is echoed.

The positive control needs one and only one ADB-F5 down/up pair, mapped scan
`3f`, from the same raw scan. Repeated/duplicate F5 transitions or missing release
are invalid. Empty target windows remain valid observations after a valid
control; they are not interpreted as proof of missing firmware events.

`check` returns JSON and exits successfully only with valid control and valid
requested trial. On failure JXA throws a fixed error, so `osascript` exits
nonzero. `report` writes even a partial or empty startup result as INCONCLUSIVE,
provided the input files exist. No final helper restoration means
`logging_restored:false`. `restoration_unverified` also forces this boolean false.

Shell status reasons `complete`, `positive_control_missing`, `session_error`,
`interrupted`, `restoration_unverified` are supported. Other recognized error
tokens are documented in `normalizeStatus`. Unrecognized strings produce a
constant `external-status-unrecognized`; their content is never saved.

F9 versus ordinary CmdL compares numeric driver sequences only when both windows
are valid and nonempty after a valid control. The result does not install a map
and cannot distinguish anything the driver already merged before its trace.

`self-test` runs pure JavaScript fixtures without Foundation, HID or file access.
Node tests additionally exercise the JXA bridge with Foundation-shaped stubs;
they do not establish native JXA execution on macOS. The enclosing package must
run the self-test with the actual `osascript` before its first logging mutation.
