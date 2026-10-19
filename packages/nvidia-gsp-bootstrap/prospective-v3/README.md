# Isolated prospective combined profile v3

V3 combines the frozen V2 source composition with the checked timer proposal.
It references the existing V2 and timer packages by exact hashes; their source
files, fixtures and contracts remain unchanged. Production compiler defaults
and the approved ten-patch profile remain unchanged.

The four timer patches replay sequentially against their pinned raw sources
and project inputs. The V2 timer-status predecessor is byte identical and is
replaced exactly once by the complete checked timer result. The timer additions
to `os.c` merge with V2's separate capabilities guard in original coordinates.
The complete raw-to-V3, ten-to-V3 and V2-to-V3 patches then replay exactly.

The actual TimerOriginal bridge retains six privately namespaced original
callbacks and six strong project exports. The two new checked project exports
return cancellation/destruction status to the original OS callbacks. The
original timer helpers remain local functions. No generated refusal or test
backend substitutes for these definitions.

Run the existing 483 CPU controls, then compile the combined profile after V2:

```sh
python3 packages/nvidia-gsp-bootstrap/prospective-timer-checked/check_timer_checked.py \
  --upstream build-src/nvidia-upstream \
  --namespace build/nvidia-execution/original-rm/original/contract/S540GlobalRmNamespace.h \
  --output build/nvidia-execution/prospective-checks/timer-checked
python3 packages/nvidia-gsp-bootstrap/prospective-v3/check_combined_profile.py \
  --repo . --upstream build-src/nvidia-upstream \
  --checked-source build/nvidia-execution/original-rm/checked-source \
  --v2-output build/nvidia-execution/prospective-checks/combined-profile-v2 \
  --namespace build/nvidia-execution/original-rm/original/contract/S540GlobalRmNamespace.h \
  --cc /usr/bin/clang --cxx /usr/bin/clang++ \
  --kernel-sdk build-src/MacKernelSDK \
  --timer-control-report build/nvidia-execution/prospective-checks/timer-checked/timer-checked-controls.json \
  --output build/nvidia-execution/prospective-checks/combined-profile-v3
```

The default requires Intel macOS. The SDK must match the pinned Git commit and
every tracked blob. `--cross-probe` labels a separate cross-compilation; the
optional `--sdk-archive` checks the exact local pinned archive instead of Git.
Both output directories must be fresh. No full source tree or executable is
stored in this package.

Local Clang 18 validation compiled all **25 changed original C units, three
strong project C bridges and the real Darwin timer C++ backend with SDK
headers**, with warnings as errors and an individual 4096-byte frame check.
Separate timer CPU controls passed 483 checks in each plain and fatal sanitizer
variant. The unmodified baselines fail 4, 165 and 10 checks in the three relevant
groups; the existing public void ABI has 34 successful controls.

These are separate compilation and CPU-body results. They do not rebuild all
1100 units affected by shared headers or establish a complete call-chain stack
bound. Accepted RM work can still borrow timer events after the direct callback
returns, and outer void destructors still require ownership integration. This
profile provides no target KXLD proof, aggregate PM deadline, DMA-stop receipt,
GPU execution, original-entry admission or package approval.
