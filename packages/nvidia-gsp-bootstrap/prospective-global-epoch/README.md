# Serialized retained global epoch

This successor changes exactly the strong first-transaction record/header and
`S540NvidiaGlobalRmLifecycle.c`. It supplies a concrete one-shot owner protocol
for actual `coreInitializeRm` while preserving the production `KERNEL` refusal.
It requires the retained diagnostic Host and retained Darwin backend successor.

`MasterIdentity` pulls the real current ordinary master, immutable owner and
generation from the strong record before device `nv` attachment. Accepted work
threads cannot substitute for that master. It preserves output on refusal and
returns a genuine master's first sticky error. `GlobalEnter` claims a permanent
one-shot construction state. Separate source hooks record the actual original
return, pre-core refusal and post-core validation, without replacing the original
status with a later refusal. No state can reset or repeat original construction.

After the true original return succeeds, the lifecycle checks the actual system,
all 15 original children, resource server/client, Host state and crypto counters.
Only then does it read genuine current-thread API, per-GPU and allocation-lock
ownership through the sealed original probes. The basic-lock model and explicit
no-legacy-RM-semaphore source profile remain mandatory. The normal lock observer
requires completed globals, so this construction boundary uses the same real
probes directly after verifying their source-backed prerequisites. No assertion
that an arbitrary lock query is safe before construction is introduced.

This selected lifecycle has no original global shutdown import and no transition
to physical release. Its shutdown API only reports that cleanup did not occur;
real global objects, CPU fields and backend allocations stay retained. An
initialized flag describes completed original globals, never hardware admission.

The full CPU controls pass ten separate process scenarios, 138 assertions per
variant, both plain and fatal address/undefined/function sanitizers. They execute
all 1,098 actual original units plus the declared CR4 fixture and deterministic
version unit, and compile 54 actual project units. Cases include unbound and
foreign-thread rejection, duplicate before/after return, real first and second
Host allocation failures, real service refusal, preserving a preexisting portable
runtime, actual post-core API ownership, and allocation-only ownership with zero
per-GPU mask. Complete uninstrumented record and lifecycle TUs also cross-compile
as x86_64 Mach-O with the composed Darwin SDK plan. This is Linux-hosted evidence.
The final repeated controls reuse the byte-identical original objects from the
full compile, with exact command/source/object and companion-inventory checks;
all project objects and harnesses are recompiled. No native Apple run is claimed.

**Known blocker:** actual late allocation failure at ordinal 154 can leave the
original constructor inside an endless resource-client cleanup retry. The check
captures this separately as a blocked negative in both variants. It never counts
a timeout as successful original return or allocation-failure closure. Source
trace: `sysConstruct_IMPL` failure -> `rmapiShutdown` -> `serverFreeDomain` ->
`serverFreeResourceTree` -> `rmapiLockAcquire` -> refused TLS allocation.
`serverFreeDomain` ignores the failed client-free status and retries the same
list head. The production global gate remains closed. A separate exact source
successor must retain failed construction before this destructive cleanup and
guard the corresponding generated NVOC ancestor cleanup sites.

`prepare.py transforms(values)` composes three exact source replacements after
retained-backends. It adds no TU or compile definition. The public exports live
in the existing strong record: `s540FirstTxnMasterIdentity` and the six
`s540FirstTxnGlobal*` functions declared by `global-api.h.inc`.

Reproduce with `check.py --upstream ... --composition ... --output ... --cc ...
--cxx ... --host-control --jobs 6`. Optional `--reuse-originals` accepts only an
unchanged composed source/compiler profile and byte-identical objects/commands
with identical companion files except the two implementation C files.
`check_kernel.py --composition ... --output ...` compiles the uninstrumented TUs.
