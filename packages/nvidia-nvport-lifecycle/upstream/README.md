# Pinned NVPort memory and owned-object callers

The integration extracts NVIDIA release `615.78.08`, commit
`1a82fbfda8f321b056eb3568850f9316c5e465c5`. The complete reference inputs
retain their original bytes and MIT notices. `PROVENANCE.json` records each
Git blob identity, source location, source-body hash and compiled-body hash.

`nvport_memory_lifecycle.c` contains 31 memory functions.
`nvport_owned_sync.c` contains 11 synchronization functions. The latter replaces
the five-function v5 mutex extraction in the final link. The existing three
untracked allocator callers remain shared dependencies. Linking both mutex
extractions would create duplicate symbols and is unsupported.

## Fixed release profile

The original counter implementation, allocator-list synchronization, global
paged/nonpaged allocators, custom allocators, allocator-owned mutexes and
allocator-owned spinlocks are included. Counter operations reuse the pinned
NVIDIA atomic closure.

Fenceposts, per-allocation lists, caller information, allocation logging, GSP
process limits and existing-block allocators are omitted. They are compile-time
profile choices rather than successful placeholder implementations.

Allocation counts and cumulative requested bytes are available. Active and peak
byte sizes remain zero because this upstream profile does not retain each
allocation's size. Its peak allocation count is not a monotonic high-water mark
when size tracking is disabled. There is no size-query API, ownership validator,
fencepost checker or automatic freeing of outstanding allocations.

`nvport_safe_length.h` retains the original unsigned length-add macro closure
and the original `PORT_SAFE_DEFINE_MATH_FUNC(Add, , Length)` expansion. The
other SAFE operations are omitted.

## Explicit bootstrap adaptation

The sole modified NVIDIA function body is `portMemInitialize`, renamed to
`s540NvportMemoryInitialize` with an `NV_STATUS` result. The original bootstrap
macro ignores two fallible operations. This adaptation checks the ordinary
sleepable-thread context, checks initialization-count overflow, allocates a
temporary untracked spinlock object and checks its OS spinlock initialization.

Both allocations complete before any global initialization state is published.
A failed object allocation returns `NV_ERR_NO_MEMORY`. A failed spinlock
initialization frees the temporary object and returns the actual error. The
globals remain cold in either case. Once the lock is ready, the original
counter-only initialization path has no further fallible operations.

`portMemShutdown` retains its original body. It requires a matching successful
initialization. Lifecycle transitions are externally serialized. All custom
allocators, allocations and allocator-owned objects must be released before the
final shutdown. An allocator must outlive every object allocated through it.
The adapter-only `IsInitialized`, `IsCold` and `AllocatorCount` queries expose
the real lifecycle state without claiming a complete NvPort core interface.

The full NvPort core, `portInitialize`, Resource Manager and GPU initialization
are absent. No wrapper reports success for these unsupported interfaces.

## Assertions and diagnostics

Checked assertions follow NVIDIA's release profile. Mandatory assertions remain
active and invoke the real non-returning assertion hook. Owned-object creation
and destruction use the real tracked `PORT_ALLOC` and `PORT_FREE` operations.

The basic diagnostic profile retains the original printer calls and OOM
callback mechanism. Formatting and emission use an OS adapter hook, not an empty
success stub. The integrated kernel checkpoint uses silent final shutdown and
does not register an OOM diagnostic callback. Diagnostic traversal and callback
execution are not part of its kernel runtime coverage.

The checkpoint provides CPU-side software foundations. It does not implement
interrupt handlers, hardware initialization, DMA, command submission, graphics
or Metal acceleration.
