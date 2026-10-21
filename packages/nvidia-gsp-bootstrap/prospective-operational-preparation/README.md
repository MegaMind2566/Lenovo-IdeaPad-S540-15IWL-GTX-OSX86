# Local operational preparation checkpoint

This source-only checkpoint combines the global RM result correction, concrete
Context/Session interrupt installation, bounded callback dispatch and retained
global allocator work. It extends the frozen integrated preparation at commit
`f08010b02dbcd9c29951794ba170d921d07ffea2`; that checkpoint and the successful
idle-loader target test remain historical evidence with their original scope.

`LOCAL-PREPARATION-STATUS.json` binds the selected composition, local compiler
reports and component receipts. Component documentation states which actual
bodies run and which platform endpoints are fixtures. Linux CPU execution and
SDK Mach-O crosscompilation do not establish target kernel execution.

## Changes

- Public RM startup status agrees with the actual return value, including
  retained out-of-memory failures after construction.
- An explicit retained Owner/Session bridge reaches the genuine Context ISR
  and bottom-half wrappers, derives MSI mode from the backend and keeps stop
  refusal monotonic. Startup does not invoke this diagnostic installation.
- Callback dispatch reports real arm/lock/cancellation failures and preserves
  outstanding work when callbacks mutate the registration list.
- The two global allocator identities use their original concrete allocation
  and free implementations. Initialization is bound to the retained global
  epoch; the outer runtime remains retained. Private tracking construction
  preserves the original lock order, and public reserved-storage aliases
  refuse before mutation. Generic dynamic allocator calls
  and their context-sensitive stack closure remain separate obligations.

## Reproduce the source composition

With the authenticated canonical and integrated parent directories available:

```sh
python3 -B builders/prepare_nvidia_operational_successor.py \
  --canonical-parent build/integrated-inputs/compose-check-public \
  --base build/integrated-successor-5 \
  --output build/operational-local-replay \
  --profile global-result --profile irq-installation \
  --profile rc-dispatch --profile allocator-stack
```

The operational compiler accepts the resulting composition and requires the
pinned NVIDIA tree, kernel SDK and explicit compiler paths. It freshly compiles
the project units and, with `--compile-changed-original`, the changed original
C subset. It does not perform the complete original build, final link, package
creation or target loading. New original exports require that subset check.

## Remaining admission requirements

The global and loader entry refusals remain closed. Aggregate kernel stack
bounds and actual execution capacity, callback/PM shutdown duration, original
cleanup authority, hardware DMA stop and the runtime coordinator remain
unproved. The DMA containment draft is explicitly unselectable: an original
BAR0 register writer can bypass a guard on PCI configuration writes.

This checkpoint is not an installation package. No new GPU initialization,
acceleration, firmware execution, physical reclamation or security change is
claimed. No paid GitHub build is requested; intermediate source commits use
`[skip ci]`. Native artifact reuse still requires the exact compiler, SDK,
command and full dependency bindings specified by `AGENTS.md`.
