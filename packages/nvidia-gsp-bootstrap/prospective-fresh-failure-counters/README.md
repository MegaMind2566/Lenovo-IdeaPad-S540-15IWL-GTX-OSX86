# Fresh diagnostics after a failed original adapter call

B7 exposed the first sticky refusal but printed the first-transaction **seal
cache** as if it were a current service sample. The cache is normally populated
only during successful sealing or destructive-transition validation; both
paths stop before refreshing it when a failure is already sticky. Its zero
values therefore cannot establish that no allocation or service failed.

This profile preserves that cache, labels it `counters=cached`, and separately
reads the existing fresh service getters after the public original wrapper has
returned. An unavailable source prints its actual read status, without invented
counter values. The fresh read does not refresh the seal or change any first
status, lock, owner, cleanup, hardware or stop decision.

The supported allocator's failures do not increment the unsupported-memory API
counter. A separate diagnostic observer now records atomic saturating
module-lifetime attempt, failure and entry-rejection counts, plus an atomic
maximum requested page count. Counters are sampled independently; they are
not a coherent cross-counter snapshot. No existing `AbiStatistics`, Session,
binding or live allocation array is read by the new getter.

The first failure observer to reserve a zero-state slot writes an immutable
scalar tuple and release-publishes it. The getter reads that tuple only after
an acquire observation of its published state. A reserved, unfinished tuple
is explicitly unavailable. It records the actual failure stage, request flags,
geometry and existing raw CPUID observations, without an extra CPU probe or
retained pointer. Invalid-state entries only increment their counter; their
request geometry is not inspected. No production API resets the observer.

`s540DeviceReadAllocationDiagnostics` is a private scalar-only C API. Its getter
requires the actual ordinary master thread and the actual first-transaction
record's original-wrapper-return observation, with no original call in flight.
Failed reads leave output untouched. It neither relies on callback quiescence
nor creates it. Its status and observed mask distinguish unavailable evidence
from observed zero. This is not a new user RPC or lifetime authority.

The independent attach/constructor witness is sampled through its actual typed
getter. Logs distinguish last progress, the first failure, constructor class
and ordinal, and the validity of missing-engine/GSP-client observations. An
instance is a loop ordinal, never an encoded address. `complete` means an attach
exit was observed, including failed exits; it does not mean initialization
succeeded.

At most seven fixed scalar log records are emitted for one failed wrapper return.
The old initialization guards, status propagation and retained-resource policy
are unchanged. There is no new user RPC, pointer logging, encryption operation,
cleanup authorization, fabricated success, or target result.

CPU controls compile the complete actual Services **KERNEL branch** with explicit
ordinary/interrupt/logger/fatal endpoints and a separate complete actual Session
translation unit. They exercise actual request stages and flags, immutable failure publication,
DMA mappings, retirement and drain refusal through those real bodies. Eight
concurrent writers separately stress the actual atomic observer, and a reserved
publication-state control verifies that unfinished fields remain unavailable. Separate C controls
execute the actual inserted helpers and unchanged adapter boundary with the
actual C headers and explicit getter/original-return endpoints. Only the raw
CPUID body is replaced in the Services fixture. These are host controls; actual
Darwin SDK compilation, final native stack measurement and the Lenovo test
remain separate requirements.
