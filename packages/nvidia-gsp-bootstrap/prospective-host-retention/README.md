# Isolated Host heap retention proposal

This proposal changes isolated copies of the real Host allocator, crypto refusal
boundary and unsupported-memory facade. Production sources and compiler defaults
remain unchanged. The strong first-transaction record is an explicit required
input; there is no weak implementation or success fallback.

Each allocation records its immutable real owner, transaction generation and
allocation serial. `BeginOwner` must precede the first original global allocation;
the exact `nv` identity attaches later without retagging earlier allocations.
Unassociated original allocations and unpublished allocation reservations make
the real Host preflight refuse. Allocation capture is rechecked after reservation
and before allocating backing. The record must return `NOT_READY` during its
reserving phase. These two checks close the legacy-capture/publication race.

A physical free requires a real one-use record permit. Permit admission and first
refusal share the record's atomic ordering. Already admitted frees complete after
refusal; later frees logically retire their exact pointers, retaining physical
backing and live-byte counters. A retired slot cannot be reused or shut down.
Metadata for backing already released remains separately reserved until actual
permit completion. Completion refusal retains a zero-byte pending node, never
claims retained physical backing, and never retries `IOFree`.

All record capture/acquire/completion calls run outside the allocator guard.
Refusal publication is atomic and never calls back into Host. The record's Host
preflight reads guarded Host state plus the real atomic crypto and memory ever
counters; it does not call the record again. The first-transaction startup still
requires its actual outer owner and startup serialization.

A call lease precedes every dynamic Host guard access. Shutdown closes admission
only by an atomic transition from exactly zero users, so an allocation paused
before its first reservation, a snapshot, an inspector or native fault-control
call cannot use a deleted guard. Initialization resets individual non-ever
fields; the unavailable and invalid-free atomic streams are never copied or
reset. Static service instrumentation uses atomic storage without touching the
dynamic guard. This gate does not establish module lifetime or completion of
first-transaction callbacks. The platform-facts getter returns a borrowed pointer
into static storage: an actual consumer needs the outer owner's retention through
its last use and before another initialization can replace those facts.

The actual central Host unavailable and invalid-free boundaries, crypto
`refuse(symbol)`, and memory `unavailable`/`lifetimeUnavailable` publish the strong
atomic refusal before and after their monotonic counter updates, before subsequent
inner frees. This covers a refusal racing the record's RESERVING phase as well as
a historical unbound refusal that the real preflight must reject. Official disabled
feature queries and no-op releases retain their original behavior. Domain/symbol
arguments are diagnostics and never authorize execution.

The current revision also publishes actual allocation failure before returning
`NULL`: `NO_MEMORY` for imposed storage/capacity or backend allocation failure,
and `INVALID_STATE` for invalid context or zero size. A capture/recheck refusal
keeps its actual status. The strong hook is inactive while genuinely unbound, so
the ordinary fault-and-retry path remains available there. Once owner reservation
or a transaction exists, the failure is sticky before a caller can perform an
inner free. Allocation failure itself does not increment the unsupported counter.
The prior `0ae6` revision and its exact audits remain in `prior-0ae6/`.

The controls link the actual Host, strong record, participant record, original
memory headers and eight Darwin service implementations. Scheduling observers
surround real `malloc`/`free`; they are excluded from kernel builds. Separate
processes test healthy mixed-domain behavior, pre-Bind reservations, concurrent
owner/free/shutdown ordering, real address reuse, actual completion refusal, and
all four refusal producers before and after `nv` attachment. Additional controls
exercise a real RESERVING refusal and concurrent dynamic-guard readers against
2000 Host open/close attempts and 10000 actual refusal publications. No outer
callback return note is needed to trigger their heap retention.

Use explicit paths to the separate strong record and participant proposal:

```sh
python3 packages/nvidia-gsp-bootstrap/prospective-host-retention/check_heap_retention.py \
  --repo . \
  --record packages/nvidia-gsp-bootstrap/prospective-first-transaction/record \
  --participants packages/nvidia-gsp-bootstrap/prospective-first-transaction/record/deps \
  --upstream build-src/nvidia-upstream --namespace path/to/S540GlobalRmNamespace.h \
  --cc /usr/bin/clang --cxx /usr/bin/clang++ --output path/to/fresh-controls
```

The default requires Intel macOS and verifies thin x86_64 Mach-O objects and
executables. `--host-control` explicitly selects the Linux CPU control. The SDK
probe helper separately compiles the complete Host, crypto, memory and
strong-record translation units with warnings as errors and a 4096-byte frame
diagnostic. Local validation is not native Apple or kernel execution.

```sh
python3 packages/nvidia-gsp-bootstrap/prospective-host-retention/check_sdk.py \
  --repo . \
  --record packages/nvidia-gsp-bootstrap/prospective-first-transaction/record \
  --sdk path/to/MacKernelSDK --overlay path/to/fresh-controls/overlay \
  --upstream build-src/nvidia-upstream --namespace path/to/S540GlobalRmNamespace.h \
  --cc path/to/clang --cxx path/to/clang++ --output path/to/fresh-sdk-probe
```

The SDK helper defaults to an actual Apple compiler on Intel macOS and requires
a clean Git checkout of the pinned kernel SDK. A Linux cross probe explicitly
adds `--host-control`; an archive extraction additionally needs
`--sdk-archive path/to/MacKernelSDK.tar.gz` and a byte-exact full-file inventory.

Both helpers capture actual compiler header dependencies and reject input changes
during their run. The saved local audit records 267 checks in each plain and fatal
ASan/UBSan/function variant, plus four complete Mach-O SDK translation units.

The allocation ceilings remain 8192 records, 256 MiB per allocation and 512 MiB
total. Quarantine can intentionally retain backing for the lifetime of the
loaded image. This does not restore logically destroyed objects, prove all
failure producers, drain accepted work, establish a complete call-chain stack
bound, issue a GPU/DMA-stop receipt or approve original initialization/unload.
