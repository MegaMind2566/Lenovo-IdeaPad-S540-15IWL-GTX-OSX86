# Retained failed original global construction

This opt-in successor composes after retained diagnostic Host, retained Darwin
backends and the permanent global epoch. It preserves a genuine failing
`sysConstruct_IMPL` outcome before that function begins system teardown.

At the reviewed late allocation failure, sticky Host OOM prevents fresh TLS
allocation. `sysConstruct_IMPL` failure cleanup calls `rmapiShutdown`, whose
resource-server client cleanup needs that allocation. `serverFreeDomain`
ignores the failed client-free status and repeats its unchanged list head.
Returning a made-up success or merely breaking that retry would leave a false
or partly destroyed global state.

The selected original failure label captures the exact failed system and actual
nonzero constructor status under the immutable owner, generation and ordinary
master thread while its original global epoch is in core. The capture works
after sticky refusal and never clears the first error. It returns the actual
constructor status before system/resource/TLS/child cleanup. Two exact generated
`g_system_nvoc.c` guards preserve the captured system's ancestor state and skip
object-create unlink/zero/free cleanup. Failed-create caller output is untouched;
`g_pSys`, the strong epoch and Host allocation records retain their real roots.

The original core outcome is still recorded only after `coreInitializeRm`
actually returns. Its status, actual system-construction status, stronger first
sticky error and later validation status remain separate. Failure does not
publish initialized globals. No epoch resets, retry, original shutdown, physical
free permit, hardware admission or kernel entry is introduced. Nested child
constructors may already have performed their own cleanup before the system
failure boundary; this contract preserves the failed system and its remaining
roots, rather than asserting every earlier field is unchanged.

`prepare.py` emits separate exact `source-successor.json` and
`project-successor.json` manifests. Its `original_transforms` modifies only
`system.c` and `g_system_nvoc.c`; `transforms` modifies only the strong first
transaction record/header. All input/output bytes are recorded. Both new public
exports belong to the existing strong record:
`s540FirstTxnGlobalRetainConstruction` and
`s540FirstTxnGlobalConstructionRetained`.

`check.py --upstream ... --composition ... --output ... --cc ... --cxx ...
--host-control --jobs 6` compiles the full actual original inventory and actual
project inventory. It runs existing global-epoch scenarios and a separate
process for every observed Host allocation position, including 154, plus the
first unobserved position as a terminal control. Observation-only hooks detect
any system or generated cleanup after retention. Both plain and fatal address,
undefined and function sanitizer variants are required. CPU/platform fixtures
remain explicit and unavailable scalar boundaries abort on invocation.

`check_kernel.py --upstream ... --composition ... --output ... --cc ...` uses
the completed composed Darwin project compile plan and actual pinned original
make profile to compile the uninstrumented record, lifecycle, `system.c` and
`g_system_nvoc.c` under `KERNEL` and `__KERNEL__`. This is a compile probe;
production kernel refusal remains closed. Neither checker establishes kernel
execution or GPU/GSP initialization. Current results are recorded separately.

`LOCAL-CONTROL-VALIDATION.json` independently audits the saved plain and fatal
sanitized runs: each has ten scenarios, 154 injected constructor allocation
failures and one terminal control. All sources, objects, binaries and 330 logs
match. The original runner's final status remains failed: its last inventory
guard used a local variable overwritten by the project compilation loop. The
guard now explicitly inventories `output/source`; the corrected full runner has
not been reexecuted. This audit preserves the original failed report and does
not claim complete allocation-failure closure.

The harness also does not establish consistency between the returned stronger
sticky error and `result.startupStatus` after an original optional-allocation
fallback. That diagnostic obligation and the additional postcore TLS failure
positions remain open. The selected production lifecycle and its kernel entry
refusal remain unchanged in this checkpoint.
