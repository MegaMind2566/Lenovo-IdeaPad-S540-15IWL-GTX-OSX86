# NVIDIA CPU support runtime and RM library consumers

This component groups the next CPU-side porting work into one production startup path. It connects NVIDIA string and pseudorandom utilities, checked module initialization, and the original vector/list libraries used by the resource manager to the existing Darwin memory and synchronization backends.

It is included in **S540-nvidia-transport-v7**, version **0.7.0**. The format-7 laptop report confirms this version: `integrated_passed`, all 258 combined kernel startup checks passed (128 support, 72 lifecycle, 35 caller/reserve and 23 foundations), every component true including cleanup, verified PCI provider, the same two-read TU117 variant-41 match and no warnings. This bounded sequential startup checkpoint is complete; no repeat laptop test is required. Native CI evidence remains separate from the hardware result.

## Combined implementation

| Area | Scope |
|---|---|
| Utilities | Pinned NVIDIA string functions, selected safe arithmetic/utility headers and xorshift pseudorandom generation |
| Module lifecycle | Checked memory and pseudorandom-module initialization, explicit failure propagation and reverse-order cleanup |
| RM library consumers | NVIDIA vector and list initialization, insertion, iteration, growth, removal and destruction through real tracked allocators |
| Memory correction | Explicit vector reallocation correction releases the old buffer even when the vector is empty; failed allocation preserves the existing container |
| Integrated startup | Existing foundations, allocation/mutex callers and tracked-object lifecycle, followed by the new support-runtime and consumer sequence under the same exclusive lease |
| Delivery | One reporter, one compiled package and the existing EFI fallback procedure |

The source and adaptation manifests distinguish original bytes from project changes. The vector correction is explicit; it is not presented as an unchanged upstream function. The selected startup is an adapted CPU profile, not the complete upstream `portInitialize()` or the full resource manager.

## Lifetime and allocation contracts

Initialization and shutdown run on an ordinary thread, with interrupts enabled, external lifecycle serialization and no concurrent users. Containers and local pseudorandom objects must be destroyed before their allocator or module is released. Shutdown must refuse live resources rather than freeing them behind callers.

The existing reserve remains **4 MiB**, split into **32 slots** with at most **128 KiB per request**. Allocator and tracking metadata also consume slots. The selected bounded consumers fit this profile; this does not establish a general RM heap, pageable memory, DMA or VRAM allocation.

Xorshift is deterministic pseudorandom generation. It is not cryptographic randomness or a hardware entropy service. A seed derived from uptime does not add an entropy guarantee. Pseudorandom state requires the upstream ownership and synchronization preconditions.

## Validation and evidence

The production entry point runs all CPU blocks together. Completion requires every component to pass and reserve, tracked allocation and OS-object counts to return to their baseline. It creates no worker threads and does not intentionally enter a contended kernel wait.

Native checks cover actual library behavior, vector/list reference models, allocation failure, cleanup, repeated startup/shutdown and shared-lease exclusion. AddressSanitizer and UndefinedBehaviorSanitizer run with fatal diagnostics. Source provenance, kernel compilation/linking, exact platform imports, signatures and report decoding are checked before packaging.

The report adds independent **NvPortSupport** evidence: Core, Utilities, Consumer and Cleanup. Format-7 success requires this block, all existing CPU evidence blocks and the unchanged TU117 match. Missing or failed evidence cannot produce `integrated_passed`.

## Hardware boundary

This component adds no GPU access. The probe retains exactly one read-only BOOT_0 load and one conditional read-only BOOT_42 load, with the existing identity, power-state, mapping and provider guards.

HAL/RM construction, GPU initialization, firmware loading, DMA, hardware interrupt handling, command execution, Metal and graphics acceleration remain unimplemented. Kernel contention, interrupt-context execution, suspend/wake and runtime unload remain unvalidated.

## Installation and rollback

Use the [transport package guide](../nvidia-transport/README.md). The entire block has one combined laptop checkpoint; individual utility and container changes do not require separate packages or reports. Keep the working Samsung EFI as the fallback and use the 240 GB test EFI for the candidate.
