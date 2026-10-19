# Retained direct Darwin backends

This isolated source successor keeps direct Darwin service storage, locks,
timer/workqueue thread calls, PID references and the Host guard alive after the
actual permanent first-transaction owner begins. It adds no hardware or original
entry admission, stop receipt, final-release issuer, or installable driver.
Frozen project sources are inputs only.

`prepare.py` reads a complete composition and emits nine exact changed project
files plus `project-successor.json`. `transforms(values)` is also composable with
the other fixed source profiles. There are no additional translation units.

The actual strong record owns bounded, thread-bound lifecycle permits. A
preowner create/free increments the scope count before reading phase. BeginOwner
reserves phase before checking that count; sequentially consistent operations
prevent both sides from missing each other. A busy preowner scope makes owner
admission fail without publishing an epoch, including a racing sticky refusal.
An active epoch only captures its actual authorized owner/generation. It never
issues a physical-release permit.

Every actual Guard stores its immutable birth tuple. Public timer/workqueue
destruction checks retention before cancel, stop, join or thread-call release.
All synchronization final frees check before altering or testing held tokens.
Partial object/guard/worker construction failures retain allocated backing and
initialized lock parts. An intrusive permanent list records retained storage
without another allocation; repeat final frees cannot release or duplicate it.
An older object remains explicitly unassociated, without being retagged. A
conservative reservation-time retention remains permanent even if preflight
later rolls back. PID final release retains the process reference too.

HostShutdown takes a preowner-only strong-record release scope before changing
Host state. It returns false for a real active/reserving or sticky epoch even
when Host has zero allocations. Thus heap counters cannot authorize deletion of
its separate IOLock or clearing its initialized facts.

Run the actual implementation controls with:

```sh
python3 packages/nvidia-gsp-bootstrap/prospective-retained-backends/check.py \
  --composition build/composed-retained-rc-shutdown-platform/composition.json \
  --upstream /absolute/pinned/open-gpu-kernel-modules \
  --kernel-sdk /absolute/pinned/MacKernelSDK \
  --cc /usr/bin/clang --cxx /usr/bin/clang++ \
  --output /absolute/fresh/control-output
```

The default requires native Intel macOS and the actual Apple compiler. It links
the control executables with Darwin dead stripping, signs them and verifies
their signatures before execution. Use a composition that has not already
applied this successor. For explicit Linux x86_64 controls add `--host-control`,
select the Linux clang binaries, and supply `--sdk-archive` when the SDK is an
archive extraction. Retained-resource leak suppression is Linux-only.

The reviewed local run passes fourteen cases and 130 checks in each ordinary
and fatal ASan/UBSan/function-sanitized executable. It executes the actual
transformed strong record, Darwin backend methods and Host
Initialize/Preflight/Shutdown, with actual crypto/memory counters and cancellation
implementation. Controls cover preowner physical cleanup, held locks, retained
live callbacks, repeated destruction, constructor failure at storage/guard/
condition/worker stages, startup failure before IRQ arm and queue binding,
sticky/foreign/generation mismatch, create/free/Host-release admission races,
sticky reservation, and failed-reservation lifetime.

Only allocation/free/reservation scheduling points are paused in control copies.
Unused original metadata adapters abort if invoked. The raw timer return hook
has the explicit no-wrapper-binding behavior; these tests do not exercise GSP
wrapper lease settlement. Seven uninstrumented changed kernel translation units
also compile against the verified entire pinned SDK. Execution uses the actual
POSIX backend, not the Darwin kernel; native linking, thread-call execution and
GPU behavior remain untested here.

This successor must still be composed into a fresh complete image. Transport
Platform/IRQ resource retention belongs to the coordinated IRQ participant;
this directory does not transform IRQ bodies. Explicit timer Cancel and queue
Stop retain their normal drain semantics. The profile only prevents physical
final release and implicit destructive actions; it does not certify callback,
interrupt, device-DMA or module-text quiescence.
