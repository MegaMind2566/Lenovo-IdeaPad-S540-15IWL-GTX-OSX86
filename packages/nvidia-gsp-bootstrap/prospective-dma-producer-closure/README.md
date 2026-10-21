# Scoped DMA producer guards

This opt-in source profile extends the exact `operational-successor-2`
composition (`40f0fd1f…`) together with the PM revocation profile. It closes
specific CPU BME-enable entry points and adds a retained cleanup-mask identity
observer. It issues no hardware-stop receipt or PM acknowledgement.

The original GM107 bus/function configuration writers acquire the genuine PM
OPERATION commit before their actual BAR0 BME-enable store. Completion is
reported only after that store endpoint returns. Function-1 FMODEL and invalid
function branches preserve their no-store behavior. Misaligned DWORD offsets
are refused, including offsets 1–3 that overlap PCI command byte 4.

The complete Session configuration-write path applies the same commit to a
bound RM enable request. A conservative hardware-lifetime hold is not identity
evidence: the commit still requires the exact genuinely bound cancellation
state and actual current OPERATION scope. Unknown pointers refuse. BME clear
requests retain their existing behavior. If both the backend and completion
fail, the actual backend error remains the result and failed completion retains
the reservation.

Revocation closes new accepted OPERATION commits. A write accepted earlier may
finish after revocation, and remains observable as in flight until its actual
return. A future stop coordinator must drain accepted writes before a checked
BME clear/readback. Neither a zero commit observation nor BME-off proves all
original CPU, firmware, device or posted-write producers have stopped.

The separate cleanup observer reads immutable retained record identity after a
real sticky failure. It requires genuine validated global READY state, actual
adapter-wrapper return, revoked CLEANUP phase before its fixed deadline, no
commit or backend reservation, no unfinished work/direct tickets or event
borrowers, and actual IRQ software drain. Genuine completed callbacks clear
their tickets through the existing return protocol; no invented terminal tag
is accepted. The observer preserves the first error and retained phase.

Only the full IRQ mask path can select this observer, and it repeats identity
checks under the existing actual original API/GPU locks. General callback
drain, original entry, RM/GSP initialization and destruction retain their prior
authorizers. The identity observation does not establish execution of the
transitive original locking/HAL mask path on target hardware.

`SOURCE-CONTRACT.json` binds the exact source transforms. The compact local
receipt distinguishes actual strong-record/cancellation execution, the
complete Session implementation, actual original writer bodies, and explicit
platform/metadata/register endpoints. Linux CPU controls and SDK crosscompiles
are separate from kernel execution and target GPU initialization.

Remaining work includes generic MMIO/config writer coverage, backend restore
and firmware request-generation behavior, complete CPU producer exclusion,
hardware readbacks and posted-write drain, aggregate kernel stack capacity and
the PM deadline. The historical blocked `dma-containment` profile stays
unselectable. All hardware, original-entry, reclamation and PM gates remain
closed; no paid CI is requested.
