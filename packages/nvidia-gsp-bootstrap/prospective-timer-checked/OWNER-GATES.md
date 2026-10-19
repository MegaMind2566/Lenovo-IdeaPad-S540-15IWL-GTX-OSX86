# Timer event and owner retirement gates

All references below are to NVIDIA commit
`1a82fbfda8f321b056eb3568850f9316c5e465c5`, rooted at
`upstream-source/open-gpu-kernel-modules-1a82fbfda8f321b056eb3568850f9316c5e465c5`.
These are source contracts, not claims that each path executes during the selected
TU117 first transaction. Feature/entry reachability must justify exclusions.

## Accepted work is a separate borrower

In `src/nvidia/arch/nvalloc/unix/src/osapi.c`,
`RmRunNanoTimerCallback` passes the original event pointer directly to
`osQueueWorkItem`. Its flags include `bDontFreeParams = NV_TRUE` and
`bLockGpuGroupDevice = NV_TRUE`. The function returns when queue submission
completes. `_tmrEventServiceTimerWorkItem` subsequently dereferences that same
pointer through `tmrEventServiceTimer`. Therefore a Darwin timer cancellation
receipt and a returned direct timer callback do not prove the event is unborrowed.

The existing `nano_callback` in `S540NvidiaGspTimersOriginal.c` calls
`rm_run_nano_timer_callback` and returns; it does not hold an event reference until
the accepted RM work item completes. Clearing the OS queued flag is not a queue
completion receipt. A global unavailable/rejected-call ledger records failure,
but a check only after original destruction cannot undo an earlier use-after-free.

A future real integration must associate an exact event and timer generation with
queue acceptance and completion. Before submission becomes visible, obtain the
event's borrower reference. Release it only on submission failure or on completion
of every accepted work path, including work rejected/skipped by its executor. A
retirement seal must stop new accepted borrows. After stopping the timer producer
and draining all accepted references, destruction may inspect the same sealed
generation and zero borrowers before releasing event storage and callback owners.
Reopening for a later schedule needs a new generation; stale completion cannot
authorize a new event at a reused address. Neither a caller-supplied Boolean nor
the timer backend's `NV_OK` can stand in for this receipt.

The proposed name `s540GspTimersSealEventBorrowers` is a design description only;
no fixture implementation is offered as real integration in this candidate.

## Lock and bounded-wait requirement

`subdeviceCtrlCmdTimerCancel_IMPL` in
`src/nvidia/src/kernel/gpu/subdevice/subdevice_ctrl_timer_kernel.c` asserts both
API-lock and GPU-lock ownership. Accepted timer work requests the GPU group lock.
A borrower-drain wait inside this locked caller could wait for work that needs
the lock held by the waiter. The ordinary owner must seal producers and drain
accepted work before entering destructive RM code or acquiring those locks; an
under-lock event check must return a refusal if borrowing remains. The fixed
original revocation deadline applies to that real drain. Failure retains every
backing owner and prevents later original destruction.

## Owner destruction sites requiring checked propagation or prior exclusion

| Source and caller | Current ownership loss / continuation | Required guard before a destructive phase |
| --- | --- | --- |
| `gpu/timer/timer.c`: `tmrCtrlCmdEventDestroy` | Original frees API `pUserData` before void destroy. | This candidate returns exact failure and retains both allocations. Borrower seal is still required before a successful real release. |
| `gpu/timer/timer.c`: `tmrapiDeregisterEvents_IMPL` | Original clears notification GPU/event pointers after void destroy. | This candidate retains them and stops on failure; its outer void path still needs a checked pre-destructive guard. |
| `os/os_timer.c`: `osDestroy1HzCallbacks` | Clears `pOs1HzEvent`, callback list and free list, then returns `NV_OK` regardless of void destroy. | Propagate a statusful event operation before clearing any pointers; guard its owner before destructor invocation. |
| `gpu/timer/timer.c`: `tmrDestruct_IMPL` | Destroys timer spinlock/refcount owner before calling `osDestroy1HzCallbacks`. | Perform the real timer/accepted-work retirement and sticky-refusal check before this destructor starts, not after its last call. |
| `gpu/timer/timer.c`: `tmrStateDestroy_IMPL` | Unconditionally deletes timer refcount owner through a void API. | Earlier unload/adapter checked boundary must refuse all later state destruction if timer/borrower retirement failed. |
| `gpu/subdevice/subdevice.c`: `subdeviceDestruct_IMPL` | Clears `pTimerEvent`/notification action and continues object teardown after void destroy. | Checked destruction admission before this generic destructor; a return inside a void destructor alone cannot stop generic object freeing. |
| `rmapi/event_notification.c`: `_removeEventNotification` | Unlinks the notification first, then clears its GPU/event pointers after void destroy. | Validate/retire before unlinking and propagate exact refusal; preserve the callback owner and list links on failure. |
| `gpu/subdevice/subdevice_ctrl_timer_kernel.c`: `subdeviceCtrlCmdTimerCancel_IMPL`, schedule path | Marks notification disabled or proceeds to reschedule after void cancel. | Statusful operation before action mutation/reschedule; no blocking borrower wait while API/GPU locks are held. |
| `gpu/timed_semaphore.c`: `tsemaDestruct_IMPL`, flush control | Destructor clears event and destroys callback's entry list; flush invokes callback immediately after void cancel. | Refuse before the object/list destructor or duplicate callback; prove selected feature path exclusion if not reachable. |
| `gpu/fsp/kern_fsp.c`: `kfspCleanupBootState_IMPL` | Clears polling event then frees payload/other state. | Retire callback/event and accepted references before any dependent owner free, or prove selected TU117 exclusion. |
| `gpu/gr/fecs_event_list.c`: timer event destroy path | Clears FECS timer pointer after void destroy. | Guard trace-state owner and preserve pointer on failure, or prove selected feature exclusion. |
| `diagnostics/gpu_acct.c`: timer event destroy path | Clears event while cleaning accounting state. | Guard accounting owner before free; source has GSP-client branch exclusion, which needs selected-path proof. |
| `gpu/gpuvideo/videoeventlist.c`: timer event destroy path | Clears video timer pointer during cleanup. | Guard video callback state before free, or prove selected feature exclusion. |
| External-device, confidential-compute, SPDM and NVLink timer callers | Additional void calls can drop pointers, mutate callback state or continue destruction. | `all-callers.json` records the complete direct-call inventory; selected-profile reachability/exclusion is not inferred here. |

Paths in this table are relative to `src/nvidia/src/kernel` except the explicitly
named `osapi.c`. The first checks to compose around a first adapter transaction
are timer owner/destructor and `osDestroy1HzCallbacks`, then the actual selected
resource-owner destruction paths reachable from checked `RmShutdownAdapter`.
Client-only and other-architecture paths may be excluded only with actual source
and profile evidence. Preserving just the event allocation while its `pUserData`
owner or lock is freed is not a valid quarantine.

The current source-order candidate, checked backend exports, fixed deadline and
sticky ledger are necessary pieces. They do not close this owner/borrower gate by
themselves; all admission fields remain false.
