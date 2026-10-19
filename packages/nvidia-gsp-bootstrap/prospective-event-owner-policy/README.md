# Original RC participant successor

This isolated successor replaces the first-transaction timer candidate's
deliberate RC refusal with real transaction participation. It changes no frozen
parent, production owner, source profile, kernel entry, admission mask or working
EFI. It does not issue a final hardware-stop or callback-text release receipt.

The immutable descriptor row names the actual `rm_run_rc_callback` address. Its
data is the exact already-bound `nv_state_t`, and its service identity is the
actual RC timer registered before entry. The record obtains an arm lease before
real timer publication; the real callback enters that lease before invoking the
original wrapper. Original-wrapper return and the later Darwin action return
remain distinct observations. Rearm obtains a new monotonic generation while
the old callback retains its own running generation. Synchronous cancellation
retires a pending arm only after the backend actually confirms cancellation.
Failures preserve sticky status and retained owners.

RC is not a nano timer event. No fake `TMR_EVENT`, caller-selected callback,
NVOC class, or EVENT/OWNER descriptor is introduced. A direct caller cannot
invent the timer service's guarded ADMIT/ENTER/RETURNED observations.

`prepare.py` exposes exact-anchor transforms for combined-image composition:

| Transform | Input | Output |
| --- | --- | --- |
| `record_overlay` | Frozen strong record, optionally with independent GPU-binding additions | RC lease admission and original-address revalidation |
| `header_overlay` | Strong-record public header | Distinct RC descriptor and typed entry/probe declarations |
| `timers_overlay` | Frozen first-transaction real timer overlay | Actual RC accept, entry, return, rearm and cancel boundaries |
| `original_policy_overlay` | Frozen first-transaction `osapi.c`, optionally with independent GPU-binding additions | One immutable row for actual `rm_run_rc_callback` |
| `RC_ORIGINAL` | Compiled with actual full NVIDIA headers/namespace | Typed original wrapper-address probe |

Generated files belong in an explicit fresh output directory. Repository
outputs are allowed only under `build/`. The frozen parent inventory, exact file
hashes and project dependencies are checked before parent helper import.

`check.py` executes the actual pinned original RC wrapper and original metadata
readers, the exact parent production descriptor table plus the RC row, the
strong record, retained Host allocator, cancellation registry, queues and native
Darwin timer backend. GPU lookup, hardware sanity, 1Hz action and original RM
lock observation are explicit fixtures. These are not substitutes for actual
GPU execution or the transitive 1Hz target policy.

The local Linux controls passed 22 checks in each plain and fatal
ASan/UBSan/function variant. They cover pending cancellation, actual callback
entry and return, real rearm with distinct generations, stop while RC is
running, no rearm during stop, refusal of a forged producer stage and an actual
Host allocation failure before the original wrapper is invoked. That failure
retains the participant without inventing original-return evidence. Four complete
project units also passed kernel-target Mach-O compilation with the pinned SDK;
this is cross-compilation evidence. Leak
inspection is disabled on this executor; final owner release is deliberately
unavailable and remains separately visible. Native Apple validation and
combined-kernel-image definition/relocation checks are still required.

Run with an already-materialized exact frozen companion Host overlay:

```sh
python3 packages/nvidia-gsp-bootstrap/prospective-event-owner-policy/check.py \
  --upstream "$UPSTREAM" --namespace "$NAMESPACE" --host-overlay "$HOST_OVERLAY" \
  --cc "$CLANG" --cxx "$CLANGXX" --output "$OUT/rc"
```

Non-Apple CPU controls require the explicit `--host-control` switch.
Optional `--sdk` and `--sdk-archive` arguments also check the exact SDK identity
and compile the record, typed RC port/probe and actual timer backend.

## Selected source findings

All upstream references below name NVIDIA commit
`1a82fbfda8f321b056eb3568850f9316c5e465c5`.

| Source route | Exact consequence |
| --- | --- |
| `osinit.c:2281`, `RmInitAdapter` | Calls `nv_start_rc_timer` unconditionally after interrupt verification; an RC backend is required by the unchanged full-root profile. |
| `generated/g_objtmr_nvoc.c:299–317` | PF_KERNEL_ONLY selects OS timers for real events. `USE_PTIMER_FOR_OSTIMER_CALLBACKS` is false, so `osInit1HzCallbacks` does not manufacture an OS-backed 1Hz event. |
| `os_timer.c:109–156` and `osRun1HzCallbacksNow` | Registers ordinary 1Hz entries in the timer object's list. RC runs that list under the original conditional GPU token; these entries are not `TMR_EVENT` owners. |
| `generated/g_kernel_bif_nvoc.c:246–250`; `kernel_bif.c:184–187` | TU117 enables the BIF existence check and registers `_kbifCheckIfGpuExists` with NULL data and `NV_OS_1HZ_REPEAT`. This is a concrete initial RC target. |
| `kernel_bif.c:1232–1245` | The existence callback checks actual GPU sanity/existence and can remove itself from the 1Hz list. It borrows the bound GPU rather than an invented event owner. |
| `nvrm_registry.h:3358–3361`; `kernel_gsp.c:4689–4692,5800` | Periodic GSP health checking is officially disabled by default. A selected source/profile must preserve and verify that setting before excluding `_kgspHealthPeriodicHealthCheck`. |
| `kernel_gsp.c:7167–7223` | `LIBOS_LOG_DECODE_ENABLE=0` selects the original no-resource log-polling branch. The selected profile already uses that build option. |
| `kernel_gsp.c:3272–3466` | Synchronous GSP RPCs poll command/sequence completion, including the INIT bootup context. This does not prove complete adapter operation without IRQ. |
| `osinit.c:2223`; `os_sanity.c:_osVerifyInterrupts` | The full adapter root deliberately generates and verifies an actual software interrupt. A no-IRQ package cannot claim unchanged `rm_init_adapter` completion. |

The upstream tree has 17 direct `tmrEventCreate` call sites: OS PTIMER-1Hz,
accounting, Hopper SPDM, FECS trace, Hopper confidential-compute timeout,
subdevice timer control, two timer API routes, two external P2060 timers,
video tracing, three Blackwell/Rubin NVLink routes plus the common NVLink route,
timed semaphore and FSP polling. Several data pointers are NULL or plain
allocations, so a blanket NVOC-class OWNER rule would be incorrect. Selected
guards and external-entry exclusions must establish which of these routes are
admitted before EVENT/OWNER rows can be granted. This package grants none.

The exact BIF 1Hz callback and other selected 1Hz registrations still require
whole-profile reachability, owner-lifetime and original error-path review. RC
participation alone does not close them. Direct IRQ participation, full aggregate
stack bounds, bounded PM cancellation, original final destruction and authentic
GSP/DMA cessation remain independent requirements.
