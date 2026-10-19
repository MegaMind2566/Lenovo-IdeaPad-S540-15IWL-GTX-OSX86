# Isolated first-transaction candidate

This package adds reviewable ownership and cancellation boundaries for a finite
initialization attempt. It does not change the production profile, gate mask 15,
kernel entry, firmware candidate or laptop-test plan. No hardware-stop receipt
is issued. The complete original runtime remains unadmitted.

The strong record starts before original Host allocations, then attaches the
exact original `nv_state_t` once. The companion
[`prospective-host-retention`](../prospective-host-retention/) allocator tags
real allocations with that immutable owner/generation. Actual Host, crypto and
memory refusals publish sticky failure before caller rollback frees. Physical
free permits and first refusal share one atomic order; earlier committed frees
must actually complete, later frees retain their backing and metadata.

The original-source patch applies strictly after frozen V3. It defers adapter
failure cleanup, preserves real API/GPU token release, records inner GSP failure
before reviewed member cleanup, and guards original destruction before its
first destructive action. Eight original translation units and one typed
metadata/counter bridge are independently compiled. The ledger preserves open
transitive and success-path ownership obligations.

Real device/global queues and timer registries bind to the strong record.
Acceptance reserves a genuine lease before publication. Original wrapper return
and the later action return are distinct. A direct timer return cannot retire
accepted work borrowing its event. Failed post-destruction notification keeps
the registry owner as a dead-backend tombstone, preventing retries through a
freed backend pointer. The fixed seal endpoint performs actual service stops
and drains outside original locks; under-lock destruction guards only
revalidate the sealed generation and sticky state.

Run the complete candidate from any working directory:

```sh
python3 /path/to/repo/packages/nvidia-gsp-bootstrap/prospective-first-transaction/check_first_transaction.py \
  --upstream /path/to/pinned-nvidia-source \
  --namespace /path/to/real-generated-S540GlobalRmNamespace.h \
  --output ./first-transaction-check \
  --cc /path/to/clang --cxx /path/to/clang++ \
  --sdk /path/to/pinned-clean-MacKernelSDK \
  --v3-root /path/to/materialized-verified-V3
```

All generated source, objects and logs go beneath the resolved output path.
An output inside the repository must be a descendant of `build/`; package,
upstream, SDK and explicitly supplied V3 source trees are rejected before any
component runs. The exact package, companion Host and project dependency
inventories are checked before execution and again after all components return.
Omitting `--v3-root` lets the original-source helper reconstruct V3 there.
Default execution requires Intel macOS. Explicit `--host-control` permits
separately labelled CPU controls elsewhere; an SDK archive in that mode is
cross-compilation evidence only. SDK verification requires the pinned clean git
checkout (including absence of untracked headers), or an explicit
`--sdk-archive` whose pinned bytes and complete extraction inventory match.
Historical Linux reports
are retained under component `evidence/`; a new native run generates new reports.

The component controls currently distinguish actual implementation from
explicit test endpoints:

| Evidence | Scope |
| --- | --- |
| 74 original boundary checks | Actual wrapper/API-lock/NVOC/constructor bodies; GPU init and record endpoints are explicit controls. |
| 20 queue and 24 timer checks | Real service boundaries and fault retention; record/policy dependencies are explicit controls. |
| 24 joint checks | Strong record, real Host/crypto/memory and queue/timer ports; original callback metadata/policies are typed test controls. |
| 20 checks across 12 original bodies | Actual work/nano/public wrapper bodies with real services and strong record; an earlier sticky error survives a successful original result after the lock-release marker. Typed test descriptor rows remain separate from production policy. |
| 267 companion Host controls | Real allocation/free/first-refusal ordering, owner reservation, allocation failure and lifetime stress; see its generated report. |

`OriginalLocksReleased` still returns `NV_ERR_NOT_SUPPORTED` after reading real
API/GPU ownership because the RM-semaphore capability is unresolved. The
production original descriptor table authorizes only the reviewed nano-work
shape; EVENT/OWNER rows, RC policy, pending-arm replacement, exact work GPU
instance binding and direct IRQ participation remain admission gates. Closing
admission may conservatively refuse an unreviewed causal descendant; this
retains resources and is not proof of complete producer semantics.

Successful CPU controls do not close transitive inner cleanup, scalar/fatal
failure coverage, PM deadline/cancellation, aggregate kernel/IRQ stack budget,
capacity or authentic GSP/DMA-stop proof. No final service/context/text-owner
release exists in this candidate. PMstop is not a join and software drain is
not hardware DMA cessation.
