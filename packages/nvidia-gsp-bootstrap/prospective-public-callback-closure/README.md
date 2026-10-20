# Prospective public callback closure

This opt-in composition successor replaces the Work/Timer KERNEL callback
backend with exported IOKit event sources. It leaves the frozen base services,
NVIDIA sources and every hardware/original-entry admission gate unchanged.
The idle target attempt on Darwin 25.6.0 was refused while binding
`_thread_call_cancel_wait`; no successful target load is established here.

Native run 39483421884 passed both links with only Work and Timer recompiled,
1,100 original and 58 unchanged project objects reused, and all 388 final live
imports matched to declared public source exports. The 20-minute job expired
during independent packaging; it produced no deliverable ZIP. After correcting
cache report checkpoints and phase-local input verification, run 39488036361
at `d145d9e01f8470a31d499313957e82b47580358b` passed both native links,
independent verification, strict ad-hoc signature checks and packaging.
The link phase took 583 seconds and packaging took 266 seconds. Final matrices
and fresh post-signature checks remained complete. The new ZIP still requires
the closed target idle load/snapshot/unload check.

## Export and lifetime evidence

The pinned Apple XNU snapshot is `f6217f891ac0bb64f3d375211650a4c1ff8ca1ea`
(`xnu-12377.1.9`), not the exact unpublished target build. Its
`config/Private.exports` contains `_thread_call_cancel_wait` while
`config/Mach.exports` does not. A declaration in `thread_call.h` is insufficient
to establish third-party KPI availability. Neither `thread_call_isactive` nor
`thread_call_wait_once` is in the public export set.

Replacing the wait with `thread_call_cancel` would leave an entering/running
callback. Ordinary ONCE `thread_call_free` can release asynchronously. Direct
SIGNAL mode is private and runs at timer interrupt level. This successor uses
none of these alternatives or a fabricated successful callback/drain.

Each service object owns an `IOWorkLoop`, an `IOTimerEventSource` configured with
public `kIOTimerEventSourceOptionsPriorityWorkLoop` without AllowReenter, and an
`OSData` containing its immutable action/context binding. There is no custom
metaclass. The extra per-object workloop can fail allocation; every partial
construction unwinds and reports `NV_ERR_NO_MEMORY`.

Apple's workloop-priority timer implementation uses its private signaler to
request work; the application action executes under the workloop gate.
`wakeAtTime` schedules that preallocated signaler without taking the gate,
allocating or sleeping. Existing service Guards serialize all scheduling.
This avoids a Guard-to-gate acquisition opposite the callback's gate-to-Guard
order. Arm/enqueue remain available from their existing interrupt contexts.

Cancellation closes timer rearm or queue admission under the service Guard,
then releases the Guard before `IOWorkLoop::runAction`. Gate acquisition waits
for the complete application callback return, including the interval after
logical callback/queue flags have become idle. The gated action calls
`cancelTimeout`: Apple invalidates pending delivery generations and drains its
private interrupt signaler internally. Existing action-thread self-cancel and
self-stop refusals remain intact. A timer keeps the same source for reuse.

Final retirement requires the existing owner contract: all external references
and callers are quiescent, successful drain, successful removeEventSource, then
release event source, binding and workloop. A failed drain/removal retains
objects and reports refusal; it never grants destruction. The Work transaction
binding and retained-backend policy are preserved by exact anchored changes.

Primary sources and exact Git object IDs are recorded in PROVENANCE.json.
`tests/sdk_import_reference.cpp` independently calls the public interfaces
without including this implementation header. The native import/export audit
must still verify the resulting objects against the pinned SDK and export lists.

## Local validation

Run `python .../prospective-public-callback-closure/check.py --sanitize`.
To exercise the actual composed bodies, add `--source-root <composition/project>`.
The test compiles the real transformed KERNEL branches against explicit
concurrent IOKit fixtures. It covers all five construction failure stages,
pending/dequeued/running cancellation, callback rearm, self-refusal, interrupt
arm/enqueue with the gate held elsewhere, concurrent producers, drain/removal
failure retention/retry, and no callback after destruction. An explicit pause
after production idle flags publish but before callback return proves that Stop
waits for the gate rather than trusting those flags.

For composed inputs, retained-backend policy and transaction-record hooks are
explicit fixtures; transaction admission hooks throw if accidentally reached.
The real composed refusal/retention branches and timer-return hook execute, but
this does not validate the independent transaction record or backend policy.

Local ASan/UBSan checks are separate from real IOKit execution. LeakSanitizer's
process inventory is blocked by this host; leak detection is disabled and all
service/framework owner counts are checked explicitly. No local mock, SDK
compile or export audit establishes target loading, GPU initialization or
acceleration. No security setting is changed.
