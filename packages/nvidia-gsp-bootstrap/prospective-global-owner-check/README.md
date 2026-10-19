# Actual global construction under the retained owner

This CPU integration check runs the complete composed `s540GlobalRmInitialize`
implementation, including original `coreInitializeRm`, against the actual strong
first-transaction record, actual retained Host, and actual Darwin CPU services.
`BeginOwner` runs before the first original global allocation; the device `nv`
has intentionally not attached yet. The original record policy is unchanged.

The question tested is specific: does legitimate early global construction delete
an NVOC object which the strong record cannot authorize, and therefore make the
record fail before device attachment? The tested healthy construction does not.
No owner policy change is justified by these results.

| Process | Actual source result | Host/record observation |
| --- | --- | --- |
| Unbound baseline | `NV_OK`, all 15 global children and RS memory-export client | 154 allocations; six physical transient frees; subsequent complete global and Host shutdown succeeds |
| `BeginOwner` before globals | `NV_OK`, same original global objects | All 154 allocations remain physically alive; six temporary frees (2,216 bytes) become logical retirement; record clean; no unknown retained NVOC object |
| Same owner, first allocation fails | Original `NV_ERR_NO_MEMORY` (81) | Record retains the same failure at Host allocation site; global epoch is not initialized; owner and generation remain unchanged |

All three processes pass with the plain build and with fatal address, undefined,
and function sanitizers: 21 assertions in each variant. The observation fields
for Host/record and `result.initialized` describe the construction snapshot.
The baseline's later clean shutdown is separately asserted in its process.
The retained process deliberately ends without a teardown attempt.

The check compiles all 1,100 make-declared original translation units: 1,098 use
the actual composed original source, one is the existing explicitly declared
privileged-CR4 CPU fixture, and one supplies the deterministic version string.
It also compiles 54 actual project units. The two unconditional IOKit loader
translation units are excluded from this hosted CPU binary. Platform facts are
fixtures, and unimplemented native boundary endpoints are exact-typed aborting
tripwires; they cannot manufacture service success. A CPU-only readback is
appended to a disposable copy of the strong record so its private pre-attachment
identity and error state can be inspected. Its prefix remains byte-identical and
the probe is rejected by `#error` in a kernel build.

Reproduce with the pinned source and a verified retained composition:

```sh
python3 packages/nvidia-gsp-bootstrap/prospective-global-owner-check/check.py \
  --upstream /path/to/pinned/open-gpu-kernel-modules \
  --composition /path/to/verified/composition \
  --output /path/to/new/cpu-check-output \
  --cc /path/to/clang --cxx /path/to/clang++ --host-control --jobs 4
```

The evidence file records the exact composition and record digests, compiler
identity, boundary inventory, binary digests, and scenario observations. Per-unit
commands, source/object digests and logs remain in the reproducible output.

The next operational owner successor still needs to establish the genuine global
master epoch on its persistent worker, retain its runtime through reboot, and
check both the original constructor status and the sticky record error before
continuing. Some original optional allocation failures can be recovered by RM
while the stronger transaction record remains failed; a successful constructor
return alone must never grant entry. These controls exercise neither that full
fault matrix nor the GPU, kernel stack, interrupts, hardware DMA hold, unload, or
module lifetime. They change no kernel entry/admission gate.
