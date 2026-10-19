# Prospective GSP teardown status retention

`gsp-teardown-status-prospective.patch` is an isolated four-file patch against
NVIDIA commit `1a82fbfda8f321b056eb3568850f9316c5e465c5`. It is not included in
the frozen ten-patch profile and does not admit an original hardware entry.

The existing exported signatures are unchanged. The statusful checked adapter
must treat every non-`NV_OK` result as partial cleanup and quarantine the retained
context, GPU, backing allocations, mappings and register access. It must not
retry a destructive partial stage or acknowledge PM based on its return alone.

## Changes

- `kgspUnloadRm_IMPL` returns the first suspend-RPC, processor-suspend or teardown
  failure before entering later stages. `bGspRmUnloaded` is published only after
  processor suspend and teardown both return `NV_OK`. A completed unload is
  idempotent. The separate force-unload bit is rejected as proof: its actual
  setter in `subdevice_ctrl_gpu_kernel.c:688` also runs after unload failure.
- `kgspTeardown_TU102` returns reset, FWSEC preparation and FWSEC execution
  failures instead of asserting and replacing them with the Booter result.
  `NV_ERR_GPU_IN_FULLCHIP_RESET` remains an error, not completed quiescence.
- `kgspExecuteBooterUnloadIfNeeded_TU102` checks the SEC2 reset status before
  executing Booter ucode.
- `gpuStatePreUnload`, `gpuStateUnload_IMPL` and `gpuStatePostUnload` return the
  first failed engine transition. Post-unload and P2P errors also propagate;
  loaded-state publication and subsequent destruction are stopped on failure.
- `gpuEnterShutdown_IMPL` preserves an earlier unload error. In
  `gpuStateDestroy_IMPL`, a failed late GSP unload returns before final internal
  objects, falcon/video lists and access maps are freed. The initialized-state
  transition is published after that checked GSP stage.

The patch preserves the original engine ordering. Earlier successful or void
stages may already have changed state when a later error occurs. Fail-fast
propagation does not roll them back or make them safe to repeat.

## Executed evidence

`check_gsp_teardown_status.py` verifies full source SHA-256 values, copies only
the four original source files, checks and applies the candidate to those copies,
and extracts eight complete original function bodies without rewriting them.
The compiled harness supplies explicit fixtures only at external stage boundaries.
It tests the actual function control flow and state publication, not a model
implementation of the patch.

The candidate passes **38 assertions** in both plain and fatal
ASan/UBSan/function-sanitized Clang 18 runs. The same assertions on the unpatched
original bodies expose **25 failures** in each variant. Scenarios include healthy
normal and GC6 paths, each GSP failure boundary, the force-unload flag, engine
pre/unload/post failures, P2P failure, shutdown error precedence and final resource
retention. An explicit assertion observes that the original void engine-destroy
stages already ran before the late GSP failure; this gap is not hidden.

This harness does not establish original-header ABI closure, full translation
unit compilation, kernel execution, hardware quiescence or a PM deadline.

```sh
python3 packages/nvidia-gsp-bootstrap/cancellation/check_gsp_teardown_status.py \
  --upstream /path/to/pinned/open-gpu-kernel-modules \
  --output /path/to/check-output \
  --cxx /path/to/clang++-18
```

## Remaining ownership boundary

TU117 uses `gpuGetChildrenOrder_GM200`, selected in `g_gpu_nvoc.c:1692`.
`gpuChildOrderList_GM200` in `kern_gpu_gm107.c:507` is reversed for unload and
destroy. The original `gpuStateDestroy_IMPL` runs these engine-destroy callbacks
before its late `kgspUnloadRm` call. Examples requiring further ownership proof:

| Original callback | Actual incomplete error/lifetime boundary |
|---|---|
| `kfifoStateDestroy_IMPL`, `kernel_fifo_init.c:240` | Frees graphics context descriptors; subsequent channel unmap/set operations are only asserted. The callback returns `void`. |
| `kbusStateDestroy_GM107`, `kern_bus_gm107.c:3946` | Discards BAR2 destruction status, can unmap a BAR0 window and frees the fake sparse descriptor. The callback returns `void`. |
| `kgmmuStateDestroy_IMPL`, `kern_gmmu.c:414` | Frees WAR page-table/directory descriptors and discards fault-buffer destruction status. The callback returns `void`. |
| `ksec2StateDestroy_IMPL`, `kernel_sec2.c:594` | Invokes boot-state cleanup through a `void` boundary. |

Moving GSP suspend ahead of these callbacks is not justified by this patch:
engine cleanup may require live GSP-backed frees. Conversely, successful IRQ
drain does not prove that the GSP processor or DMA engines stopped. Physical
retirement of deferred backing must therefore require separate hardware-domain
quiescence evidence, or retain all implicated backing through successful GSP
shutdown. Draining deferred allocations immediately after IRQ stop and before
GSP shutdown would leave this gap open.

No full cleanup, safe DMA retirement, callout producer closure, cancellation
deadline or laptop-test readiness is claimed.
