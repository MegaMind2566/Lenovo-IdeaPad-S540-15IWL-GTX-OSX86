# Prospective original IRQ installation

This opt-in source successor connects the permanently retained operational Owner,
its actual Session, and the original Context interrupt wrappers. It adds explicit
worker-dispatched `installDiagnosticInterrupts()` and
`quiesceDiagnosticInterrupts()` methods. `Owner::initialize()` still refuses
original entry. No loader, global-lifecycle, operational admission or physical
release gate is opened.

Installation requires the actual validated global epoch, exact retained owner,
original private state, four distinct initialized Context stacks, operation
cancellation scope, live PM lease, and the same Session hardware-lifetime
generation and PCI handle. The contract calls the existing original
`rm_gpu_handle_mmu_faults`/`rm_isr` Context wrapper and both existing original
bottom-half wrappers. An additional Context adapter-entry prerequisite refuses
entry without that installed, armed, still-current bridge. Any stop attempt
permanently invalidates this prerequisite, including when retained Session bits
remain set.

Before OS registration, the actual backend reads `getInterruptType(0)` and a
bounded PCI capability inventory under provider arbitration. This first profile
accepts only an observed message-signaled vector on an actual one-vector MSI
device without MSI-X. Context pulls those immutable backend observations itself
and sets the original `NV_FLAG_USES_MSI`, preserving unrelated flags. Unknown,
legacy, MSI-X, broader vector capability or a previous mode selection refuses.
No historical target report or caller-provided mode Boolean is admission.

The Linux original registers its live IRQ before `rm_init_adapter`; the original
`rm_isr` requires a non-null private state and safely refuses before GPU state
load. The source-pinned controls exercise these actual branches, including the
Context wrappers. They do not execute GPU initialization or a target IRQ.

PM revocation publishes cancellation through the existing producer, then the
actual worker attempts controller detach, ISR/BH software drain and original
persistent masking. Software and complete drain results remain separate.
Pre-GPU or sticky/closing cleanup may refuse the original mask helper; all
callback owners and backend storage remain retained. A retained backend stop
result is never converted into a successful teardown, PM acknowledgement, DMA
stop receipt, or release authority. A coordinator that performs original global
initialization, Context preparation and binding remains a separate prerequisite.

Local controls run the unchanged selected backend, bridge and identity bodies
against explicit OS/record/API fixtures, plus the actual original pre-init IRQ
bodies with complete original headers. `check.py` cross-compiles only the three
changed translation units with the already authenticated parent SDK commands.
These controls do not prove real IOKit execution, hardware delivery, callback
duration, a genuine CPU stack boundary, the PM deadline or whole-runtime closure.
