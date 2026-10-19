# Single Lenovo test: prerequisite status

The requested deliverable is one controlled original RM/GSP initialization and
shutdown attempt on the S540 TU117. **It is not ready for installation.** The
working Lenovo checkpoint remains v9; no repeat v9 hardware test is requested.
Brightness, external displays and NVIDIA power-off work remain deferred.

The last completed native Intel macOS validation is source commit
`76e0f43c6c1eaf5f259acbe73846e89ecd9be1a7`, Actions run `39175620059`.
Its exact evidence remains in
[NATIVE-INTEGRATION-VALIDATION.json](../nvidia-global-rm/NATIVE-INTEGRATION-VALIDATION.json).
It does not validate subsequent edits. The ten approved original-source
overlays and their historical audits are preserved unchanged.

The subsequent software checkpoint adds explicit central-policy and validated
EFI RSDP lookup contracts, optional PCI identity outputs used by the originals,
and source-backed memory/crypto refusal inventories. The isolated combined
prospective profile compiles its 19 changed original C units and two real
cancellation bridges; it remains separate from the approved ten overlays.
Three further memory-unwind candidates pass their actual-body fault controls.
None of these changes establishes original adapter or GSP runtime success.

The first two follow-up native runs stopped in development instrumentation:
canonical macOS path comparison, then missing compiler `.su` output for truly
code-empty translation units. Both cases have explicit regression controls.
The corrected collector cross-compiles all 1,100 baseline original objects and
binds absent `.su` files only to unchanged objects with no executable bytes.
A fresh native run is still required for this complete checkpoint.

Follow-up run `39182950863`, exact source `2e3ffbb460f4b2384c36edcea84acb5241fee66f`,
has now passed complete native original-source compilation, all 2,398 component
controls in both variants, the actual kernel bridge/link controls and all 156
original global allocation-failure cases in each variant. Its last typed NVOC
proof step failed because its relative output path was interpreted from the
original source working directory. The workflow is therefore **not green**.
[The exact partial native evidence](../nvidia-global-rm/NATIVE-CHECKPOINT-VALIDATION.json)
records that failure and the successful preceding steps separately. The path
fix has an end-to-end real compiler/disassembler regression control; a new
native run must validate it and subsequent candidate changes.

The next isolated profile is documented in [prospective-v3](prospective-v3/README.md).
It composes the memory, cancellation and checked-timer changes without changing
the frozen ten-overlay production defaults. Its 25 changed original C units,
three real C bridges and actual SDK timer backend pass cross compilation;
the separate timer candidate passes 483 controls per variant. Native Apple
validation of these additions is pending. Accepted callback borrowers,
pre-lock terminal drains and guards before original owner destruction remain
required even when direct timer cancellation succeeds.

Run `39208972401`, source `43db7c6a385491899dc3d8b00f4e0f29b276fe96`,
failed before any job step started; its first retry also has no steps or logs.
The repository-check job failed at the same pre-start boundary. The user
confirmed that the GitHub budget was exhausted and authorized restarting after
restoring it. Both jobs have been restarted. The pre-start failures provide no
compilation or execution evidence for the additions.

After that restart, the repository check passed. The native job reached the
compiler controls but failed the new end-to-end NVOC fixture because its LLVM
GEP parser rejected the compiler's output. The next parser revision supports
documented canonical no-wrap flags and retains diagnostic IR/object inputs.
Byte-offset guesses and dynamic member indices still fail. A fresh native
run must establish the actual Apple-compiler result.

The [isolated idle-loader prototype](prospective-loader/README.md) passes its
local state and SDK controls, with entry permanently closed. The separate
[checkpoint3 rotation-entry proof](../nvidia-global-rm-crypto/selected-route-proof/README.md)
checks the exact historical native inputs; it cannot be transferred to a new
source profile by changing hashes alone.

| Requirement | Current evidence and remaining work |
|---|---|
| Original callback contracts | [The complete 110-callback ledger](../nvidia-global-rm/CALLBACK-PROFILE-AUDIT.md) distinguishes implemented services, official disabled queries, unavailable operations and lifetime guards. Definitions alone do not close operational coverage. Remaining internal/error routes require implementation or independent exclusion. |
| Device memory and PCI identity | [Memory contracts](../nvidia-device-transport/MEMORY-CONTRACTS.json) cover exact original ABI checks, actual retained PCI DVSEC reads, refusal boundaries and bounded allocation diagnostics. Failed requests preserve output and ownership. |
| DMA lifetime | IRQ drain and actual hardware DMA cessation are separate requirements. Logical frees retain backing and IOVA through original engine destruction until an exact session/generation receipt is independently validated. The approved source profile has no receipt issuer. |
| Adapter failure ownership | A failed original Boolean initialization now quarantines its context. [Prospective checked unwind](adapter/ADAPTER-STATUS-AUDIT.json) propagates lock and teardown errors and preserves residual ownership. Its original-source changes remain isolated pending complete composition and review. |
| GSP teardown | [Prospective source changes](cancellation/GSP-TEARDOWN-STATUS-PROSPECTIVE.md) preserve first errors from actual suspend/reset/FWSEC/Booter and original GPU unload phases. Partial boot and void engine destructors require retained DMA ownership; no stopped bit is accepted as a substitute for a successful operation. |
| PM revocation | [Cancellation controls](cancellation/README.md) use a fixed generation-tagged record and the original PM event timestamp. Cancellation of actual source wait bodies and conditional lock acquisition is distinct from completed hardware cleanup. The PowerLifetime gate remains closed. |
| Kernel stack | The compiler records source/object-bound stack usage and direct machine-code edges. Unresolved indirect dispatch, recursion, dynamic frames and external depth remain unknown, not zero. Aggregate entry bounds still require proof. No heap stack switch is used. |
| Target kernel | The supplied report identifies macOS 26.7.1, build 25G241, Darwin 25.6.0. Public SDK compilation and inherited-class ancestry do not establish actual target export/vtable resolution. No private report identifiers are required in this repository. |
| Final validation | The development workflow now retains stack measurements and exercises isolated prospective error paths. New source changes require a fresh native Intel macOS run, followed by evidence tied to that exact source/artifact. |

Source-body controls execute actual extracted original functions with explicit
dependency fixtures; they do not execute a GPU or establish kernel runtime
success. Cross compilation is reported separately from native Apple compiler
validation. No candidate ZIP is produced while admission remains unresolved.
