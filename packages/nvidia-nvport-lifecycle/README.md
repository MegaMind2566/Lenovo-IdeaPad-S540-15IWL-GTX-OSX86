# NVIDIA NVPort memory and object lifecycle

This component extends the v5 caller checkpoint with tracked allocator lifecycle, real allocator-owned mutex/spinlock creation and destruction, checked bootstrap failure, and resource accounting. It is integrated into the [v6 transport package](../nvidia-transport/README.md). The format-6 laptop report confirms version 0.6.0: all 72 lifecycle, 35 caller/reserve and 23 foundation checks passed in the Tahoe kernel, including cleanup, with no warnings. This bounded sequential startup checkpoint is complete; no repeat laptop test is required. It does not establish kernel contention, interrupt behavior, full RM operation or GPU initialization.

It is not a full NVPort core or NVIDIA resource-manager implementation. It adds no GPU access, firmware, DMA or graphics acceleration.

## Original source and explicit adaptations

The extraction pins NVIDIA release `615.78.08`, commit `1a82fbfda8f321b056eb3568850f9316c5e465c5`. It includes 31 memory functions and 11 synchronization functions. Forty-one function bodies are unchanged. The memory bootstrap is explicitly adapted to return `NV_STATUS`, check both lock-storage allocation and OS spinlock initialization, unwind on failure, and publish initialized state only after those succeed. It does not reuse the upstream unconditional-success core initializer.

The [provenance manifest](upstream/PROVENANCE.json) and [source notes](upstream/README.md) identify original inputs, unchanged bodies, the checked-bootstrap adaptation and the fixed compilation profile. Original MIT notices remain in the source and references.

## Selected contracts

- Ordinary-thread lifecycle with external quiescence; one exclusive startup lease covers v5 and v6.
- Global and custom allocator dispatch, allocation/free, allocation counters and allocator release.
- Allocation counts and cumulative requested bytes follow the original counter profile. Active/peak byte sizes are not tracked when allocation-size headers are disabled.
- Original owned-object creation releases tracked storage if OS object initialization fails. Destruction releases both the OS object and allocator-owned storage.
- Kernel spinlocks save and restore the exact prior interrupt state. Owner, nonrecursive and quiescent destruction preconditions remain caller responsibilities.
- The reserve remains 32 fixed slots of 128 KiB each (4 MiB total), with 16-byte alignment. Bootstrap and allocator metadata consume slots. Zero, oversize and exhausted requests fail explicitly. It is not a general RM heap or DMA/VRAM allocation service.

NVIDIA's selected Unix allocation profile is non-interrupt context and no sleeping. The reserve's lock-free bitmap does not expand that contract to interrupt execution. Kernel contention, interrupt callers and suspend/wake require separate validation.

## Diagnostics and failure scope

Mandatory assertions reach a real fatal backend. Formatted diagnostics use a bounded 512-byte buffer and real output. The kernel bridge refuses interrupt or interrupt-disabled diagnostic contexts with a fatal contract error. Native-only fault injection and simulated context controls are excluded from the kernel build.

The combined kernel startup never registers an OOM report callback and always requests silent memory shutdown. The original non-silent registry report traverses tracking state while holding a spinlock; that diagnostic/callback path is outside this kernel profile. It is not silently replaced with a successful no-op.

## Validation

The production entry point combines existing foundation/caller checks with global/custom allocation, owned-object lifecycle, bounded exhaustion/reuse and complete cleanup. It creates no workers and does not intentionally enter a contended kernel mutex wait. Reserve slots, tracked allocations and actual OS mutex/spinlock object counts must return to their initial state.

Native CI separately covers bootstrap storage/initialization failures, original owned-object failure cleanup, arithmetic overflow, reserve exhaustion, repeated lifecycle, native concurrent allocation/synchronization, and fatal assertion subprocesses. AddressSanitizer and UndefinedBehaviorSanitizer use fatal diagnostics. Kernel compile/link, exact platform imports and all source hashes are verified by the enclosing transport builder.

Actual results and source identity are recorded in the compiled package's `BUILD.json` and `validation/lifecycle-checks.json`. Native tests exercise functional userspace backends; they do not establish kernel interrupt or blocking-wait behavior. No separate laptop test is selected for an individual primitive or wrapper.
