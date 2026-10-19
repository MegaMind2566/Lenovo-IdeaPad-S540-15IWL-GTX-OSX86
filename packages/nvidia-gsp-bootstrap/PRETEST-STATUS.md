# Single Lenovo test: prerequisite status

The next hardware milestone is one controlled original RM/GSP initialization
attempt on the S540 TU117. **No installable candidate is ready.** The confirmed
Lenovo checkpoint remains v9. Brightness, external displays and electrical
NVIDIA power-off work remain deferred.

## Exact completed native checkpoint

Intel macOS Actions run
[39218234557](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/actions/runs/39218234557)
passed completely at source `a60109e4cf48b7614514f8565fae2d2325bfc359`.
The downloaded artifact digest is verified. Its results cover:

- 2,398 component controls in each ordinary/sanitized variant.
- 429 first-transaction/Host/queue/timer controls in each variant.
- All 156 original global allocation-failure cases in each variant.
- Full original-source compilation, kernel bridge/link controls, firmware
  validation, disabled UVM, unavailable OS-event policy and the measured typed
  NVOC dispatch.

[NATIVE-FIRST-TRANSACTION-VALIDATION.json](../nvidia-global-rm/NATIVE-FIRST-TRANSACTION-VALIDATION.json)
binds these claims to exact source and artifact hashes. This run does not cover
subsequent edits. Earlier native records remain historical evidence.

## Subsequent combined source work

The new complete-image composer combines the frozen V3/first-transaction source
with exact GPU-instance binding and API/GPU/allocation-lock observations. All
1,100 original units compile locally against the composed source/headers; all
53 project units compile with real cancellation participants. These results
are explicit Linux Mach-O cross-compilation, not a new Apple/kernel execution.

The fixed retained-diagnostic, RC-participant, shutdown-protocol and seven-callback
platform source options compose together. All 56 resulting project units and
the changed original `osapi.c` compile locally. The final complete native source profile
still needs its own 1,100-unit rebuild and actual same-image link.

The retained Host policy pins associated physical backing from transaction
start, with separate logical-retirement counters and no invented error. Its
29 controls per variant include actual queue/direct-timer authorization,
concurrent duplicate frees and a genuine earlier service refusal. It issues no
hardware-stop or final-release receipt. Direct Darwin timer/workqueue/guard
allocations need their own retained lifetime; Host pinning does not cover them.

The typed one-shot shutdown bridge calls the exact original
`gpuEnterShutdown_IMPL`: state unload plus normal GSP shutdown, without
`gpuStateDestroy`. Its 191 controls per variant and two complete TU compilations
are software evidence with declared hardware/token fixtures. It is not the
current production teardown path and does not attest universal DMA cessation.

## Remaining integrated admission

| Requirement | Remaining work |
|---|---|
| Complete final image | Native full-profile compile, actual dead-stripped kext link, exact original/private closure, three metaclasses, firmware and retained typed roots in the same image. Full-input unresolved symbols are not automatically live selected-root requirements. |
| Original locks/lifetime | Connect the actual lock observer to a serialized global/context epoch with ISR/DPC exclusion. A zero current-thread lock mask is not all-thread quiescence. |
| Callback producers | Compose genuine RC behavior and hard-IRQ/coalesced-BH participation, including master-thread pending drains and a non-destructive persistent hardware-mask phase. Do not invent EVENT/OWNER policy rows for plain 1Hz callbacks. |
| Allocation ownership | Acquire the real session hardware-DMA hold before any original attempt. Preserve CPU objects, direct service backends, DMA backing/mappings, context and module text after the retained diagnostic. |
| Kernel stack | Measured frames and direct edges are available. Recursive components, indirect calls, external depth and complete wrapper/IRQ headroom still prevent an aggregate bound. Unknown paths are not zero. |
| PM/cancellation | Establish actual cleanup/producer ordering within the PM deadline. A software drain or PMstop is not a hardware-stop receipt. |
| Operational entry | The production KERNEL global entry and bootstrap initializer still refuse. A complete retained transaction and actual target-loader success must precede original GPU entry; loading the idle image alone is not an RM/GSP initialization test. |

The supplied target report identifies macOS 26.7.1/build25G241, Darwin25.6.0.
Public SDK compilation does not demonstrate exact target export/vtable loading.
Hardware results are observations for the eventual Lenovo test; software checks
do not establish GSP firmware execution or graphics acceleration.
