# Stack, producer and revocation source checkpoint

This child extends commit `944ee1c2b901b2078b742590b8babf227a1de278` with three
isolated source profiles. `LOCAL-PREPARATION-STATUS.json` binds their exact
composition, compilation reports, component controls and remaining limits.
The previous checkpoint and successful idle-loader target test retain their
original scope. Neither is rerun as routine coverage.

## Source changes

- Stack context: the unchanged original allocator algorithms move into private
  inline bodies. The three measured global paths reach concrete callees while
  the public generic ABI, dynamic allocator fallback and real OOM callbacks
  remain. The nonpaged immediate frame grows from 8 to 24 bytes; that change
  requires a fresh caller budget and does not establish an aggregate bound.
- Revocation: a genuine cancellation control-word reservation orders timer,
  IRQ and TX acceptance against cancellation publication. It remains pending
  until the real endpoint returns. Failed retirement retains the obligation;
  an IRQ retirement failure also closes software ingress while preserving the
  actual enable/mask obligations. Cleanup uses the existing fixed deadline.
- DMA producer paths: the same reservation surrounds reviewed BME-enable
  writes through the two GM107 configuration writers and the bound Session.
  A separate retained-master observer can authorize the narrowly reviewed
  failed-initialization IRQ mask. It preserves the first error and grants no
  original-entry or general device-access authority.

## Local evidence and reproduction

Controls execute actual original bodies and shared protocol implementations.
Each receipt distinguishes real code from platform, clock, hardware endpoint
and privileged-CPU fixtures. SDK Mach-O crosscompilation on Linux is separate
from Apple native compilation and target execution.

```sh
python3 -B builders/prepare_nvidia_shutdown_successor.py \
  --canonical-parent build/integrated-inputs/compose-check-public \
  --integrated-base build/integrated-successor-5 \
  --base build/operational-successor-2 \
  --output build/shutdown-local-replay \
  --profile stack-context --profile pm-revocation --profile dma-producer
```

The new compiler takes the same ancestor paths, the resulting `--composition`,
pinned `--upstream` and `--kernel-sdk`, explicit `--cc`/`--cxx`, and
`--compile-changed-original`. It checks fresh project objects and only the
child's changed original C subset. It does not rebuild the full original
profile, link a kext, create an installation package or authorize target use.

## Open admission requirements

The global lifecycle, loader state and Bootstrap source are byte-identical to
the parent. All runtime, hardware, stack-capacity, physical-release and PM
admission gates stay closed.

The shared CAS does not make the earlier PM callback event atomic with commit
acceptance. The event-boundary control deliberately exercises delayed hooks,
including an already exhausted budget, while preserving the earlier deadline.
Endpoint and arbitrary callback duration, firmware activity, all CPU/MMIO
producers and posted-write drain remain unproved. BME-off and zero pending
transactions alone cannot issue a DMA-stop receipt.

The cleanup-mask observer covers sticky `RETAINED` only. General clean
`CLOSING` cleanup still requires a separately checked authority. Original stack
graphs, actual target capacity and framework/reentry headroom also remain open.

No paid GitHub build is requested. Source checkpoints use `[skip ci]`; native
artifact reuse still requires the exact compiler, SDK, command and full
dependency bindings in `AGENTS.md`. This is not an installation package.
