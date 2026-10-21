# Permanent operational session lifetime successor

This opt-in successor gives the real bootstrap `Owner` an explicit
`retainDiagnosticLifetime()` operation. Its existing persistent ordinary worker
checks its actual prepared context, cancellation binding and live PM lease, then
reserves an atomic image pin and calls the genuine
`beginRmHardwareDma(&transport)`. Failed acquisition releases only the image
reservation. Once the real Session holds the hardware lifetime, the reservation
becomes permanent, including a revocation racing acquisition or later failure.
No caller readiness Boolean, stop receipt or final-release API is added.

The same stable heap `Impl` continues owning the context, transport Session,
firmware copies and Store, PM lease, platform, dispatcher, snapshot guard and
service bindings. Core stop and context detach refuse before their first
destructive operation. The actual Session independently refuses backing/IOVA
reclamation and unbinding while the hold exists. The required loader successor
refuses module stop and preserves its control-service state while the real
image pin count is nonzero. Its transport already owns actual provider and
service retains; retaining a pointer alone is not used as an ownership proof.
The public facade may disappear without destroying the retained `Impl`.

`retainedDiagnosticOwner()` yields the exact retained `Impl` identity only after
successful hardware-lifetime acquisition. The integrated entry coordinator must
call `s540FirstTxnBeginOwner` once on that same worker before original global
allocation, and establish the real cancellation operation/record binding before
original calls. This helper does not claim that epoch itself. The retained Host,
direct-backend and permanent global-epoch profiles remain required; their
object-level retention covers original logical destruction inside RM.

The PM callback atomically pulls only the original guarded monotonic PM event
through `Lease::revocationEventNs()`. Its original producer stores that event
with release ordering. The hook needs no second service guard acquisition and
publishes real cancellation with that exact
timestamp before enqueueing the owner stop. This avoids the old callback's
`power.snapshot()` registry/provider queries. The cancellation deadline remains
the real event plus 30 seconds. No PM acknowledgement, PMstop, software drain or
successful protocol return is treated as hardware cessation.

`prepare.py --composition COMPOSITION_JSON --output FRESH_OUTPUT` emits four
project replacements and one original GSP TX-source replacement. The image
integrator must also apply `loader_transform`
to the actual isolated loader. No frozen file, root builder, workflow or
production admission profile changes here. `initialize()` remains a refusal
and reports all four blocked gates.

Run explicit CPU controls with the genuine pinned namespace:

```sh
python3 packages/nvidia-gsp-bootstrap/prospective-session-lifetime-closure/check.py \
  --upstream /path/to/pinned-nvidia-source \
  --namespace /path/to/genuine/S540GlobalRmNamespace.h \
  --assets /path/to/verified-firmware \
  --output /path/to/fresh-session-controls \
  --cc /path/to/clang --cxx /path/to/clang++ --host-control
```

These execute the real transformed Owner, Session, Context, Store, tracked Host,
timer binding, dispatcher, PM protocol and cancellation. Provider observations
and physical/device page addresses are explicit native backend fixtures;
original RM bodies are typed abort tripwires. Tests cover failure before hold
acquisition, foreign-caller dispatch to the exact worker, permanent hold/replay,
real logical page and mapping retirement without physical release, failed core
stop, PM producer ordering and the unchanged deadline, and facade destruction.
The permanent case intentionally keeps its real worker and all owners alive.
Address/undefined/function sanitizers remain fatal; LeakSanitizer is disabled
for these intentionally retained owners.

The recorded local controls pass 115 checks in each ordinary and fatal
sanitizer run, plus five source/admission ordering contracts. Both changed
production C++ translation units also compile against the pinned kernel SDK
as x86_64 Mach-O objects with warnings treated as errors and the 4096-byte
frame warning enabled. These Linux controls and cross-compiles do not prove
target kernel execution or complete-image linkage.

This closes an operational ownership gap; it does not prove the required
revocation-to-hardware-stop bound. Original wait cancellation, complete unwind,
producer and IRQ closure, original shutdown, posted PCIe writes and device DMA
must all fit the actual 30-second PM deadline with scheduling margin. The parent
may remove device power when that timer expires even if software retains every
byte. Target kernel linkage/execution, original stack bounds and authentic
hardware cessation evidence remain separate admission requirements. The package
must not open original entry while those proofs remain absent.

**Remaining PM deadline proof.** `PM-DEADLINE-AUDIT.json` pins the actual composed
source bytes and anchors. The reviewed condition/Falcon/status-queue/RPC receive
polls now check cancellation; their old long ThreadState budgets alone are not
the minimal remaining gap. The parent Turing GSP-init send path reaches
`GspMsgQueueSendCommand`'s TX-space poll without a cancellation check. Its local
timeout restarts at one second for each of at most 16 fragments. That is a
nominal per-message bound, with scheduler and endpoint latency still outside it;
it does not bound the complete revocation, original unwind and hardware stop.

The opt-in original TX successor now checks the exact GPU's genuine
cancellation scope at each space-wait iteration and immediately before submit.
Actual `msgqTxGetWriteBuffer` only exposes unpublished free slots;
`msgqTxSubmitBuffers` alone advances the write pointer and writes `TX_HEAD`.
An observed cancellation can therefore return through the original status path
while retaining partially staged fragments without publishing them. No rollback,
free, reset or successful completion is invented. There is no shared atomic
commit word between PM revocation and the final queue submit: a concurrent
revocation after the last check can still race a genuine accepted command.
The source keeps that committed-send result and the retained hardware lifetime.

`check_tx.py` executes the exact original transformed send body, the actual
unmodified msgq free-space/get-buffer/submit bodies and the genuine composed
cancellation record. All 114 checks pass in both ordinary and fatal sanitizer
variants. Hardware registers, clock, timeout and CC endpoints are explicit
fixtures. Controls cover partial staging, real revocation during a wait,
cleanup deadline expiry, no/foreign binding, pre-submit revocation and a
revocation at actual commit. The complete changed original translation unit
also cross-compiles as x86_64 Mach-O with warnings treated as errors and the
4096-byte frame warning. These close the observed TX polling gap while the
aggregate PM deadline and concurrent commit ordering remain unproved.

The original GPU-lock-release deferred-work path can also enter a queued 1Hz
list and synchronously call `pProc(pGpu, pData)` through a void function pointer.
The list traversal and individual callback body have no demonstrated time or
cancellation bound. A genuine pending callback must be bounded or excluded by
an exact source-derived policy; a cancellation check around its invocation
cannot bound time inside it. This is a conditional reachable obligation, not a
claim that every first initialization runs such a callback. The actual Context
DMA-stop receipt verifier still returns `NV_ERR_NOT_SUPPORTED`. These concrete
gaps keep `PowerLifetime` closed; increasing a timer or retaining allocations
does not resolve them.
