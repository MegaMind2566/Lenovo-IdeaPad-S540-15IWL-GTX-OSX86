# Actual GSP boot memory and retry contracts

The pre-publication audit of the B10 source found two additional host-side
bootstrap defects. Neither proves an incorrect message reached GSP: the B9
target test stopped before GSP boot, during VBIOS extraction.

`kgspCreateRadix3_IMPL` requests noncontiguous memory with a 2 MiB GPU page size.
The actual descriptor-to-OS path forwards that page size to the Darwin memory
service, which correctly rejects unsupported geometry with status 86. The
original fallback accepts only status 81 (`NV_ERR_NO_MEMORY`), so it cannot
recover this unsupported request. Nor may a later retry erase the first
retained allocation refusal. This profile requests the real 4 KiB geometry
before the first allocation. The original allocation status, existing
no-memory fallback, table construction, data copying and error cleanup remain
unchanged. It does not make the backend accept huge pages or relabel them.

The cancellation insertion in the original GSP boot retry loop assigned its
result to the previous attempt's `status`. A healthy cancellation check thereby
erased an earlier boot error before the original timeout-reset condition.
The check now uses a separate local status. Cancellation errors still stop the
loop immediately with their actual status; a healthy check preserves the prior
boot result until the original timeout reset and next boot attempt.

Only these two exact source sites are transformed, after the selected PCI
topology profile. There are no new translation units, exports, protocols,
hardware claims, release authority or changes to the allocation/cancellation
producer gates. CPU controls exercise the actual transformed source bodies and
reviewed descriptor/OS geometry and retry boundaries with explicit host
endpoints. Native image validation and a new Lenovo test remain necessary.
