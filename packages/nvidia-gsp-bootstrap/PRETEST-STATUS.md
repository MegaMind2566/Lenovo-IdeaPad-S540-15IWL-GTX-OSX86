# Single Lenovo test: prerequisite status

The next target milestone is an idle complete-image loader ABI check on the
S540 TU117, before any original RM/GSP initialization. No new ZIP has yet passed
its complete native packaging run. The confirmed Lenovo checkpoint remains v9. Brightness, external displays and electrical
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

The subsequent fixed live-ABI profile composes 60 project units, retained
direct-service backends and the serialized global-epoch record. Its 60 project
units and five changed complete original units compile locally. A strict
exploratory Linux Mach-O bundle link of 1,163 actual objects has no unresolved
private callbacks; its 439 public imports are within the same 445 reviewed SDK
operations. This is not an Apple kext link or a target-loader success. Actual
OS-event guards and the nonprimary-only emulation profile are selected; the
native final verifier independently requires the character/event insertion
dispatcher to be absent.

The retained Host policy pins associated physical backing from transaction
start, with separate logical-retirement counters and no invented error. Its
29 controls per variant include actual queue/direct-timer authorization,
concurrent duplicate frees and a genuine earlier service refusal. It issues no
hardware-stop or final-release receipt. Direct Darwin timer/workqueue/guard
allocations have a separate retained-backends successor with 130 checks per
variant, including zero-heap HostShutdown and preowner allocation/free races.
It does not cover the direct transport Platform/IRQ backend lifetime.

Actual original global construction under BeginOwner passes ordinary and
fatal-sanitized CPU controls: all 15 globals and the resource-server client are
constructed, with 154 allocations and six logical temporary retirements, no
physical frees and no unknown NVOC deletion. A later global-epoch fault test
exposed a retained-mode OOM at allocation 154: original sysConstruct cleanup
tries to acquire a newly allocated TLS entry after sticky allocation refusal,
and an ignored resource-server cleanup failure loops. The retained construction
failure path is being corrected; healthy construction does not close this
failure case or permit kernel entry.

The typed one-shot shutdown bridge calls the exact original
`gpuEnterShutdown_IMPL`: state unload plus normal GSP shutdown, without
`gpuStateDestroy`. Its 191 controls per variant and two complete TU compilations
are software evidence with declared hardware/token fixtures. It is not the
current production teardown path and does not attest universal DMA cessation.

## Latest native result and idle test packaging

At source `49808c86f4d99dc2821c6887c0156841cd40564f`, native run
[39413559517](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/actions/runs/39413559517)
stopped when Darwin's fortified `memset` macro expanded the shutdown fixture's
function definition. Idle-package run
[39413559453](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/actions/runs/39413559453)
compiled all original inputs and the first 42 project units, then rejected the
live-platform unit's extra `__bzero` import. Inspection of that actual Apple
object confirms its seven expected exports and four private imports are intact;
the sole extra symbol is the compiler's public snapshot-zeroing helper.

The fixture now undefines only the fortified function-like macro before its
existing freestanding implementation. The live-platform symbol contracts now
permit only `__bzero` as an optional compiler memory helper and still reject
missing callbacks, unexpected private imports and changed exports. Actual helper
imports remain recorded and subject to the final SDK import audit. A new native
run is required to establish compilation, linking, signing and packaging; no
target execution or successful ZIP is inferred from these corrections.

The follow-up local validation passed all 13 composition-integrity tests,
191 shutdown checks in each ordinary/fatal-sanitized variant, a separate
191-check run with a simulated Darwin fortified function macro, 31 live-platform
checks per variant, 49 packager source controls and 18 actual loader-decoder
checks per variant. All 60 integrated project units also compile freshly to
Mach-O against the pinned SDK. The modified shutdown fixture's frozen inventory
is updated and checked in full. These are Linux CPU/cross-compilation controls;
the acquired firmware pair was not rechecked in this local follow-up, and no
native final link, signature or bundle was produced. The source-bound
[local validation record](prospective-complete-image-package/NATIVE-FIX-LOCAL-VALIDATION.json)
retains those distinctions.

Native idle-package run
[39432077042](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/actions/runs/39432077042)
at `91130ef72328f91f5d784de085b92444668c6521` failed before any job script
started, including its second attempt. Repository validation and the full native
development job also failed with no steps. Available API results expose no
startup reason and no job log; inspect the job annotations before attributing
this to billing, runner capacity or a code failure. The native package build
must run again at the latest source after the startup block is resolved.

Native Actions run
[39230673074](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/actions/runs/39230673074)
at source `0f73640865cb9c2d0dbaf351b4ac27305c5de3c8` passed the early source,
compiler, original-profile and first-transaction controls, then stopped in the
original lock-observer compilation script: it passed the `xcrun` launcher as
if it were a compiler executable. No target module was loaded. The script now
resolves the actual Xcode clang path, with its candidate source contract updated;
this correction passed in native run
[39408242488](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/actions/runs/39408242488)
at `d647e524ab6965b278af4858e0178853f4d02e1a`. That run then stopped at the GPU
checker namespace input. The GPU and mapping checks require the V3 additive
wrapper; the workflow supplied the baseline header. The old wrapper guard also
compared a historical raw hash containing a Linux absolute include path. The
corrective guard pins the independent baseline/alias contracts and reconstructs
every wrapper byte for the actual canonical baseline path. The three workflow
arguments are corrected, with new positive and refusal controls across separate
absolute paths. The next native run must validate those corrections and the
remaining complete image/package stages.

The separate idle packager requires the exact successful fresh native report,
its intact complete original/project objects, pinned SDK and firmware. It checks
the three metaclasses, imports, roots, loader pointers and firmware again, signs
the bundle/controller, and verifies the existing image bytes are unchanged apart
from permitted signature metadata. The target scripts issue only the idle
snapshot request and attempt normal unload after the load test. All original
RM/GSP entry gates stay closed. An idle-loader result does not establish GPU
initialization, firmware execution or acceleration.

Later IRQ, assertion and construction-retention successors remain separate
source work. They are not prerequisites for the idle-only package because no
original global or adapter entry executes during that test.

## Remaining integrated admission

| Requirement | Remaining work |
|---|---|
| Complete final image | Native full-profile compile, actual dead-stripped kext link, exact original/private closure, three metaclasses, firmware and retained typed roots in the same image. Full-input unresolved symbols are not automatically live selected-root requirements. |
| Original locks/lifetime | Validate the serialized global/context epoch and close the retained late-OOM construction failure before kernel entry, with ISR/DPC exclusion. A zero current-thread lock mask is not all-thread quiescence. |
| Callback producers | Compose genuine RC behavior and hard-IRQ/coalesced-BH participation, including master-thread pending drains and a non-destructive persistent hardware-mask phase. Do not invent EVENT/OWNER policy rows for plain 1Hz callbacks. |
| Allocation ownership | Acquire the real session hardware-DMA hold before any original attempt. Preserve CPU objects, direct service backends, DMA backing/mappings, context and module text after the retained diagnostic. |
| Kernel stack | Measured frames and direct edges are available. Recursive components, indirect calls, external depth and complete wrapper/IRQ headroom still prevent an aggregate bound. Unknown paths are not zero. |
| PM/cancellation | Establish actual cleanup/producer ordering within the PM deadline. A software drain or PMstop is not a hardware-stop receipt. |
| Operational entry | The production KERNEL global entry and bootstrap initializer still refuse. A complete retained transaction and actual target-loader success must precede original GPU entry; loading the idle image alone is not an RM/GSP initialization test. |

The supplied target report identifies macOS 26.7.1/build25G241, Darwin25.6.0.
Public SDK compilation does not demonstrate exact target export/vtable loading.
Hardware results are observations for the eventual Lenovo test; software checks
do not establish GSP firmware execution or graphics acceleration.
