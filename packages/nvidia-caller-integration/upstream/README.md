# NVIDIA allocator and mutex caller inputs

This directory integrates three exact allocator function bodies from NVIDIA
release `615.78.08`, commit `1a82fbfda8f321b056eb3568850f9316c5e465c5`.
The enclosing translation unit is an adapted extraction, not the full NvPort
MEMORY module. The original MIT notice and function bodies are preserved.

`nvport_allocator_callers.c` compiles `_portMemAllocPagedUntracked`,
`_portMemAllocNonPagedUntracked` and `_portMemFreeUntracked`. They call the real
NVIDIA allocation OS interface. The wrapper preserves its original handling of
zero length, a failed allocation, and a null free.

The extraction selects the original release-only checked-assertion behavior.
Checked builds and externally supplied assertion replacements are rejected.
No tracked allocator, global allocator initialization, user-copy, spinlock,
semaphore, RW-lock, resource manager, GPU initialization or graphics capability
is supplied by this excerpt.

Original ABI headers, the complete source reference, and the public memory and
debug contracts are reused from `../../nvidia-os-adapter/upstream`; they are not
duplicated. `reference/memory_tracking.h` preserves the complete original
declarations for the three private NvPort entrypoints. It is a provenance
reference, not a compiled tracking implementation.

`PROVENANCE.json` records original file identities and the exact extracted body.
The targeted verifier pins Git object hashes independently of manifest hashes,
checks the unchanged function bodies, checks the narrow C ABI and rejects
unrecorded source changes even when a manifest checksum is updated.

The caller APIs do not remove backend context or capacity limits. The bounded
Darwin reserve contract is documented by the integration package; it is not a
claim that arbitrary upstream RM allocation contexts are supported.

`nvport_mutex_callers.c` preserves the five original function bodies for
caller-owned `PORT_MUTEX` initialization, destruction, blocking acquisition,
conditional acquisition and release. The mutex structure and declarations
come from complete pinned references in `reference/`. Mutex creation through
`PORT_MEM_ALLOCATOR`, module initialization and other lock types are excluded.

Mandatory `PORT_ASSERT` remains active: a failed predicate calls the declared
non-returning `s540NvidiaCallerAssertionFailed` backend. The predicate is
evaluated once. Checked assertions alone use the original release profile.
`PORT_FREE` can only be reached if a mutex unexpectedly contains a tracked
allocator: the extraction treats that as a fatal unsupported-contract failure.
It never substitutes a fake successful allocator free. Normal caller-owned
mutex initialization always sets that field to null.
