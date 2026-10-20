# Retained failed global construction — reconstructed October 20

This additive source profile returns the actual `sysConstruct_IMPL` allocation
error before cleanup needs another TLS allocation. It retains the partial
`OBJSYS`, its ancestors, child objects and native backing until reboot. The
existing kernel global-entry gate remains closed.

The scratch loss removed the earlier uncommitted implementation and controls.
These are newly reconstructed sources and fresh validation; no historical
uncommitted freeze, binary or test result is used.

`prepare.py` exports `project_transforms(values)` for the strong record/header,
and `original_transforms(values)` for complete `system.c` and
`g_system_nvoc.c`. Apply after retained diagnostic, retained backends and global
epoch. Original source inputs are pinned by SHA. No new TU or macro is needed.
The three record APIs remain project exports. The typed actual failure-boundary
probe `s540FirstTxnGlobalOriginalSystemFailure` is a strong project endpoint in
original `system.c`; do not rename it into the private original namespace.

Capture requires the actual ordinary master, immutable owner/generation, genuine
IN_CORE epoch and the typed original failure boundary. The two generated guards
precede every ancestor destructor, unlink, in-place zeroing and physical release.
Heap object-create failure still returns NULL and the original status; in-place
construction retains the caller's original storage and pointer.

Fresh controls passed on Linux x86_64 ELF, plain and ASan/UBSan/function variants:
10 returned epoch cases plus allocation 154 and post-core TLS 155/156, 207 assertions
per variant. Allocation 154 returns 81 with both complete ancestor guards observed
and every `OBJSYS` byte unchanged. Allocations 155/156 preserve original-core status 0
separately from sticky 81. All outcomes retain Host backing and refuse shutdown.
The full 1..156 fault matrix remains unfinished; this profile does not close it.

The clean plain run reused 1099 newly compiled original objects only after exact
source, normalized command, object and actual compiler-dependency checks. It
freshly compiled the identification TU and 52 project TUs. The sanitized run
freshly compiled 1100 original and 52 project TUs. Three complete C TUs also pass
a separate non-Apple Mach-O kernel-type cross probe. None of these results is
Apple runtime, kernel, hardware, final-image or entry-admission evidence.

The first CPU run failed when its executable unexpectedly became an empty,
non-executable replacement after case 6. No runner basename collision was found;
container ptrace was unavailable, and the external replacement cause remains
unresolved. Its failed report is retained. A clean relink/rerun passed with
executable hash/mode checks around every process. The first failure has not been
relabeled as a successful test.

`evidence/*compilation.json.gz` stores the exact compiler manifests with shared
actual dependency identities to avoid repeated headers. Each envelope includes
the original manifest SHA and JSON format. Replace each row's `dependency_ids`
with a `dependency_sha256` map from the envelope's dependency table, then encode
with indent 2, sorted keys and a trailing newline to recover the original bytes.
Every such decode was compared byte-for-byte before saving. Test reports record
the metadata as it stood during execution; implementation and control source
hashes remain unchanged, while this README, status and contract validation fields
were finalized after the run.

`replay_v3_project.py` replays the exact 28-file V3 companion source inventory
`ec8108f5…`; its output explicitly declares source-only and compiled=false. It
requires the existing freshly verified 4005-file V3 source tree `fa8498c3…` beside
it. It never fabricates the V3 checker’s compiled audit.
