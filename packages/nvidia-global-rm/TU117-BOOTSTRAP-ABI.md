# TU117 bootstrap ABI review

The successful native development build at project commit
`d81b19845bf31bca61464e198bdc883790af05bc` still had **132 reviewed
callbacks without implementations**. This is a historical baseline, not the
count after subsequent implementation. Its actual-bridge link did not retain
the source-gated `coreInitializeRm`/`RmShutdownRm` lifecycle. The final combined
build must measure both closures again.

[The pinned inventory](upstream/adapted/TU117-BOOTSTRAP-ABI-AUDIT.json) enumerates
all 132 callbacks, their exact original type and failure policy, 424 lexical
references in original C sources, source hashes and ten reviewed branch
anchors. It grants **no production reachability exclusions**. Lexical retention
is not a runtime call graph: an absent C reference may come from a macro or
header, while a retained generic OS wrapper may never run on the selected GPU.

| Baseline family | Callbacks | Required review |
| --- | ---: | --- |
| Diagnostics | 6 | Ordinary messages, error paths, fatal invariants and crash records |
| RM ACPI services | 9 | Initialization before GSP boot, methods and notification policy |
| Power and console | 11 | Real PM reference, runtime D3 policy and original console detection |
| Tegra SoC | 15 | Actual PCI device facts and the original GPU property guards |
| User mappings, processes and events | 20 | Kernel clients as well as any exposed user entry |
| DMA imports, peers, UVM and fabric | 23 | Ownership, cleanup and request admission for every path |
| NVLink host primitives | 6 | Common library construction as well as link training |
| NUMA, pages and system memory | 13 | Real Darwin VM/device facts or a proved unreachable subsystem |
| Host files and capabilities | 9 | Global construction, teardown and capability namespaces |
| Virtualization and build facts | 5 | Runtime feature use and actual compile-time GRID configuration |
| PCI, cache, port I/O and VBIOS | 15 | Original initialization and fallback routes |

Several source facts affect the first combined profile:

* `RmInitAdapter` calls `RmInitAcpiMethods` before the GSP boot block.
  `nv_acpi_methods_init` cannot be omitted because the GPU is non-console.
  The original `nv-acpi.c` supports an explicit build with RM ACPI events
  disabled: zero registered handles, no subscriptions and unsupported method
  calls. A selected Darwin equivalent must describe that unavailable RM
  feature, rather than claiming the machine has no ACPI. Its power ownership
  still needs an independent implementation.
* GSP bootstrap flags directly call `os_is_grid_supported` under `NV_UNIX`.
  Physical GPU admission does not exclude this callback. The original result
  derives from `NV_GRID_BUILD`; an ordinary build's false result is a genuine
  build fact. Runtime guest/VFIO operations are separate contracts.
* `rm_init_adapter` computes `client_managed_console` through
  `rm_get_uefi_console_status` before guarding console access. A zero field in
  the newly allocated context does not prove the later result is false.
* `DynamicPowerManagement=0` and `EnableS0ixPowerManagement=0` are documented
  original policies for the initial profile. They require real RM registry
  writes/readback and entry-path review; neither replaces a Darwin power
  reference. `NvLinkDisable=1` controls training, and does not prove that
  common NVLink host allocation helpers are unused.

The diagnostic facade now implements `nv_dev_vprintf`, `nv_log_error` and
`os_bug_check` with their pinned original ABIs. Device messages include actual
original-state PCI identity and severity; Xid reports reach the system log.
The Xid boundary does not expose a Linux trace stream or vendor subscription
API. Fatal bug checks call kernel `panic`; they cannot return success. Native
controls observe actual formatted output, truncation and fatal subprocess
termination. They exercise neither kernel execution nor GPU initialization.

The selected backend policy is now profile version 2, recorded in
[PROFILE-CONTRACTS.json](PROFILE-CONTRACTS.json). Its actual original registry
transaction writes and reads back the three power/NVLink settings and then the
version marker. It first verifies the real global registry is empty: the
original registry API provides no individual-key removal operation. A failed
stage destroys only that owned cold registry and verifies it is empty. Existing
entries cause refusal before mutation; refused or incomplete rollback is
recorded as unavailable. The source overlay propagates the formerly ignored
registry initialization status and checks the original derived
`RMNvLinkControl=1` write/readback.

The profile deliberately registers no RM ACPI method handles or notifiers,
following the original disabled-events backend semantics. Its six unsupported
method endpoints preserve outputs and increment the real unavailable-call
observer when reached. They are defined unavailable features, rather than
working ACPI services, and any such call prevents aggregate runtime admission.
The actual platform battery and ACPI facts remain independent.

The global lifecycle now checks the real registry is cold before entering the
original constructor. This prevents the constructor-failure shutdown path from
destroying another registry epoch after the profile helper refused it. Failed
construction and ordinary shutdown use the same complete cleanup predicate,
including host allocations, invalid frees, unavailable calls and crypto state.

The shared host allocator now records an ownership domain on every reserved
and published pointer. Original `os_alloc_mem` and NVLink allocations use the
original domain; explicit bootstrap context, timer and firmware allocations
use the external domain. A free must match that recorded domain. A mismatch
retains the exact allocation and increments invalid frees, so original cleanup
cannot silently release bootstrap storage. The global lifecycle checks that
the original domain is empty; the outer host shutdown still requires both
domains to be empty. No equality of baseline counts is used as a substitute
for recorded ownership. The owner's initializer continues to refuse original
RM execution while the remaining runtime gates are unresolved.

Before a combined laptop package can admit original RM, the production link
must have no unresolved runtime dependencies, every unavailable feature must
have a source-backed request/path policy, and the real power, active-IRQ
allocation lifetime and aggregate stack contracts must pass. Generated typed
failures, a successful control link and CPU checks do not meet those gates.
