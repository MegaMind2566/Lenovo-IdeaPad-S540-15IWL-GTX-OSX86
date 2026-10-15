# NVIDIA Resource Server and Darwin host services

This bundle connects the original NVIDIA standalone Resource Server to the
selected Darwin runtime and groups the host services needed by later RM work.
It is delivered in **S540-nvidia-transport-v9**, not as separate component
packages. One startup lease, one compiled archive and one report cover the
whole checkpoint.

The implementation is a candidate until native macOS CI, package verification
and the combined laptop result are recorded. Version 0.8.0 remains the
confirmed baseline: 390 kernel startup checks passed, including cleanup.

## Combined implementation

| Area | Included behavior | Current boundary |
|---|---|---|
| Resource Server | Original NVOC objects, server and client lifecycle, parent/child handles, access isolation, sharing and original dispatch/refusal paths | The supported standalone library profile; the global `coreInitializeRm()` and GPU RM are not initialized |
| Host memory | Exact NVIDIA allocation/free and kernel-mapping ABI, wired cached pages, private CPU physical page tables, authenticated handles and deferred allocation release | Device-less, 4 KiB pages, bounded allocation sizes; physical addresses are not device DMA addresses |
| PCI session | Retained provider lifetime, target revalidation, aligned 4 KiB configuration reads, generation-qualified handles and quiescent stop | Read-only observer; no PCI writes, provider open, guessed PCI segment or interrupt registration |
| Real firmware | Official matching GSP and UCODES pair, exact byte hashes, ELF/UCODES parsing and checked bootstrap layout | Userspace file readiness only; no upload, GPU signature authentication or firmware execution |
| Integration | Existing CPU/transport regressions, failure propagation, resource accounting and mixed-generation lease checks | Native concurrency does not establish kernel contention or interrupt behavior |

The [Resource Server component](../nvidia-resource-server/README.md) records its
original source closure, application adapters and explicit constructor
hardening. The [memory service](memory/PROVENANCE.json),
[PCI session](pci/README.md) and [firmware assets](../nvidia-firmware-assets/README.md)
describe their narrower contracts.

## Startup and teardown

`S540NvidiaRmRuntime::checkIntegrated` first executes the existing complete
v8 path. Only successful prerequisites enter the Resource Server and host-service
callback. The provider arbitration used by v8 is released before that callback;
the shared startup lease remains held throughout.

The selected Resource Server starts the checked NVPort core, creates and uses
real library objects, then destroys them and returns the core and reserve to
their cold state. Host-memory and PCI checks subsequently release all owned
objects. A failed prerequisite leaves explicit failed/unrun evidence; it cannot
be reported as successful Resource Server initialization.

The shared startup lease refuses concurrent entry. IOKit provider arbitration
and ordinary service mutexes can wait. `lockForArbitration(false)` permits
deadlock/interruption refusal; it is not a nonblocking try-lock. GPU register
access remains exactly the two earlier read-only identification loads.

## Reporting

Format 9 adds a strict 16-field `RmServices` kernel dictionary, emitted as
`rm_services`. It separates the actual Resource Server, clients, resources,
sharing/dispatch checks, host memory, PCI session, component check counts and
cleanup. The profile is
`standalone-resource-server-cached-host-readonly-pci`.

`FullRmInitialized` remains false. The existing hardware-preparation activity
flags also remain false: device DMA, real kernel firmware verification/loading,
interrupt activation and GPU initialization are subsequent work. The userspace
`firmware_assets` result separately records verified packaged bytes and parsing.
It does not override the kernel activity flags.

The combined success status is `resource_server_prepared`. Installation and
rollback are documented in the [transport package guide](../nvidia-transport/README.md).
No individual memory, PCI or firmware package is needed for this checkpoint.
