# Typed original IRQ mask and pending 1Hz drain

`S540NvidiaIrqOriginal.c` is an additional original-ABI translation unit for
the explicit IRQ/callback composition. It requires
`S540_NVIDIA_IRQ_CALLBACK_CLOSURE=1`, the complete selected original profile,
the exact composed namespace and the strong global-epoch record header.
The selected basic lock model also requires the already-reviewed
`S540_NVIDIA_NO_LEGACY_RM_SEMAPHORE=1` profile.

Both helpers authenticate the exact ordinary master through
`s540FirstTxnGlobalReadMaster`, match its live `nv`, require the READY global
epoch, and inspect complete original current-thread lock ownership. They refuse
incoming API/GPU/allocation tokens, acquire real original API and device-GPU
locks, and recheck the immutable epoch and actual device ownership. Direct
original calls have a real original runtime/thread-state scope. All acquired
locks are released on every return path.

The mask first sets the original interrupt object's persistent `intrEn0`
selection to `INTERRUPT_TYPE_DISABLED`, then calls the unchanged original
`osDisableInterrupts`. The original GPU-unlock path may invoke
`osEnableInterrupts`; it reads the persisted disabled selection. A frozen HAL
is refused because `intrSetIntrEn` would decline to change its stored value
while `intrGetIntrEn` would still report disabled. The unsupported Tegra route
and a missing interrupt object are also refused. There is no raw register
write, destructive adapter disable, GSP/DMA stop receipt or release receipt.

The drain calls the unchanged `osRunQueued1HzCallbacksUnderLock` under the same
master, API and device-GPU ownership. This is the ordinary 1Hz callback list,
also serviced by original `_gpuLocksReleaseHandleDeferredWork`. Its entries
can carry NULL or ordinary allocation data. No `TMR_EVENT`, NVOC object or
EVENT/OWNER descriptor is invented. The exact selected Linux original profile
implements legacy RM-semaphore functions as no-ops. The complete ownership
reader instead checks the selected basic lock model and `SYS.pSema == NULL`;
the generated literal `osIsRmSemaOwner` is not used as evidence.

The strong master reader permits OP with no sticky failure. These helpers
therefore run before `BeginClosing`. After sticky retention or closing they
refuse, preserving the Platform/IRQ/power owners. A separate strong cleanup
master authority would be required to admit masking in those states.

`check_actual_1hz.py --upstream PATH [--sanitize]` extracts and executes eleven
complete hash-pinned original functions: RC wrapper, ordinary 1Hz list and
pending drain, and the actual BIF existence callback. Its explicit small-layout,
POSIX-lock and hardware fixtures prove the source behavior, not layout ABI.
It covers conditional GPU/API contention, real `bCallbackQueued`, ordinary
master drain, interrupt and missing-lock refusal, plain/NULL data, one-shot
recycling and BIF self-removal. This does not establish the complete selected
profile's 1Hz callback reachability or transitive GPU behavior.

`check_irq_original.py --upstream PATH --composition PATH --cc PATH` compiles
the unmodified production helper with the complete original headers and exact
composed namespace for the Darwin kernel target. Its CPU controls execute that
same production helper plus the four complete original interrupt set/get and
disable/enable bodies in ordinary and fatal ASan/UBSan variants. Strong record,
lock and hardware HAL dependencies are explicit typed fixtures. They verify
persistent masking across the actual original re-enable body, master and epoch
revalidation, token ownership, pending-state refusal, and acquired-token unwind.
These local controls do not execute IOKit, the target kernel or the GPU.
