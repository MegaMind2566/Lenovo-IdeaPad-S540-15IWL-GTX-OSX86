# Isolated checked timer candidate

This package preserves the existing production checkpoint and prospective v2
profile. It composes a separate timer proposal; it does not enable original
initialization, produce a GPU-stop receipt or close the PM deadline gate.

The checked port exports return the actual existing `cancel_nano` result:
`s540GspTimersCancelNano` and `s540GspTimersDestroyNano`. The public `void nv_*`
callbacks remain wrappers. The original `osCancelNanoTimer` and
`osDestroyNanoTimer` proposal calls the checked exports instead of always
returning `NV_OK`. Real failures retain the service's callback storage and
record the existing sticky refusal.

The original timer proposal preserves event/list/queued state on refusal.
Successful local event retirement follows checked backend completion;
statusful control callers retain their wrapper payload until success. Public
void event APIs remain compatible. Several outer owners still use those void
APIs, so this is not complete owner-destruction admission.

| CPU control | Checks per plain/fatal-sanitized variant | Unchanged original failures |
|---|---:|---:|
| Real checked timer bridge | 16 | 4 |
| Existing public timer ABI | 34 | — |
| Cancellation status | 49 | 10 |
| Original event/list/payload ordering | 384 | 165 |

The checked bridge controls run the actual TimerOriginal implementation and
native Darwin timer backend. They show exact self-cancel/self-destroy errors,
retained failed profiles, and normal cancellation waiting for the direct
callback to return. The remaining source controls compile complete actual
original bodies with full generated types and explicit backend/allocator/IRQ
fixtures. Plain and fatal address/undefined/function sanitizer variants pass.
Complete proposed `os.c`, both timer TUs, the actual checked port C and the
pinned-SDK Darwin timer backend also cross-compile as Mach-O with warnings as
errors and the 4096-byte frame diagnostic. This is not native Apple execution
or hardware evidence for the candidate.

`SOURCE-CONTRACT.json` pins the raw sources, four ordered patches and final
project/original bytes. The first timer-status patch is copied as an unchanged
predecessor. `check_timer_checked.py` strictly replays all patches, verifies
the final hashes, extracts the complete test bodies and runs all 483 controls
per variant. For example:

```sh
python3 packages/nvidia-gsp-bootstrap/prospective-timer-checked/check_timer_checked.py \
  --upstream /path/to/pinned-original \
  --namespace /path/to/verified/S540GlobalRmNamespace.h \
  --output /path/to/separate-output
```

The default requires the existing Intel macOS compiler controls;
`--host-control` explicitly selects the Linux CPU control. Neither mode runs
kernel code. Local reports are preserved under `evidence/`; their absolute
paths identify the historical local compilation, not portable admission.

A direct timer callback can enqueue accepted RM work that still borrows the
event. TimerCancel success does not drain that later work. Actual event
generation/borrow references, producer sealing, pre-lock terminal queue drain
and nonblocking under-lock retirement revalidation remain required. Original
destructors must check a real refusal before freeing any dependent owner;
returning early from a void destructor cannot stop generic NVOC freeing.
[OWNER-GATES.md](OWNER-GATES.md) and [ALL-CALLERS.json](ALL-CALLERS.json) retain
the exact source inventory and lock constraints. All admission fields remain
false.
