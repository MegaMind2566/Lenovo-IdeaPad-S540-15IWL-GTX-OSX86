# Original-entry power deadline admission

The real completed PM-child lease permits resource preparation. It does not
establish that original RM initialization can stop before macOS revokes power.
`Owner::initialize()` remains a refusal before original code and every snapshot
keeps `PowerLifetime` blocked, including snapshots with `powerDomainJoined` and
`powerOnCompleted` true. This is a normal sleep admission issue as well as an
emergency-power limitation.

This audit uses NVIDIA commit
`1a82fbfda8f321b056eb3568850f9316c5e465c5` and XNU commit
`f6217f891ac0bb64f3d375211650a4c1ff8ca1ea`. The companion
[provenance manifest](POWER-PROVENANCE.json) pins their paths and Apple blobs.
These source observations do not measure execution on the laptop.

## Original wait budgets

The following are configured per-wait deadlines, not hard upper bounds for an
entire initialization or teardown. Scheduling, lock acquisition, callbacks and
event draining also need bounds. Values below assume real silicon and no
timeout registry override; simulation and emulation are outside this profile.

| Wait | Pinned source behavior | Consequence |
|---|---|---|
| Turing GFW boot | [`gpuWaitForGfwBootComplete_TU102`][gfw] passes 50,000 + 2,000,000 microseconds, scaled by `gpuScaleTimeout`, to Falcon halt | Nominal silicon deadline is 2.05 seconds |
| FWSEC and Booter load/unload | [`kgspExecuteHsFalcon_TU102`][falcon] calls `kflcnWaitForHalt` with `GPU_TIMEOUT_DEFAULT`; [`timeoutSet`][timeouts] selects ThreadState for that default | During original initialization this wait can consume a 60-second ThreadState deadline |
| Original initialization ThreadState | [`rm_init_adapter`][entry] sets `THREAD_STATE_FLAGS_DEVICE_INIT`; [`_threadNodeInitTime`][threadstate] applies `max(configured, 60,000 ms)` | It is at least 60 seconds, not a 30-second whole-entry limit |
| GSP status queue link | [`GspStatusQueueInit`][queue] configures 4,000,000 microseconds on silicon, also subject to ThreadState | Nominal local deadline is 4 seconds |
| Synchronous GSP RPC and processor-suspend condition | [`kgspRecvPoll_IMPL`][poll] uses `defaultus + defaultus / 2` and explicitly bypasses ThreadState; [`osGetTimeoutParams`][os] supplies 4-second graphics or 30-second compute defaults | Nominal deadline is 6 seconds in graphics mode or 45 seconds in compute mode; a ThreadState override cannot shorten this bypass |
| GSP boot retry | [`kgspInitRm_IMPL`][boot] resets ThreadState before GFW boot and after failed attempts; [`RmGspBootRetryAttempts`][registry] defaults to four attempts | Per-attempt resets prevent treating the first ThreadState deadline as the whole-entry bound |
| Disable/unload | [`RmDisableAdapter`][disable] unloads GPU state; [`kgspUnloadRm_IMPL`][unload] waits for processor suspend and invokes teardown; Turing teardown resets ThreadState before FWSEC/Booter work | Shutdown itself needs a separate budget after interrupted initialization |

The configured 60-second deadline is sufficient to disprove admission under
the current 30-second PM response. There is no demonstrated finite aggregate
wall-clock bound for `rm_init_adapter` plus its failure unwind and complete
interrupt/DMA/MMIO shutdown. Multiplying the retry count by one wait deadline
would not establish that bound. In particular, `kgspRecvPoll` checks its timer
outside `_kgspRpcDrainEvents`; that inner event-drain loop has no explicit
iteration/time budget. The configured RPC deadline therefore does not itself
bound a continuously replenished event drain.

## Apple acknowledgement and sleep behavior

[`IOService::setPowerState`][service] documents a positive return value as the
upper limit, in microseconds, needed to complete the power transition. The
lease currently returns 30,000,000. In
[`notifyControllingDriverDone`][ack], XNU enforces a ten-second minimum and
converts the positive result into acknowledgement-timer ticks. This path has
no 30-second maximum clamp. The distinct `kMaxTimeRequested` value belongs to
client sleep notifications, not this controlling-driver return path. Merely
returning a longer value would still require proof that all work fits it.

When the driver's timer expires, [`ackTimerTick`][expire] records a tardy driver
and advances the state machine as if it acknowledged. Some builds or debug
policies panic instead. Retaining memory and withholding a false
`acknowledgeSetPowerState` preserve ownership evidence, but do not force the
parent to keep the device powered after this deadline.

On macOS, [`updatePreventIdleSleepListInternal`][idle] ignores an ordinary
driver's `kIOPMPreventIdleSleep` power-state capability. Only the display
wrangler and no-idle-sleep assertions participate in that path. Driver desire
also does not prevent demand sleep. The public
`kIOPMDriverAssertionPreventSystemIdleSleepBit` explicitly excludes demand
sleep; an idle-only assertion would therefore not close this deadline issue.
The current lease does not create such an assertion or claim one was applied.

The independent external-hook count remains necessary for callback-owner
storage: [`waitForPMDriverCall`][pmstop] has a 15-second timeout. That count
prevents freeing an outer owner still used by a revocation hook; it does not
cancel original RM execution or extend physical power availability.

## Required evidence before original entry

The PM callback now publishes an exact-state atomic revocation record before
enqueuing `PowerRevoked` on the same persistent worker that would execute
`rm_init_adapter` and disable/unload. The current checked original profile does
not yet consume that record. The dispatcher drains
accepted commands in order; it cannot execute stop while an earlier original
call is still running. OS scheduling/yielding inside RM does not dispatch a
pending owner command. Killing or reentering that worker is not a cancellation
strategy.

The reviewed checked original waits provide no common PM cancellation contract.
`kgspRecvPoll` can leave after an RPC/condition, timeout, or a real GPU-state
failure; its condition callback is not supplied for the normal synchronous
initialization RPC. `osIsGpuShutdown` reads the real `nv_state_t::is_shutdown`
notification, but that check does not cover Falcon halt or every bootstrap
wait. Inventing a reset/lost/shutdown state would not prove a safe unwind.
`threadStateSetTimeoutOverride` changes a current ThreadState deadline; it does
not cover RPCs that bypass ThreadState, later deadline resets, or foreign-thread
synchronization.

Admission requires an independently recorded revocation that relevant original
waits can observe without acquiring their own RM locks, with a reviewed error
return through the original unwind. The evidence must cover Falcon/FWSEC/Booter
polls, RPC/event/queue loops, retry suppression, blocking locks and work drains.
It must then show a worst-case time from revocation through original unwind,
disable/unload, IRQ quiescence and real DMA/MMIO retirement, with margin before
the actual PM deadline. Fault tests must revoke during those original waits and
prove complete cleanup before acknowledgement. No such integrated cancellation
and shutdown bound is established by the current source profile.

The [isolated cancellation candidate](../cancellation/README.md) adds checks to
actual original wait bodies and suppresses explicit-abort boot retry. Its CPU
fault controls revoke during those bodies; they do not establish hardware
cleanup or close this gate. The candidate is separate from the frozen checked
source profile while statusful unwind and drain contracts are reviewed.

[gfw]: https://github.com/NVIDIA/open-gpu-kernel-modules/blob/1a82fbfda8f321b056eb3568850f9316c5e465c5/src/nvidia/src/kernel/gpu/arch/turing/kern_gpu_tu102.c#L454
[falcon]: https://github.com/NVIDIA/open-gpu-kernel-modules/blob/1a82fbfda8f321b056eb3568850f9316c5e465c5/src/nvidia/src/kernel/gpu/gsp/arch/turing/kernel_gsp_falcon_tu102.c#L382
[timeouts]: https://github.com/NVIDIA/open-gpu-kernel-modules/blob/1a82fbfda8f321b056eb3568850f9316c5e465c5/src/nvidia/src/kernel/gpu/gpu_timeout.c#L245
[entry]: https://github.com/NVIDIA/open-gpu-kernel-modules/blob/1a82fbfda8f321b056eb3568850f9316c5e465c5/src/nvidia/arch/nvalloc/unix/src/osapi.c#L1826
[threadstate]: https://github.com/NVIDIA/open-gpu-kernel-modules/blob/1a82fbfda8f321b056eb3568850f9316c5e465c5/src/nvidia/src/kernel/core/thread_state.c#L330
[queue]: https://github.com/NVIDIA/open-gpu-kernel-modules/blob/1a82fbfda8f321b056eb3568850f9316c5e465c5/src/nvidia/src/kernel/gpu/gsp/message_queue_cpu.c#L342
[poll]: https://github.com/NVIDIA/open-gpu-kernel-modules/blob/1a82fbfda8f321b056eb3568850f9316c5e465c5/src/nvidia/src/kernel/gpu/gsp/kernel_gsp.c#L3271
[os]: https://github.com/NVIDIA/open-gpu-kernel-modules/blob/1a82fbfda8f321b056eb3568850f9316c5e465c5/src/nvidia/arch/nvalloc/unix/src/os.c#L2264
[boot]: https://github.com/NVIDIA/open-gpu-kernel-modules/blob/1a82fbfda8f321b056eb3568850f9316c5e465c5/src/nvidia/src/kernel/gpu/gsp/kernel_gsp.c#L5673
[registry]: https://github.com/NVIDIA/open-gpu-kernel-modules/blob/1a82fbfda8f321b056eb3568850f9316c5e465c5/src/nvidia/interface/nvrm_registry.h#L2853
[disable]: https://github.com/NVIDIA/open-gpu-kernel-modules/blob/1a82fbfda8f321b056eb3568850f9316c5e465c5/src/nvidia/arch/nvalloc/unix/src/osinit.c#L2541
[unload]: https://github.com/NVIDIA/open-gpu-kernel-modules/blob/1a82fbfda8f321b056eb3568850f9316c5e465c5/src/nvidia/src/kernel/gpu/gsp/kernel_gsp.c#L5848
[service]: https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/iokit/IOKit/IOService.h#L2107
[ack]: https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/iokit/Kernel/IOServicePM.cpp#L4576
[expire]: https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/iokit/Kernel/IOServicePM.cpp#L5581
[idle]: https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/iokit/Kernel/IOPMrootDomain.cpp#L3401
[pmstop]: https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/iokit/Kernel/IOServicePM.cpp#L8752
