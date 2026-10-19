# Read-only admission ledger

Pinned original NVIDIA source:
`1a82fbfda8f321b056eb3568850f9316c5e465c5`.
Paths below are relative to that snapshot. Line numbers refer to unmodified
source. This ledger accompanies isolated candidates and makes no readiness claim.

| Boundary | Actual source behavior | Requirement before original admission |
|---|---|---|
| Independent accepted work | `osapi.c:3615` calls `RmExecuteWorkItem` on a Darwin queue thread; Context `deviceWork/globalWork` have no cancellation scope. `RmExecuteWorkItem:764` acquires locks before its unload-drop test at `:783`. | An accepted item must carry a real master generation and immutable birth phase, with authorized entry on its actual thread and original `done` disposal exactly once. Generic foreign threads must remain unenrolled. |
| Timer producers | `RmRunNanoTimerCallback`, `osapi.c:3554`, enqueues work with GPU-group locking and `bDontFreeParams`. Existing Context stops timers during `ReleaseOriginalState`, after adapter shutdown. | Close rearm/admission and synchronously cancel timer producers before terminal accepted-work drains; retain original event payloads until accepted items finish. Verify the resulting order against checked original disable/shutdown needs. A one-shot timer control is insufficient for recurring arm generations. |
| Optional diagnostics | `kernel_gsp.c:2062` enters logs during event drain; `:6043` spins on `logDumpLock`; `liblogdecode.c:1442/1625` decodes/merges. | The separate log candidate stops optional work after actual revocation and preserves token/cursor ownership. Endpoint and scheduler latency remain outside the CPU evidence; no aggregate deadline is proven. |
| Stop-marker invalidation | `bGspRmUnloaded` is cleared after successful init RPC at `kernel_gsp.c:5344`, or resume-ready at `:7156`. `_kgspBootGspRm:5483` starts each boot attempt earlier. | Invalidate a prior completion before any new hardware start. For selected TU117, the reviewed local boundary is entry to `kgspBootstrap_TU102`, before Scrubber/FWSEC/reset/Booter, covering each normal/retry/resume/GC6 call. Clearing the marker must never be interpreted as proof of running or of stopped hardware. |
| Hardware DMA lifetime | IRQ drain and logical RM free do not stop GSP DMA. Current Context receipt validator is deliberately unsupported. | Begin an exact Session hardware epoch before original entry; accept only a sealed checked-original stop receipt bound to state, Session and generation. Every new hardware-start attempt invalidates prior completion. IRQ stop alone must never clear the hold. |
| Checked failure unwind | `kgspInitRm` can fail before the GPU_STATE flag exists; several original teardown errors were assert-only. | Compose and review the separate statusful adapter/GSP/Falcon candidates, preserve errors and retained ownership, and test each partial-start failure. `!GPU_STATE` and Boolean init failure do not attest a clean device. |
| Overall PM budget | DEVICE_INIT ThreadState permits at least 60s; framework PM acknowledgement expires around the returned 30s, then can proceed without the driver's explicit acknowledgement. | Cancellation must reach all selected blocking paths and complete actual hardware stop plus producer/work/IRQ/DMA drains inside the real event budget. Retaining memory or increasing the requested timeout is not that proof. |

`osapi.c` means `src/nvidia/arch/nvalloc/unix/src/osapi.c`;
`kernel_gsp.c` means `src/nvidia/src/kernel/gpu/gsp/kernel_gsp.c`;
`kernel_gsp_tu102.c` means
`src/nvidia/src/kernel/gpu/gsp/arch/turing/kernel_gsp_tu102.c`;
`liblogdecode.c` means
`src/common/uproc/os/libos-v3.1.0/lib/liblogdecode.c`.

All runtime gate bits remain set. The single Lenovo initialization trial has
not been attempted by these controls.
