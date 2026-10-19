# Isolated original shutdown protocol

This successor exposes the frozen, actual `gpuEnterShutdown_IMPL` function for a
future one-shot diagnostic that keeps the driver and its allocations loaded until
reboot. The original function calls `gpuStateUnload(FAST_UNLOAD)` followed by
`kgspUnloadRm(NORMAL, FAST_UNLOAD)`. It does not call `gpuStateDestroy`.

The typed bridge first pulls the genuine first-transaction record. It checks the
exact owner/generation and ordinary master thread before dereferencing the `nv`
identity, then preserves the real private state and `OBJGPU` identities. It checks
the genuine full lock-capability predicate, permanently claims one attempt,
enters the real cancellation cleanup scope, and acquires its own original
write-API/GPU tokens in their original order. It rechecks identity and record
state under those tokens before calling the actual original entry. Any failed
claimed operation is recorded before later token release can dispatch work.
Original return, later unlock/service failure and outer operation status remain
separate observations. A partial attempt cannot be retried.

The only success observation is that this exact original protocol function
returned `NV_OK`. It is not a claim that every GPU engine or posted PCIe write
stopped. It is not a DMA-stop receipt or permission to reclaim memory. There is
no receipt verifier, transport drain, context destruction, final owner release,
power acknowledgement or module unload here. No existing entry/admission gate
or production profile changes. The current full lock predicate still refuses
the unresolved RM-semaphore ownership capability.

`SOURCE-CONTRACT.json` pins the original upstream commit, the required complete
first-transaction source contract, the complete guarded GPU source and the exact
original function body. `SourceProfile.h` embeds its immutable digest into every
observation. The runner verifies the full V3 inventory and candidate reconstruction
before extracting the complete body without rewriting it. It also compiles the
complete original GPU translation unit and the complete typed bridge using the
original make-declared types and flags, verifies their real namespaced symbol
connection, and checks compiler-observed header dependencies again after execution.

Run the checks with explicit inputs:

```sh
python3 packages/nvidia-gsp-bootstrap/prospective-shutdown-protocol/check.py \
  --upstream /path/to/pinned-open-gpu-kernel-modules \
  --namespace /path/to/generated/S540GlobalRmNamespace.h \
  --v3-root /path/to/verified-materialized-v3 \
  --output /path/to/fresh-shutdown-controls \
  --cc /usr/bin/clang --cxx /usr/bin/clang++
```

Default execution requires Intel macOS and Apple Clang. `--host-control` explicitly
selects Linux CPU controls and Mach-O cross-compilation; it additionally requires
the pinned SDK (`--sdk`, plus `--sdk-archive` for an archive extraction). A supplied
V3 input may be omitted to reconstruct the same frozen inventory. All generated
files go to the output directory; repository output is permitted only under
`build/`. Output must remain separate from every source/SDK input.

Controls execute the exact original shutdown body and unmodified successor bridge
with actual NVIDIA layouts. The hardware/engine transition and GSP shutdown
endpoints, first-transaction record, full lock predicate, cancellation, thread,
runtime and API/GPU-token endpoints are explicit fixtures. They are not actual
kernel locks, a native first-record integration or hardware execution. Cases cover
foreign identities, owner/generation/private-GPU changes, source engine/GSP failure,
lock/cancellation failure, sticky-error publication before unlock, and replay.
Address, undefined-behavior and function-type sanitizers are fatal. LeakSanitizer
is disabled because the hosted environment cannot inspect `/proc/task`; these
fixtures allocate no heap.

Before the retained diagnostic can use this bridge, its outer owner must integrate
real callback/IRQ closure, cancellation and lock capabilities, unconditional
transaction backing retention, source/worker stack bounds and target kernel
linkage. The entire coordinator/context/session/text and retained memory must
remain alive after every claimed attempt. This isolated successor does not prove
those prerequisites, alter source destructor ordering or make normal unload safe.
