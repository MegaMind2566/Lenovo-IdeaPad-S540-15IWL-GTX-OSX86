# Permanent control state and empty file table

This isolated source profile supplies five exact original callbacks. It does
not register a character device, file reference or OS event. It does not grant
original GPU entry or produce an installable bundle.

`s540ControlStatePrepare` pulls the actual master/owner/generation from the
strong record before publishing a permanent `nv_state_t` and original
`PORT_SPINLOCK`. The real original spinlock initializer calls the implemented
Darwin allocation service directly, before global `portInitialize` is needed.
There is no reset or final-release API. The retained-backends successor keeps
the direct lock and Host facts alive even when tracked Host heap usage is zero.

`s540ControlStateBindAdapter` checks the exact bound record identity before
dereferencing the original structure, then admits only the selected nonprimary
TU117. Its internal device ordinal is zero; the distinct control ordinal is
the original control constant 255. These are internal identities and create
no `/dev` nodes.

The selected loader exposes no NVIDIA file-descriptor registration or RM ioctl
frontend. Consequently the file-private table is permanently empty. Failed
lookup returns NULL and preserves its output, matching the original failure
branch and its complete callers. A put cannot acquire a valid reference in
this profile. An OS event cannot have a valid originating file. Such unexpected
operations fail-stop after publishing a service refusal; they never return as
if a reference had been released or a notification delivered.

This requires actual source composition, not just the two compiler macros:
the three existing OS-event constructor/notification guard translation units
must be selected, with kernel callbacks and zero-handle GSP event buffers
preserved. The final image must independently exclude `rm_ioctl` and its sole
`allocate_os_event` insertion route. The closed loader source and raw callers
are pinned in `SOURCE-CONTRACT.json`. Compilation alone does not prove this
whole-image exclusion.

The controls execute the actual strong record, retained Host and Darwin sync
backend, three unchanged original port-spinlock bodies and the complete
original event-handle lookup. Six process scenarios cover preowner refusal,
one-shot publication, exact identity/ordinals, failed descriptor lookup,
preserved output, primary-VGA refusal, earlier real crypto refusal, two fatal
boundary counterexamples and an actual accepted queue callback attempting to
publish the master's control state. Original callback metadata/token readers
are the explicitly labelled parent CPU fixtures. Fatal diagnostics use an
explicit process-exit observer so the tests can inspect sticky errors.

There are 44 checks per ordinary and fatal ASan/UBSan/function variant, one
complete exact-header kernel Mach-O compile and six rejected source profiles.
Linux development runs use `ASAN_OPTIONS=detect_leaks=0` because the container's
LeakSanitizer process inspection is unavailable. These checks do not execute
original GPU code, establish target kernel loading or prove stack sufficiency.

```
python3 packages/nvidia-gsp-bootstrap/prospective-control-state/check.py \
  --upstream "$UPSTREAM" --namespace "$NAMESPACE" \
  --composition "$BASELINE_COMPOSITION/composition.json" --output "$OUTPUT" \
  --cc /usr/bin/clang --cxx /usr/bin/clang++
```

Use an unmodified baseline composition. The runner applies the exact retained
Host, direct-backend and global-epoch record transforms itself. Authoritative
execution requires Intel macOS; `--host-control` identifies Linux development
execution and cross-compilation explicitly.
