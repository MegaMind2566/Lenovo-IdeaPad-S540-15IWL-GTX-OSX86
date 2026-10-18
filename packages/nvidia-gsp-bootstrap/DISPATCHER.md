# Persistent RM owner thread

`Dispatcher` creates one real ordinary thread and keeps its identity for every
accepted action. It uses `kernel_thread_start` in the kernel and a pthread in
the explicit native control. It does not use a thread-call pool and does not
increase or switch the kernel stack.

Synchronous callers receive the actual action status. Asynchronous producers
can post through a preallocated 16-item ring without allocating or sleeping.
Successful posting means accepted work; it does not mean that RM stopped or
that a power transition can be acknowledged. Failed asynchronous actions remain
visible in the snapshot.

Stop closes admission and drains every accepted action. Stack-backed synchronous
requests remain owned until the worker publishes their completion. The worker
cannot invoke or stop itself synchronously. Start, stop and destruction are
externally serialized; callers must exclude new entries before destroying the
facade. A dispatcher abandoned before successful stop retains its heap state.

The kernel finish event establishes the end of owner-data and callback access.
The worker then cooperatively terminates itself through XNU; the caller drops
its explicit thread reference. This protocol does not prove kext text unloading
safe during the final termination handoff. Executable-code lifetime remains an
admission requirement for a future loadable driver.

The native harness covers 400 concurrent synchronous calls on the exact same
worker identity, real error propagation, startup acquisition failures,
recursive waits, interrupt-context refusals, bounded-ring exhaustion and stop
while a callback is blocked. Its 53 assertions passed in ordinary and fatal
ASan/UBSan/function controls. An explicit Mach-O cross-compilation against the
pinned SDK also passed. These observations do not establish Apple kernel
execution, aggregate kernel-stack safety, device power lifetime or GPU work.

Source identities and scope are in [DISPATCHER-CONTRACTS.json](DISPATCHER-CONTRACTS.json).
