# NVIDIA RM container inputs

`list.c`, the three container headers and the reference files are exact NVIDIA inputs from commit `1a82fbfda8f321b056eb3568850f9316c5e465c5` (release `615.78.08`). `PROVENANCE.json` records their Git blob identities, SHA256 digests and source paths. The six provenance checks verify the complete original bytes and the exact derivation of the compiled vector source.

`vector.c` has one explicit bug fix in `_vectReallocHelper`: the old buffer is freed after the optional successful copy, including when the vector is empty. Allocation or copy failure preserves the old buffer and capacity. The exact original remains in `reference/vector.c`. No other vector or list function body is changed.

Both libraries are used by the actual NVIDIA RM source. The pinned `rs_client.c` reference uses lists for access back references and CPU mappings. The pinned GPU interrupt manager uses `vectInit` for its interrupt table; its source path, Git blob identity and call site are recorded without compiling or importing that interrupt manager.

The three small headers under `include/nvport`, `include/utils` and `include/nvmisc.h` are project bridges. They select the release container layout, connect to the existing tracked `PORT_MEM_ALLOCATOR`, preserve diagnostic return paths and route mandatory invariants through the existing assertion bridge. They provide no successful replacements for unavailable OS services. Their include directory must precede the older adapter include directory for the two container translation units and their direct consumers only.

`S540NvidiaRmConsumer::check` runs with a caller-owned initialized allocator and ordinary-thread lifecycle lease. It checks growth, copying, insertion/removal, iteration, lookup, intrusive ownership, failure preservation, recovery and destruction. It leaves reserve slots and tracked allocations at their initial counts. It never initializes or shuts down the global memory subsystem.

The selected caller uses independent four-byte values, a vector capacity at most 32 and a list at most six nodes. Native model stress uses vector capacity at most 64 and lists at most 12 nodes. These bounds fit both `NvU32` byte arithmetic and each 128 KiB reserve slot. The broad original API does not provide checked capacity multiplication, synchronized concurrent mutation or insertion from a source that aliases a buffer being reallocated. This consumer does not exercise those unsupported cases.

The standalone native harness injects failures at 12 allocator callback positions and executes 64 cycles of 128 model-checked vector mutations, plus list allocation/removal and empty-buffer regressions. The real tracking and reserve backing remain in use. Native execution does not establish kernel contention, interrupt behavior, a complete Resource Manager instance or GPU initialization.
