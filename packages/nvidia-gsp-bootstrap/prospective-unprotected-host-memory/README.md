# Selected ordinary host-memory profile

This profile changes only the exact B6 allocation bridge and its outer original
wrapper failure diagnostic. The queue profile selects real 4 KiB pages first.
The allocation bridge admits the original unprotected-memory request only after
its own native CPUID observes GenuineIntel family 6, display model 0x8e, basic
leaf 7 available, and neither the advertised hypervisor bit nor the TME bit.
All allocation geometry, ownership, DMA translation and retention gates remain.
Unprotected=0 retains its existing behavior and does not query CPUID.

This is a trusted physical-target observation, not cryptographic proof against
a VMM that masks CPUID, and makes no claim that all CPU memory is unencrypted.
The unchanged Darwin backend allocates and zeroes ordinary owned IOBuffer VM
pages. SGX capability may be present; those ordinary pages are not reserved
EPC. No MSR, host encryption setting or incoming request flag is changed.

Allocation diagnostics report actual scalar parameters/status/raw CPU facts,
bounded to the first unprotected call plus sixteen failures. The separate outer
failure line reports the real first-transaction snapshot after the original
public wrapper returned, preserving its quarantine and error result.

`check.py --input-project BASE/project --output FRESH --cxx CLANGXX --host-control`
compiles the complete selected allocation service and Session bodies. Only the
raw CPUID instruction body is replaced in the generated CPU fixture. Observations
and OS resources are synthetic; this cannot establish Darwin compilation,
physical CPU facts, GPU initialization or a hardware DMA stop. Fatal address
and undefined sanitizers run separately; leak sanitizer is explicitly disabled
on the traced host and is not reported as passing.

`check_context.py --base BASE --output FRESH --cc CLANG` checks the separate
outer-return diagnostic and preserves refusal, quarantine and return behavior.
