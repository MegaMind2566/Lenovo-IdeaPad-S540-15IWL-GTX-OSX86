# DMA containment remains blocked

This directory is evidence only. It contains no selectable source preparation
module, runtime API, DMA-stop receipt issuer, or PM acknowledgement path.

An actual PCI Command readback after clearing Bus Master Enable can establish
the value observed at that instant. The public SDK `setBusMasterEnable()` return
value reports the previous state, rather than success. Retaining backing and
IOVA protects their lifetime, but does not prove outstanding PCIe traffic drained.

The proposed permanent host-request seal cannot currently be implemented only
in Session and the IOPCIDevice configuration writer. In the selected TU117
profile, `kbifStopSysMemRequests_GM107(..., NV_FALSE)` enables BME through
`GPU_BUS_CFG_WR32`. The generated TU117 dispatch selects
`gpuWriteBusConfigReg_GM107`, which writes the BAR0 `NV_PCFG + index` aperture
using `GPU_REG_WR32`, bypassing the transport's `configWrite` guard. Keeping BAR0
mapped preserves that alternate writer. This is a source-reachable path; this
audit does not claim it executes after every diagnostic attempt.

The first missing proof is a complete, enforceable boundary across those
original MMIO writers, all retained CPU producers, and device firmware.
Guarding only the public host configuration path would falsely claim an
irrevocable seal. A complete writer inventory and authentic producer closure
must precede any admitted implementation. A physical-reclamation receipt would
require additional hardware evidence.

NVIDIA's selected BIF implementation separately clears BME to inhibit **new**
function-0 system-memory requests and polls `TRANSACTIONS_PENDING` for
function-issued completions. Its full FLR caller ignores some precondition
failures, resets the device and restores configuration, so it cannot be reused
as a containment API. Neither BME-off nor this completion flag alone establishes
all posted writes drained or a bounded safe parent power transition.

The selected checked GSP shutdown already preserves stage failures. Its suspend
mailbox, SEC2 halt/mailbox result and WPR2-down checks describe the original
protocol, rather than whole-device DMA cessation. No duplicate status profile
was created. `ContextValidateDmaStopReceipt` continues to refuse.

Unvalidated implementation sketches were moved to `build/dma-containment-draft`.
They have not been compiled, executed, admitted, or included in an integrated
candidate. No containment, deadline, hardware, physical-release or PM-ack gate
is opened. Exact selected-source bindings are recorded in
`DMA-CONTAINMENT-BLOCKERS.json`.
