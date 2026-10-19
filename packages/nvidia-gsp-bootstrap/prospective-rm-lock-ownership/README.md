This isolated successor observes the current ordinary thread's actual API TLS,
per-GPU ownership mask and GPU allocation-lock owner. The existing per-GPU mask
does not include allocation-only ownership. The new original `locks.c` getter
calls the existing `_rmGpuAllocLockIsOwner` and `rmGpuLocksGetOwnedMask` under
the original GPU state spinlock. A statusful getter in original `rmapi.c`
checks the actual resource-server initialization and API-lock/TLS binding before
calling the existing TLS owner query. It reads TLS before taking the GPU state
lock. No mutex, ownership field, TLS slot or ready flag is added.

The caller must already hold a serialized, completed global-RM lifetime epoch
that excludes global teardown and concurrent ISR/DPC owner transfers. The query
does not issue or authenticate that epoch. Actual global-running, portable
initialization, exact `SYS_GET_INSTANCE`, `!PDB_PROP_SYS_DESTRUCTING`, ordinary
context and nonzero thread observations reject incomplete or inconsistent
states. Those observations alone cannot protect a concurrent object lifetime:
`g_pSys` is published before lock initialization, `running` remains true during
shutdown, and pending-DPC owner setters do not all take the state spinlock.

The legacy RM system semaphore is excluded only by the exact selected source
model. The basic-lock feature is 1; generated allocation/free/owner macros are
documented stubs; the three complete original acquire/conditional/release bodies
are no-ops. The full immutable 4005-file V3 inventory, those raw and composed
source hashes, candidate code and compiled project dependencies are checked by
`SOURCE-CONTRACT.json`. A nonnull live `pSema` is rejected as inconsistent. The
literal original owner macro is never used by the query. Final combined-image
definition/relocation binding remains an integration prerequisite.

The CPU controls compile ten complete original bodies and three exact private
types. Lifecycle, TLS values and ownership fields are explicit fixtures;
Darwin thread identity, context and spinlock APIs execute in user space.
Controls cover incomplete initialization, destruction, mismatched system,
invalid context/thread, preserved outputs, each owned domain, allocation-only
ownership with a zero per-GPU mask, and another thread observing its own empty
set while the original owner stays intact. They do not execute original lock
acquisition, adapter initialization or kernel code.

Run the isolated check with a fresh output directory:

```sh
python3 packages/nvidia-gsp-bootstrap/prospective-rm-lock-ownership/check_lock_ownership.py \
  --upstream "$UPSTREAM" --v3-root "$V3_SOURCE" --namespace "$NAMESPACE" \
  --output "$OUT/rm-lock-ownership" --sdk "$KERNEL_SDK"
```

The source input must be the exact frozen V3 tree, with its unchanged sibling
`project-overlay` directory; that companion's complete inventory is also pinned
before its actual checked-timer headers are consumed. An SDK extracted from the
pinned archive also requires `--sdk-archive`. Linux controls require the explicit
`--host-control` option and configured Clang C/C++ drivers. Four compile actions
produce kernel-target Mach-O objects from complete original `locks.c`,
`rmapi.c`, `os.c` and the typed query. These C units do not consume IOKit SDK
declarations; SDK identity verification is distinct from those compile actions.
See `LOCAL-CONTROL-VALIDATION.json` for the actual local result.

The standalone preparer also requires fresh output outside its source inputs.
Its source-contract controls reject overlapping output before any write and
reject pinned input symlinks even when their target has the expected bytes.
The verified local replay passed 78 observation controls in both ordinary and
ASan/UBSan/function variants, seven source-contract tests, three explicit
configuration refusals and all four kernel-target compilations. LeakSanitizer
could not inspect this executor's process tasks and was disabled in that
replay; the report states this separately from the passing object cleanup
counter. These are Linux controls and Mach-O cross compilations. Native Apple
validation is still required.

This directory is outside automatic production source discovery. The frozen
firstTxn package and its generic `OriginalLocksReleased` refusal are unchanged.
An empty current-thread result proves neither all-thread unlock nor queue/timer,
IRQ/DMA, client/resource, text, power, stack or target-kernel admission. No GPU
entry, cleanup authorization, production gate or Lenovo test is enabled here.
