# Retained first initialization experiment

This source profile adds a separate manually acknowledged, once-per-boot
experimental operation on the actual persistent bootstrap worker. The legacy
`Owner::initialize` refusal remains byte-for-byte unchanged.

The operation first acquires permanent module, Session and DMA backing holds.
It begins the genuine cancellation operation before global construction, then
begins the actual first-transaction owner epoch. A kernel global entry check
pulls the active owner, master thread, real token and PM state. Genuine global
READY, Context preparation, transaction binding and installed/armed IRQs precede
the original adapter call. Each result is preserved. Failure retains every
implicated owner until reboot; this profile grants no free, unmap or unload.

The 104-byte immutable native profile is supplied by the final linker after
measurement of the actual current objects and graph. It includes explicit
framework, unknown subtree, recursion and exception allowances. These are
experimental assumptions, not complete stack or scheduler proofs. The bundled
manual client observes `kern.stack_size`; IRQ capacity remains an explicit
16 KiB experimental assumption. Exact capacity equality is accepted.

Runtime snapshots use integer fields and a separate nonblocking guard. They
are diagnostic observations and never resource-release authority. A positive
`originalEntered` means genuine original return/attempt evidence was observed;
zero does not prove the original was never entered. Firmware and acceleration
success are not inferred from a wrapper return.
