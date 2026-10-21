This opt-in successor closes the selected global allocator dispatch and initialization race. It changes two actual NVIDIA portable core/memory translation units and adds one small guard unit/header. Original-entry, loader, kernel and hardware gates remain closed.

The previous first-core chain reaches a mutable global callback through `portMemAllocNonPaged`. Writable global getters prevent a named-writer scan from proving that callback's lifetime. A second raw portable initializer can also return success before the first initializer installs its callbacks; the first initializer can then fail and clear them. The successor authenticates the genuine record's current IN_CORE master before changing either initialization counter, rejects concurrent or recursive initialization, and publishes readiness only after the actual memory initializer completes. Raw global allocation/free refuses before publication. Original untracked tracking-lock allocation and nested TLS/NVLOG references remain exercised. The retained base portable reference and global memory metadata cannot be shut down through these entries.

Exact global allocator addresses select the existing static NVIDIA alloc/free wrappers, independently of writable callback fields. Original padding, counters, fences, limits, zero/overflow handling and OOM logic surround those calls. Generic dynamic/existing-block callbacks remain original and indirect.

Tracking initialization also has a genuine source boundary. Its original body is private static; the three original global setup sites retain their order after successful tracking-lock setup. The public ABI delegates generic tracking only after memory publication and refuses either global allocator address or any reserved main/paged/nonpaged tracking address. Global tracking reads select original immutable static storage by the compile-time fence profile. Nonglobal alloc/free/release reject reserved tracking aliases, and static unlink refuses those aliases before mutation. Existing-block constructors reject regions overlapping the global metadata object. These checks cover the reviewed entrypoints; they do not make arbitrary writes through exposed C structures safe.

`VALIDATION.json` binds 13 actual-body ASan/UBSan scenarios and 141 assertions. They exercise initialization races, foreign entry/completion, lock failure, callback poisoning, tracking aliases/reentry, retained shutdown and genuine dynamic/existing-block behavior. Three mutants fail their required assertions: restored global indirect dispatch, bypassed identity authorization, and bypassed public tracking refusal. Three source-contract controls reject changed source/writer bytes or unexpected inputs.

`INTEGRATION-VALIDATION.json` records the separate cached integration, which executes the actual global-owner record and original construction with this allocator successor: **168 plain + 168 fatal ASan/UBSan/function cases**, 3,886 assertions per variant. It covers all 154 constructor allocation positions, two additional postcore positions and terminal controls. Only actual core, memory, guard, lifecycle and harness units are freshly compiled per variant; 1,098 original, 57 project and three auxiliary objects are authenticated and reused unchanged. The former raw portable setup scenario now verifies refusal before genuine IN_CORE, with no allocation or core side effect. The historical failed constructor report remains unchanged. Privileged-CPU/platform facts remain explicit Linux fixtures; the genuine record identity is not a fixture.

Four fresh SDK cross objects bind baseline memory, changed memory/core and guard to commands, dependencies and stack captures. All ten guard exports are strong definitions without implicit constructors/destructors. Immediate global alloc/free functions have no indirect transfer in this output. Nonpaged now delegates the generic helper (8-byte local frame); paged calls the original untracked allocator directly (24 bytes); free is 24 bytes. The complete local readiness-guard graph is 16 bytes including its return address. Generic helper context, OOM callbacks, recursive/external depths, worker/IRQ headroom and actual target capacities remain unresolved aggregate-stack requirements.

The package contains source and compact receipts. Generated evidence stays under `build/allocator-stack-validation-final-4` and `build/allocator-global-integration-1`. The earlier pre-tracking receipt is preserved under `build/allocator-stack-validation-final-3/reviewed-VALIDATION.json`; it is superseded. Historical CPU objects lack a recorded compiler executable digest, so reuse establishes no native-cache eligibility. None of this executes a kernel or GPU or establishes PM/DMA safety.

The planner declarations in `prepare.py` are `INPUTS=()`, `ORIGINAL_INPUTS/original_transforms`, `COMPANIONS`, one `original-c` `PROJECT_UNITS` entry, ten `EXPORTS`, `INCLUDE_DIRECTORIES` and `COMPILE_DEFINITIONS`. Transformation requires exact base hashes and changes no existing record ABI.

```sh
python3 -m unittest discover -s packages/nvidia-gsp-bootstrap/prospective-allocator-stack-closure/tests -v
python3 packages/nvidia-gsp-bootstrap/prospective-allocator-stack-closure/check.py \
  --base build/integrated-successor-5 \
  --native ../native-latest/first-transaction-image/composition \
  --cc ../llvm-repaired/bin/clang \
  --llvm-objdump ../llvm-repaired/bin/llvm-objdump \
  --sdk ../MacKernelSDK --output build/allocator-stack-new-check
python3 packages/nvidia-gsp-bootstrap/prospective-allocator-stack-closure/check_integration.py \
  --controls build/retained-construction-controls \
  --composition build/integrated-inputs/compose-check-public \
  --output build/allocator-global-new-check
```
