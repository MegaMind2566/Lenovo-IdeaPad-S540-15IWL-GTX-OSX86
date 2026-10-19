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
