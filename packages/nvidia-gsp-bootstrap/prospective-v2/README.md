# Isolated prospective combined profile v2

V2 preserves v1 and the approved ten-patch defaults. It adds three memory-unwind
fixes, per-bootstrap invalidation of an old GSP stop marker, optional-log
cancellation, and timer cancellation status propagation. The updated cancellation
C/header are built only in an isolated project overlay. No receipt issuer or
adapter entry is enabled.

The helper verifies pinned raw sources, every standalone patch and generator,
the exact v1 reconstruction, and all strong project/fixture inputs. Two inserts
at raw `kernel_gsp.c` line 24 retain both exact headers in declared order:
`Original.h` then `Cancellation.h`. Every other overlap is refused. Both complete
combined patches are regenerated and replayed exactly, without fuzz or searching
for shifted context.

After preparing the verified ten-patch source and baseline namespace, run:

```sh
python3 packages/nvidia-gsp-bootstrap/prospective-v2/check_combined_profile.py \
  --repo . --upstream build-src/nvidia-upstream \
  --checked-source build/nvidia-execution/original-rm/checked-source \
  --namespace build/nvidia-execution/original-rm/original/contract/S540GlobalRmNamespace.h \
  --cc /usr/bin/clang \
  --output build/nvidia-execution/prospective-checks/combined-profile-v2
python3 packages/nvidia-gsp-bootstrap/prospective-v2/check_body_controls.py \
  --upstream build-src/nvidia-upstream \
  --namespace build/nvidia-execution/original-rm/original/contract/S540GlobalRmNamespace.h \
  --output build/nvidia-execution/prospective-checks/v2-bodies
```

Compilation requires Intel macOS by default. Use `--cross-probe` explicitly for
separate cross-compilation. Body controls run in native user space; an explicit
`--host-control --cc … --cxx …` labels a non-Apple control. Outputs must be fresh.
The fixtures regenerate complete original bodies from hashes and patches; no
source tree or executable is stored in this directory.

Local Clang18 cross-validation compiled **25 changed original C units plus two
strong project C bridges**, with `-Werror` and a 4096-byte individual-frame limit.
It does not rebuild the shared-header fanout through all 1100 units or establish
a complete call-chain stack bound. The separate plain and fatal sanitizer source-body controls
cover epoch 90, optional logs 37, timers 49 and memory 127 with explicit dependencies.

Timer void wrappers, event-destroy ownership and backend callback completion
remain unresolved. These controls do not establish target KXLD compatibility,
PM acknowledgement, DMA quiescence or successful GSP initialization. No kernel
or GPU code was executed and no package is approved. Callback operations that
remain unavailable continue to refuse; these patches do not implement peer/SVA
or imported-memory services.

`PROSPECTIVE-SOURCE-PROFILE.json` freezes 68 project and fixture inputs.
`CROSS-COMPILE-VALIDATION.json`, `COMPILE-DEPENDENCIES.json` and
`BODY-CONTROL-VALIDATION.json` record the separate local cross-compile and
CPU-control results; their native Apple flags remain false. The body controls
use complete extracted source bodies and explicit modeled dependencies.
