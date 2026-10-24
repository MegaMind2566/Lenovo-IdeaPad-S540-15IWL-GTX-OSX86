# Retained IRQ source selection

This isolated B6 profile transforms five exact generated B5 inputs. It selects
one MSI source from the complete Apple-published controller/specifier arrays,
rather than assuming source index zero is MSI. Apple may append an MSI source
after a legacy source. The maximum accepted published inventory is 32 sources;
every source type must be known and exactly one must be message-signaled.

The existing PCI capability inventory must still be valid, expose MSI with one
hardware vector, and expose no MSI-X capability. Source-array count is distinct
from hardware vector count. The chosen source remains fixed through registration,
enable, disable, unregister and callback provider/source checks. Before enable,
the complete inventory is queried again and the selected index, count and type
must match. A partial failure never substitutes another source or clears the
retained identity.

The profile adds no `configureInterrupts` call and no direct PCI MSI writes.
Virtual property/type queries use Apple's existing lazy resolution path, which
can allocate OS interrupt resources. This framework behavior is not described as
side-effect free. Existing owner, power, cancellation, DMA, callback and release
checks remain in force; these diagnostics grant no hardware-stop or unload
authority.

Four runtime observation fields preserve the last non-failed stage, first failed
stage, and actual call attempt/return masks (global, context, transaction, IRQ,
adapter at bits 0 through 4). Fourteen route fields travel through the existing
transport statistics into the published owner snapshot. Source counts are counts,
not masks. Probe attempt/return flags qualify its status and observed counts;
`inventoryValid` qualifies capability values. Selected-source/type validity
records the retained selection and may remain true after a later probe refuses.

`check.py` extracts the actual selected production function bodies and executes
them with explicit CPU fixtures for the OS and strong-record endpoints. It
reproduces the old source-zero refusal and checks the selected lifecycle,
ambiguous/unknown/oversized inventories, all preserved hardware restrictions,
callback identities and partial failures. Plain and fatal ASAN/UBSAN runs must
pass; ten actual-body mutants must fail. The C++ invocation alias is preserved
while the resolved compiler file is authenticated. These controls execute no
IOKit, original RM, hardware IRQ or GPU initialization.

The legacy-zero/MSI-one layout is a CPU regression fixture supported by Apple's
source behavior, not an authenticated capture of the Lenovo's actual source
array. The next physical test must report its observed route and runtime stage.
