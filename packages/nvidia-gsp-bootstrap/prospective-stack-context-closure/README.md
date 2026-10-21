# Global allocator context specialization

This opt-in source successor closes the immediate machine-dispatch ambiguity
left when the exact global nonpaged allocator delegated to the exported generic
allocator function. It does not establish an aggregate kernel stack bound.

The input is the exact final `memory_tracking.c` from operational-successor-2,
SHA256 `c27d0ac3576137f9d5c42703f51f4d473d9cfb733781d849acf22099f5c8187e`.
The successor SHA256 is
`b55ae1f99b29127f0707d81ad22711a22237ced3c249c2349ef811b79cc7b27b`.
Existing source profiles and historical receipts remain unchanged.

## Implementation and measured effect

The two original common allocation/free algorithms move byte-for-byte into
source-local always-inline bodies. Existing exported generic functions retain
their ABI and delegate to those bodies. The global paged/nonpaged/free entry
points use the same private bodies, so the compiler sees their actual global
allocator identity while preserving tracking, alias refusals, padding, limits,
locks, OOM behavior and original concrete allocation/free routines.

An inlining request alone is not proof. Fresh actual SDK Mach-O disassembly
must contain exactly the reviewed direct callees in each immediate global
function. The checker rejects both the unspecialized legacy object and a
noinline mutant which restores generic dispatch. Generic dynamic allocator
functions retain their real indirect fallback; original OOM reporting retains
its actual indirect callback.

All three measured immediate global functions report 24-byte static frames.
The nonpaged immediate frame was previously 8 bytes. That increase must be
included in fresh caller/aggregate evidence; no historical aggregate budget is
transferred and no target stack saving is claimed. The complete memory-only
graph is also emitted with all outgoing edges and barriers retained.

## Local validation

`VALIDATION.json` binds these final receipts:

- 13 complete-original-body fatal ASan/UBSan scenarios, 141 assertions, with
  every observation identical to the previous allocator implementation.
- 39 registered original OOM checks on both baseline and successor. Actual
  callbacks and the original reporting interval remain functional.
- Fresh baseline, successor and noinline-mutant Mach-O objects, exact export
  preservation, direct-callee checks and unpruned local aggregate barriers.
- 168 genuine global-owner CPU cases in plain mode and the same 168 with fatal
  ASan/UBSan/function checks, totalling 7,772 assertions. All original
  constructor, allocation-fault, retained-epoch and result observations remain
  identical. Only the memory TU is recompiled per mode; 1,162 bound link objects
  are reused. The record identity is genuine; privileged CPU/platform endpoints
  remain explicit fixtures.

The first genuine replay was invalidated when a checker changed during its
run. Its failed provenance result is preserved. The final second replay uses
frozen control sources and passes all final input bindings.

With authenticated local parents and control artifacts available:

```sh
python3 -B packages/nvidia-gsp-bootstrap/prospective-stack-context-closure/check.py \
  --base build/operational-successor-2 \
  --isolated-controls build/allocator-stack-validation-final-4 \
  --cc ../llvm-repaired/bin/clang --decoder ../llvm-repaired/bin/llvm-objdump \
  --output build/stack-context-local-replay

python3 -B packages/nvidia-gsp-bootstrap/prospective-stack-context-closure/check_integration.py \
  --base build/operational-successor-2 \
  --genuine-controls build/allocator-global-integration-1 \
  --cached-controls build/retained-construction-controls \
  --canonical-parent build/integrated-inputs/compose-check-public \
  --output build/stack-context-global-replay
```

## Remaining requirements

`OOM-SOURCE-AUDIT.json` records the original setter/callback writer inventory.
No named registration callsite was found in the selected original/project
sources, but that is not enforceable producer exclusion. Registered callback
lifetime, replacement races, recursion and transitive duration remain
unproved. The reporting interval provides no stack or PM timing certificate.

The dynamic allocator, OOM and external-provider barriers remain real. A full
current global/adapter/IRQ/callback graph, framework/reentry headroom and actual
target stack capacity still need proof. Linux CPU reuse establishes no Apple
native-cache eligibility, kernel execution, GPU access, DMA stop or PM bound.
All original/global/loader/hardware admission gates remain closed. No CI or
target package is requested by this component.
