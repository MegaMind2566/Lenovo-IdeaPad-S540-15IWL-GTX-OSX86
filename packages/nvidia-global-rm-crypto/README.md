# Global RM cryptographic dependency boundary

This package supplies the 64 exact libspdm ABI boundaries retained by the pinned
global Resource Manager, adapter/GSP, and interrupt-entry closure. **It does not implement
cryptography, SPDM authentication, confidential computing, or verification.**
Boolean operations return `false`, context factories return `NULL`, and the
X.509 date comparator returns its documented invalid-input result `-2`. Every invocation,
including a void free with a NULL context, increments lifetime-monotonic refusal
evidence. Caller buffers, output lengths, and context pointers remain unchanged.
No contexts or keys can be allocated by this boundary. An unknown context is not
freed because this backend could not have created it; its invocation makes the
combined global RM/adapter trial unavailable regardless of its return path.

The combined trial must require `unavailable_calls`, both words of the unavailable symbol mask,
and `counter_overflow` to remain zero after quiescent global startup, adapter/GSP
operations, and complete shutdown. Counters cannot be reset. A zero difference
between two nonzero snapshots is insufficient. A successful combined trial
therefore establishes that these unsupported operations were never requested;
it does not establish that cryptographic services work.

## Why the TU117 profile can exclude SPDM execution

The original generated GPU HAL sets `PDB_PROP_GPU_CC_FEATURE_CAPABLE` only for
the listed Hopper and newer devices. TU117 takes the original false branch.
The original `confComputeIsSpdmSupported` HAL likewise selects its false branch
for TU117. Generated object and method tables nevertheless retain CCSL, keystore,
and hash cleanup references in the deviceless global RM closure. The source
explicitly notes incomplete CONF_COMPUTE/SPDM compile guards.

No generated class table, lifecycle function, hardware capability, or build
feature is altered here to eliminate those imports. The original
`SPDM_NULL_PRESENT` profile is not enabled: its copy-through AES routines and
zero tags would report fake cryptographic success. Real crypto must be supplied
before any future profile can truthfully execute the unsupported SPDM paths.

`portCryptoInitialize` is a separate original nvport pseudorandom generator
initializer. Its upstream documentation explicitly excludes security-sensitive
use; this package does not replace it or promote it to a cryptographic RNG.

## Validation

The compiler checks the facade declarations against nine unmodified headers
from NVIDIA's pinned libspdm 3.5.0 copy. The native refusal test verifies all
64 symbols, caller-memory preservation, NULL and extreme-length refusal,
monotonic evidence, and 16,384 concurrent refusals. These are user-space ABI and
boundary checks. Actual global RM and adapter execution must separately prove
zero invocations on macOS before the combined trial can succeed.

Source anchors and SHA-256 hashes are in `upstream/PROVENANCE.json`. NVIDIA and
DMTF copyright notices remain in the reference headers.
