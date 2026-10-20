# Isolated nano-work GPU identity successor

This source-only successor applies after the frozen first-transaction package
from checkpoint `a60109e4cf48b7614514f8565fae2d2325bfc359`. It changes no frozen
package, production profile, descriptor row, kernel entry or gate mask. The
generic original-lock predicate remains `NV_ERR_NOT_SUPPORTED`. No GSP/DMA-stop
receipt or final owner/text release is issued.

The existing nano WORK descriptor authenticates the callback, flags and borrowed
event. It does not authenticate `nv_work_item_t.gpuInstance`. The original worker
uses that field both to acquire a GPU lock and to resolve the callback target.
An integer copied from a work item is insufficient evidence of the target's
association with the transaction.

The additional protocol reserves a single `(transaction generation, exact nv,
actual OBJGPU, instance)` before `osAttachGpu` writes either reciprocal pointer.
It publishes the immutable tuple only after both real writes. Duplicate or
replacement attachment cannot overwrite the original association. Publication
reads actual API ownership; queue admission and worker entry compare metadata
against cached scalars and perform no private-state or GPU-manager lookup under
the queue guard. Immediately before the original GPU callback, the typed bridge
revalidates the actual resolved object and its `nv` under the acquired GPU token.

| Source boundary | Pinned source anchor | Additional obligation |
| --- | --- | --- |
| Attach publication | `osinit.c:300–322`; `gpumgrAttachGpu` requires API ownership at `gpu_mgr.c:1528` | Reserve before the reciprocal writes; publish after them and before registry/engine setup. |
| Queue production | `os.c:764–808` | Read the real `gpuInstance`; refuse before queue publication and the producer's failure free. |
| Worker dispatch | `osapi.c:744–812` | Recheck immutable metadata at entry, then the actual object after GPU lookup; preserve lock release on failure and publish failure before done frees. |
| Attach failure | `gpu_mgr.c:1619–1636` and V3 `osInitNvMapping` | Preserve mask/count, capabilities, DPC state, GPU registry, attach arguments, pending device and GPU lock before rollback. Restore only a visibility token actually acquired by this call. |
| Detach | `gpu_mgr.c:1646–1681` | Check the actual GPU's deletion permission before any pending-client, DPC, capability or registry mutation. |
| Private writers | `RmInitPrivateState`, `RmClearPrivateState`, `RmFreePrivateState`; public wrappers take no API lock | Before binding, only the actual transaction master may construct private state. After exact binding, refuse private replacement/clear/free; the candidate has no final release issuer. |
| Context bookkeeping | `s540GspContextReleaseOriginalState` | Check the same private-state permission before private-owner flags could be cleared. |

The attachment error path deliberately retains its partial owners. The original
void deletion API may refuse an unknown GPU while its caller still unlinks the
registry. The successor therefore refuses an unknown GPU at detach entry; it
does not add an OWNER descriptor or claim successful GPU destruction. Healthy
final detach would need a separate reviewed owner/deletion contract.

GPU construction and the event bus begin before `osAttachGpu`. Earlier
constructor and HAL-binding rollback families remain open and are not covered
by this additional attachment guard. RC, pending timer replacement, event/owner
policies, direct IRQ participation, PM deadline, aggregate stack and hardware
stop remain separate admission gates.

`prepare.py` accepts explicit `--upstream`, optional `--v3-root` and `--output`.
It verifies the exact parent freeze and dependencies, replays strict overlays,
and emits complete generated translation units, the additional original patch
and a source manifest below the output directory. Generated files never belong
in this package. Validation reports will distinguish actual source bodies and
real service/record implementations from explicit hardware and original lock
endpoint controls.

`check.py` replays the frozen Host retention overlay itself. An optional
`--host-overlay` is accepted only if its complete inventory matches that fresh
replay. The V3 private namespace requires the generated
`combined-profile-v3/prospective-private-namespace.h` wrapper. Its absolute
baseline include must name an ordinary canonical file with independently
pinned baseline bytes. The wrapper is reconstructed byte for byte from the
frozen V2 alias contract, so different native checkout paths do not require the
same raw wrapper hash. Extra directives, changed aliases and symlinks are
refused. All actual compiler dependencies are recorded and checked
again after both variants finish. `compile_full.py` applies the same namespace
check and compiles the complete changed `osinit.c`, `osapi.c`, `gpu_mgr.c`, typed
bridge, strong record, context and real queue/timer/services backends.

The executable controls retain the original `nv.h` ABI and execute 15 complete
source bodies: the parent's 12 work/timer bodies, with the modified worker, plus
the actual proposed attach/private-clear/private-free bodies. The strong
record, cancellation participants, work queues, timers and Host retention code
are real. API/GPU tokens, GPU-manager lookup, runtime stack, empty timer list and
hardware-time endpoints are explicit CPU fixtures. The extra owner/event rows
remain confined to this test executable; production descriptors are unchanged.

Thirteen independent cases cover healthy original dispatch; duplicate attach;
unreserved publication; missing API ownership; queue production before binding;
wrong GPU instance; replacement/missing/wrong-`nv` resolved GPUs; missing GPU
token; recovery/private cleanup refusal; a foreign-thread refusal between the
actual attachment stores and publication; and metadata mutation between queue
admission and worker entry. The latter uses the real queue behind a held first
action, then confirms the second original action never runs and its event
borrower remains retained.

Local validation passes 39 assertions in each plain and fatal
ASan/UBSan/function-sanitizer variant, plus nine x86_64 macOS kernel-target
compile actions. These are Linux CPU/cross-compiler controls against the exact
frozen parent, not native Apple execution or a hardware test. See
`LOCAL-CONTROL-VALIDATION.json` for report hashes and the remaining boundaries.
