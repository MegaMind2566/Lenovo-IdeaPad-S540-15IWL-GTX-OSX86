# Prospective original-operation cancellation

The production bootstrap owner now binds a fixed cancellation record to its
exact original `nv_state_t` and persistent worker. The real PM revocation hook
publishes that record before posting shutdown to the worker. Failed cleanup
retains the binding; successful stop removes it only after the PM callback
owner is excluded. These changes do not admit original initialization:
`PowerLifetime` and the other current gates remain blocked.

`S540NvidiaGspCancellation.c` uses a generation-tagged atomic word and contains
no heap owner pointer, allocation or RM lock. A stale producer cannot revoke a
later binding at the same state address. The first revocation records a real
monotonic timestamp and fixed 30-second deadline; repeated requests cannot
extend it. The PM lease records its actual callback event time under the same
guard as revocation. A later original-state binding carries that earlier time
and immediately refuses preparation; it cannot start a fresh budget. Future
event timestamps are rejected. A publication flag prevents unbind/rebind from racing timestamp
storage. Checks are valid with CPU interrupts disabled; a real one-millisecond
retry pause additionally requires ordinary thread context.

An active initialization operation returns the existing
`NV_ERR_OPERATION_ABORTED` after revocation. Its original error unwind must
explicitly enter a separate cleanup phase. Cleanup checks permit the required
hardware teardown until the same absolute deadline expires, then return an
error that must retain all original, DMA and callback owners. Finishing a
cancellation scope records only that the original call returned; it is not a
GPU-stop receipt. No reset/lost/shutdown GPU bit is invented.

The check applies to the bound operation worker. It does not silently enroll
independent timer, work-queue or IRQ threads in that scope. Those producers and
their drains require their own reviewed ownership and cancellation contract.
The [lock/drain design](LOCK-CANCELLATION-DESIGN.md) explains why an OS callback
cannot return early through the original `void` lock wrappers.

## Isolated original wait candidate

`prepare_wait_candidates.py` checks the exact SHA-256 of four pinned original
translation units and writes proposed copies, a reviewable unified patch and
an extraction manifest to a separate output directory. It changes no original
snapshot, checked-source manifest or ten-patch production profile.

The proposal checks revocation before Falcon halt/condition reads, before each
GSP event-drain iteration, inside the RPC poll and status-queue loops, and before
bootstrap attempts. It propagates every Falcon wait error and prevents an
explicit abort from becoming an ECC-disabled GSP boot retry. Original cleanup
status propagation and lock reacquisition must be reviewed together with this
candidate before composition.

The source-body fixture compiles complete actual proposed functions with the
full original headers and namespace. Only register/timer/event endpoints are
explicit CPU fixtures. A separate thread revokes after the actual body has
entered its wait; the body itself returns the abort. Baselines also verify
that the same functions observe normal condition completion.

| CPU control | Checks per plain/fatal-sanitized variant | Scope |
|---|---:|---|
| Fixed record | 38 | Exact owner/identity, 16 concurrent revocation producers, immutable earlier-event deadline, future-time refusal, generation reuse, cleanup phase, interrupt-safe checks and real retry pause |
| Actual original wait bodies | 40 | Four baseline/completion and in-wait revocation trials: condition wait, Falcon halt, inner GSP event drain and status queue |

Run `check_cancellation.py` with `--upstream`, `--namespace` and `--output`.
`--host-control` permits a Linux CPU control; without it the existing native
builder requires Intel macOS. The local Clang 18 plain and fatal address,
undefined-behavior and function-type controls pass. All four complete proposed
translation units also compile against the pinned original headers with
warnings treated as errors. These observations are not native Apple CI or
kernel execution for this new candidate.

No test here starts a Falcon, executes GSP firmware or proves its processor/DMA
stopped. Observed CPU-fixture abort latency is not a worst-case hardware or OS
scheduling guarantee. Original checked unwind, actual GSP-stop receipts,
callback/lock drains and the aggregate deadline remain necessary before the
single experimental laptop initialization can be admitted. See the
[PM deadline audit](../platform/POWER-DEADLINE-AUDIT.md).
