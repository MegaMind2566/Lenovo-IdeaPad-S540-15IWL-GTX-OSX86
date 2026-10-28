# Selected optional ACPI backend capability absence

The B9 Lenovo report confirms selected optional NVLink absence and completion
of GPU child attachment. It stops during GSP preparation with VBIOS extraction
status `0x51` (`NV_ERR_NO_MEMORY`). The report's first host refusal is external
site 0/service 0, which cannot identify the producer: ACPI and the outer original
allocation-context guard share this value. The available counts do not prove a
missing ROM or memory exhaustion.

The original `RmInitAcpiMethods` calls `acpiDsmInit` before `kgspInitRm`. Its
optional supported-function and DOD probes enter the deliberately disabled RM
ACPI-events backend. That backend returns `NV_ERR_NOT_SUPPORTED`; our unchanged
facade additionally publishes a sticky service refusal, after which retained
host allocation correctly refuses further work. This is a source-supported
candidate for the observed allocation failure, not a uniquely traced B9 event.

This profile changes only two optional initialization call sites in the actual
`acpi_common.c`: supported DSM function-list probes and DOD discovery. The exact
active original transaction and the actual compile-selected version-2 disabled
RM ACPI-events backend permit a bounded absence record before the facade call.
The operation still receives `NV_ERR_NOT_SUPPORTED`. The original code fills
failed DSM cache states, unavailable generic/callback capabilities and the DOD
failure status; no success, display list or AML result is fabricated. Every
other call, invalid authority and enabled backend follows the
unchanged original route and refusals. All six ACPI facades remain unchanged.

The private record contains at most one bit per 12 supported-function queries
and one DOD observation, only for the same immutable generation. Repeated valid
queries are idempotent and do not add observations. A failed reservation remains
unavailable. Existing pure B9 strong-record
authority functions inspect the actual ordinary master, global epoch and real
stable cancellation producer; their historical NVLink names grant no additional
capability. No service-counter/cached readiness flag is used as authority.

The 32-byte scalar witness is readable and logged only after the real original
wrapper returned. No pointers, resets, cleanup permits, new AML calls, allocator
gate changes or user protocol changes are introduced. Backend absence says
nothing about hardware ACPI methods, platform power ownership or GSP success.
