# NVIDIA ResourceServer subsystem

This package runs NVIDIA's actual `RS_STANDALONE` ResourceServer and NVOC object runtime on the existing Darwin NVPort services. It advances the port from independent container consumers to a real server, client database, resource graph and resource API lifecycle. It does not initialize the global Resource Manager or the GPU.

The source is pinned to NVIDIA open-gpu-kernel-modules **615.78.08**, commit `1a82fbfda8f321b056eb3568850f9316c5e465c5`. The complete selected closure contains fourteen C translation units. The existing v7 list translation unit and its header are byte-identical and shared instead of linked twice. Ninety original source/header references are preserved with SHA-256 and Git blob hashes in [PROVENANCE.json](upstream/PROVENANCE.json). [BUILD.json](upstream/BUILD.json) records the exact source and compile profile.

## Implemented behavior

`S540NvidiaResourceServer::check()` constructs a real server and creates two actual NVOC `RsClient` objects with `RsClientResource` proxies. It allocates actual `RsResource` parent/child objects, checks handle isolation between clients, rejects invalid classes and duplicate handles, applies and revokes real sharing policies, and releases resource trees and clients. Server destruction also cleans up a live resource graph.

The application adapter explicitly provides two parameterless classes and kernel-resident parameters. It calls NVIDIA's generated constructors directly, preserving NVOC metadata, casts, constructors, method dispatch and destructors. It does not provide fabricated GPU classes. The original base resource refuses duplication and unsupported control commands; these refusals are part of the exercised API behavior. Base-client callbacks retain their original standalone semantics, so this profile does not claim process security-token authentication or a complete RMAPI interface.

The checked NVPort core and bounded reserve are initialized before the server and shut down in reverse order. The successful complete scenario needs twenty-nine free reserve slots after the two-slot core baseline, for a measured peak of thirty-one of the existing thirty-two slots. No reserve expansion is introduced.

## Explicit adaptations

The original references remain unchanged. The compiled server copy has three documented changes:

- Check every constructor acquisition, publish `bConstructed` only after success, release partial acquisitions in reverse order, and clear ownership after failure.
- Replace the empty standalone global-policy hook with the complete unchanged `serverInitGlobalSharePolicies` implementation from upstream RM sharing code.
- Track the actual top-lock mode in `serverFreeResourceTree`, including a missing-handle compatibility path that originally acquired a read lock and released it as a write lock.

A ResourceServer-only header overlay also replaces the two typed iterator macros. Each macro calls the generic list/map/multimap implementation through its original C signature, then assigns its returned base iterator into the typed union. This removes incompatible function-pointer calls while preserving all function-sanitizer checks. Container structures and the shared list implementation remain unchanged. Provenance tests derive both the exact compiled server and header overlay from the original references.

## Darwin services and limits

The separate backend supplies ordinary-thread RW-lock exclusion, thread identity, bounded refcounted thread-local storage and diagnostics. Read and write locks both use the existing real owner-thread OS mutex. This preserves exclusion and ownership without adding concurrent-reader optimization. The TLS adapter supports thirty-two active thread records and sixteen entries per thread, refuses exhaustion, and rejects shutdown while references or locks remain. It is an application backend for this selected subsystem, not NVIDIA's complete TLS/interrupt implementation.

All entry points require the shared outer startup lease and initially cold services. The production sequence creates no workers and performs no GPU register access, DMA submission, interrupt registration or firmware loading. Full `rm_init_rm`, `coreInitializeRm`, `RmClient`, GPU resource classes and hardware initialization remain outside this package.

## Verification

The native production entry completes **45 checks**. The backend suite completes **134 checks**, including thirty-two concurrent TLS threads and 4,800 contended lock updates. The allocation-pressure suite completes **598 checks** across thirty-one constructor and thirty-one full-graph pressure cases, verifies twenty-nine real failure cases, and then recovers through the complete production entry. All suites require complete cleanup. The provenance suite contains ten checks of source hashes, derivation, ABI sharing and compile profile.

Local Clang native runs and fatal AddressSanitizer/UndefinedBehaviorSanitizer runs passed using the actual production backend. Linux execution uses a scratch-only monotonic-clock compatibility include for the existing Darwin clock adapter; it is not included in the package. Intel macOS CI and the combined laptop checkpoint are recorded by the parent transport package.
