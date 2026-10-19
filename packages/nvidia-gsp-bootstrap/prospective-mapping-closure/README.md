# Retained image user-mapping state

This isolated source candidate supplies the five exact NVIDIA mmap callbacks
used by `dynamic-power.c`. It has a real Darwin mutex, immutable exact-nv /
owner / transaction-generation binding, real OS thread ownership, and actual
`allRevoked`, `safeToMmap`, and wakeup-needed state. It has no reset, destroy,
replacement, caller-supplied generation, or user-mapping registration entry.
The created mutex remains retained with the attempt.

The selected loader has a snapshot/request IOUserClient. It supplies no memory
mapping override or alternate legacy method table. `profile_guard.py` binds its
exact header and implementation to `SOURCE-CONTRACT.json`. The official pinned
Apple `IOUserClient::clientMemoryForType` returns `kIOReturnUnsupported`; the
inherited `mapClientMemory64` only maps after successful descriptor lookup.
Thus the admitted user GPU-mapping set is empty for this specific image. The
backend's revoke operation sets the corresponding state under its actual
mutex. The initial state is false, matching the zero-initialized original Linux
state; an empty set does not automatically fabricate the initial receipt.

This scope says nothing about kernel BAR IOMemoryMap objects, DMA descriptors,
GPU shutdown, or bus mastering. It authorizes no hardware stop or reclamation.
The normal GPU driver/user mapping frontend is not implemented here.

Each backend compilation requires `-DS540_NVIDIA_NO_USER_MAPPINGS=1` and rejects
**any** definition of `NV_UVM_ENABLE` or `NV_PM_RUNTIME_AVAILABLE`, including a
zero definition. The composer must run `profile_guard.validate_profile` against
the exact project root it compiles. A loader change requires a new ingress
review; this source profile cannot be reused merely by changing a hash.

`check.py` first replays the frozen GPU-binding parent's real strong record,
Host, cancellation, queues and timers. It then executes two complete pinned
original dynamic-power caller bodies with the genuine mapping implementation,
real transaction authorization and real mutex. GPU token/runtime/PM endpoints
are explicit CPU fixtures. Eleven fresh-process scenarios provide 30 checks
per plain and fatal ASan/UBSan/function variant, including actual callback
contention with the master, sticky refusal while the callback is blocked,
recursive/unlocked access, foreign nv/thread, and real allocation failure.
The backend and the complete original `dynamic-power.c` compile as x86-64
Mach-O against actual NVIDIA headers. Seven contradictory source profiles
must fail preprocessing. Kernel execution and GPU access remain untested.

Example (Intel macOS, explicit actual Apple compiler paths):

```sh
python3 packages/nvidia-gsp-bootstrap/prospective-mapping-closure/check.py \
  --upstream build-src/nvidia-upstream \
  --v3-root build/nvidia-execution/prospective-checks/combined-profile-v3 \
  --namespace build/nvidia-execution/prospective-checks/combined-profile-v3/prospective-private-namespace.h \
  --cc /usr/bin/clang --cxx /usr/bin/clang++ \
  --output build/nvidia-execution/mapping-closure
```

Linux CPU controls require `--host-control`. Fatal sanitizer controls disable
LeakSanitizer in the restricted Linux environment; the deliberate retained
objects have no release issuer in this candidate. The same tests retain ASan,
UBSan and function sanitizer enforcement. No production source is changed and
no original-entry admission is granted.
