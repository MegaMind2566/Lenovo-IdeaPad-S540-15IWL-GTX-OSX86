# Candidate lock and drain cancellation

This is a prospective design, not an implemented or approved source profile.
The frozen ten-patch profile is unchanged. Scope is one selected TU117 and the
first experimental original initialization attempt, with no external RM clients.
That restriction does not establish absence of contention: original work items,
timer callbacks and interrupt bottom halves execute on separate threads.

All upstream references below use NVIDIA commit
`1a82fbfda8f321b056eb3568850f9316c5e465c5`.

## Isolated implementation evidence

`rm-lock-cancellation-prospective.patch` implements the API conditional loop and
GPU preflight described below in two copied original source files. It uses the
real `s540GspCancellationCurrentScopeActive`, `CheckCurrent` and `PauseCurrent`
operations. Low-priority API aging is explicitly refused in an active scope;
its original behavior is preserved outside that experimental scope.

`check_rm_lock_cancellation.py` verifies original source hashes, applies the
candidate only to copies, and compiles 25 actual original function bodies. These
include the ordinary Unix nvport wrappers, real original GPU rollback release,
API acquire/release and ownership helpers. The executable links the actual
cancellation record and Darwin synchronization/platform services. Object metadata,
tracing and hardware interrupt operations are explicit fixtures; this is not an
original-header ABI or hardware test.

The candidate passes 30 assertions in plain and fatal ASan/UBSan/function runs;
the same assertions expose 10 failures in the unpatched bodies. Tests cover
asynchronous revocation during actual API reader/writer contention, multi-GPU
preflight without partial token mutation, post-commit GPU rollback, preservation
of ordinary IRQ flags, recursion, safe upgrade, TLS failure and successor lock
acquisition. All actual Darwin service owners are released. Callout binding,
all lockable-mask mutation cases and aggregate PM timing remain unproved.

## Cancellation contract

Use one retained, generation-checked device cancellation record. Operation
revocation is monotonic. Its absolute deadline is independent of original thread
timeout initialization, reset, retry and sleep-time exclusion. A bounded pause
checks the record before and after sleeping and never sleeps with a spinlock
held. A suggested maximum pause of 1 ms limits requested sleep, not scheduler
latency.

Distinguish operation cancellation from cleanup permission. An already-revoked
operation token must prevent another boot attempt, but cannot make every cleanup
lock acquisition fail immediately. Cleanup needs an explicit retained scope,
its own remaining absolute budget, and a statusful partial-state result. Expiry
retains resources; it does not authorize acknowledgement, destruction or a
fabricated successful unload. Neither scope extends the externally imposed PM
deadline. If the budget is exhausted, software retention still does not prove
that hardware power remains available.

Bind the record on the stable owner thread and on every admitted RM work, timer
and bottom-half callback. Callouts retain their binding through return. An
owner-thread-only record is insufficient. Scope absence preserves existing
contracts; it is not evidence that an unbound callback is safe during this
experiment.

## API lock: conditional attempts inside the statusful RM boundary

Target `src/nvidia/src/kernel/rmapi/rmapi.c`, `rmapiLockAcquire` at line 551.
The existing conditional path at lines 595-613 already uses these exact APIs:

- `portSyncRwLockAcquireReadConditional(g_RmApiLock.pLock)`;
- `portSyncRwLockAcquireWriteConditional(g_RmApiLock.pLock)`;
- matching `portSyncRwLockReleaseRead` / `portSyncRwLockReleaseWrite`.

For an in-scope ordinary nonconditional acquisition, retain the existing request
validation and effective read/write selection, then repeat conditional attempts.
On contention, check cancellation/deadline and pause outside the lock. Preserve
an explicitly conditional caller's single-attempt behavior. Retry only contention;
propagate invalid context, invalid lock order, invalid handle and other errors.

Only a successful conditional acquisition may publish `threadId`, timestamp,
trace, TLS lock-hold metadata or ownership. If revocation wins immediately after
token acquisition, release the actual token in the matching mode before returning
the cancellation status. Do not call the normal metadata-dependent release path
before its metadata has been established. On failure leave no token, no ownership
and no TLS lease. Balance `contentionCount` on all normal writer exits. Either
preserve low-priority aging with bounded conditional retries or explicitly reject
that unsupported mode before any mutation; do not silently change its semantics.

The existing `threadStateResetTimeout(NULL)` at line 679 must not reset the device
cancellation deadline. Nested original RM APIs reached during initialization also
need this path; limiting it to the outer INIT module misses nested acquisitions.

Do not change `os_acquire_rwlock_*`, `os_acquire_mutex` or
`os_acquire_semaphore` to return early. The Unix nvport implementations in
`src/nvidia/src/libraries/nvport/sync/sync_unix_kernel_os.c` expose ordinary
acquisitions as `void` and only assert their OS status. Returning without a token
would fabricate ownership in callers.

## GPU locks: preflight without changing interrupt semantics

Target `src/nvidia/src/kernel/core/locks.c`, `_rmGpuLocksAcquire` at line 641.
Its normal semaphore wait at line 951 follows a count decrement and precedes
publication of GPU ownership. It cannot be cancelled by returning early from the
semaphore callback.

Do not simply OR `GPU_LOCK_FLAGS_COND_ACQUIRE` into an ordinary request. Besides
changing lock-order validation, `_gpuLocksAcquireDisableInterrupts` derives its
`isIsr` behavior from that flag at line 579. A retry mechanism must preserve the
original ordinary-thread interrupt masking behavior.

The concrete candidate is a normal-acquire availability preflight:

1. Keep the original mask construction, GPU alloc-lock inclusion, safe-upgrade
   handling and normal lock-order/recursive-acquire checks. Keep original flags.
2. After those checks, before the first count decrement, inspect **every** lock
   to be acquired while holding `rmGpuLockInfo.pLock`. Include the alloc lock for
   `GPUS_LOCK_ALL` and explicit `GPU_LOCK_FLAGS_LOCK_ALLOC`. Require both
   `!bRunning` and `count > 0`; the latter prevents reaching the normal semaphore
   slow path when previously queued waiters still exist.
3. If any required lock is unavailable, change no lock count, owner, acquired
   mask or semaphore token. Release the state spinlock, balance priority boost,
   check/pause, and restart mask construction and validation from current state.
   Never retain a GPU pointer, group mask or lockable-mask observation across
   that pause without its existing lifetime protection.
4. If all required locks are available, run the original commit sequence under
   the same state spinlock, with original flags. No other thread can consume one
   of those counts between preflight and decrement. All ordinary semaphore and
   middle-path waits must be unreachable for that attempt.
5. Once any lock has committed, complete the original transaction or use its
   existing partial-acquisition rollback. Do not insert a cancellation return
   between count mutation and ownership bookkeeping. Observe cancellation again
   at the next statusful boundary after ownership is coherent.

Reusing `_rmGpuLocksAcquire` covers the existing callers
`rmGpuLocksAcquire`, `rmGpuGroupLockAcquire`, `rmDeviceGpuLocksAcquire`,
`rmGpuLockAlloc` and `rmGpuLockFree`; each caller's status propagation still needs
review. Preserve `NV_WARN_NOTHING_TO_DO`, safe-upgrade semantics, acquired-mask
output and resource-server lock metadata. Existing explicit conditional and
elevated-context paths remain single-attempt paths.

This avoids cancelling an enqueued semaphore waiter and therefore avoids inventing
token/count rollback for a racing wakeup. It can starve under contention, but
returns cancellation/deadline failure instead of waiting indefinitely. Lock
destruction's separate `_rmGpuLockDestroy` wait at line 337 still requires a
statusful retirement design; successful acquisition alone does not close it.

## Callout drain: close admission, return status, retain callback storage

Add statusful terminal-drain operations. Do not weaken the existing original
`void` timer cancellation callbacks: their callers may free event data as soon as
the callback returns. A bounded refusal through that interface does not establish
that freeing such data is safe.

| Object | Terminal drain candidate | Success condition |
|---|---|---|
| Work queue | Atomically close admission; snapshot accepted work; let the actual worker execute/free every accepted item; wait with deadline and preserve counters on refusal. | Accepted work completed, no queued data, no executor reference and framework call inactive. |
| Timer | Latch stop-requested, clear armed state and prevent rearm; use nonwaiting cancellation for pending dispatch; poll the actual callback/framework lifetime with deadline. Retries preserve the stop request. | No active callback, no future dispatch and no framework reference that can use callback storage. |
| IRQ bottom half | Close controller admission and unregister; retain original pending-work obligations; bound each real original bottom-half invocation as well as the framework wait. | Hard ISR and bottom half returned, pending RM obligations resolved and call storage safely released. |

Use a separate short-lived drain-operation guard if needed; a persistent
stop-requested latch must not make retry impossible. Never increment completed
counters, consume work data or clear callback ownership merely to satisfy a
deadline. Do not cancel a pending work executor while it still owns accepted
items requiring original cleanup. Do not destroy on `NV_ERR_IN_USE` or timeout.

Current unbounded operations are work flush / `thread_call_cancel_wait` in
`S540NvidiaDarwinWork.cpp:130,161` and timer cancellation in
`S540NvidiaDarwinTimer.cpp:123,126`. A candidate can use
`thread_call_cancel`, `thread_call_isactive` and actual `thread_call_free` success
for terminal retirement, with admission closed and callback-owned data retained.
Their exact combined framework lifetime contract must be checked against the
pinned XNU implementation before implementation; a logical callback counter
reaching zero does not alone prove the thread-call wrapper has returned.

The current IRQ drain has finite poll counts, but
`S540NvidiaDarwinDevice.cpp:607` invokes residual original bottom-half work
synchronously. That invocation remains part of the deadline budget.

## First experiment: evidence required and exclusions

The no-external-client restriction removes one producer class only. Before an
original TU117 initialization attempt is admitted, demonstrate all of these:

- Statusful init/disable/shutdown preserve partial original state on every
  cancellation path, including failed lock reacquisition after relaxed GSP boot.
- Every admitted callback is bound to the retained cancellation domain; work and
  timer producers have a verified closure order. Closing a queue must not discard
  a cleanup action that original unwind still requires.
- Actual original API/GPU lock tests contend from another thread, cancel before
  acquisition and race cancellation with token availability. After failure,
  prove no owner, count, waiter token, TLS lease or interrupt-mask change leaked;
  a subsequent real owner must acquire/release normally.
- Cover alloc-plus-GPU acquisition, lockable-mask change, recursive/order errors,
  safe upgrade and real success. Prove a failed multi-lock attempt changed no
  count; do not replace the production algorithm with a model fixture.
- Deadline refusal during a running work/timer callback retains every implicated
  object. A later retry drains and frees exactly once. Test a callback that needs
  the API/GPU lock concurrently with cleanup rather than assuming no contention.

Poll cancellation alone cannot satisfy this admission. Remaining nonpolling
waits, spinlock critical sections, GSP log-lock loops, original callback bodies,
hardware reset/DMA quiescence and IOKit services all require coverage. A separate
partial-cleanup review is necessary even if every acquisition test passes.

The design bounds cooperative waiting decisions against an absolute clock. It
does not prove kernel scheduler latency, MMIO completion time or a physical
30-second power guarantee. Keep the power gate closed until aggregate timing and
hardware-safe unwind have evidence; retention after refusal protects software
lifetime, not continued device power.
