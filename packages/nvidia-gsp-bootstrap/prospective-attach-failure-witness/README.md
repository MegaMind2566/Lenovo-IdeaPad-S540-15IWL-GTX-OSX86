# Attach and constructor failure witness

The B7 target reports `firstSite=2`, the generic retained root site. Its
`(0x22:0x56:954)` tuple means that `gpumgrAttachGpu` returned 86; it does not
identify the constructor or prove that an allocation ran. This profile adds
scalar evidence at the actual attach and child-constructor boundaries.

The exact B7 `gpu.c` and `gpu_mgr.c` inputs are SHA-256 pinned. Their existing
calls, return values, retained child slots, deferred-cleanup requests, GPU
visibility restoration and optional-engine refusal remain intact. In
particular, the retained profile still returns an unsupported constructor's
error. This observer does not make an optional engine successful or remove it.

A private 80-byte snapshot records the current generation, last attach and
constructor progress, and the first actual failure's class ID, instance
ordinal, stage and raw status. Later outer attach failures cannot replace the
first child failure. A missing-engine observation is valid only after the
original property read; GSP-client mode is read from the existing CPU field
using the pinned generated macro and selected feature value. Neither field
adds a hardware read. An engine constructor's raw error is captured before a
later missing-engine check could replace its original return status.

Generic GPU code passes the existing null-safe `pOsGpuInfo` field to the
observer. The pinned Unix `NV_GET_NV_STATE` definition establishes that this
is the real OS identity; that platform macro is deliberately not required or
mocked in the generic GPU translation unit. CPU cases cover a null or foreign
OS field, and a mutation that forges the observer identity is rejected.

The fixed witness is reserved once per boot by the actual ordinary master of
the current exact `nv` and generation. Pure record snapshots provide these
diagnostic checks, including after a sticky first error. No identity API that
can change FirstTxn status is used. Foreign/IRQ callers, changed generations,
wrong `nv` values and repeated begins cannot overwrite a prior witness.
There are no retained pointers, dynamic allocations, locks, new KPI imports or
deep logging calls.

`complete` records that an attach exit path was reached, including failure.
The getter independently requires the original wrapper's actual returned
observation before it exposes the snapshot, and leaves output untouched on
refusal. The outer Context logger consumes the scalar getter only after that
wrapper has unwound. No userspace wire layout or hardware-admission policy is
expanded by this profile.

CPU controls compile the actual transformed `gpuCreateObject` and
`gpumgrAttachGpu` bodies plus the separate production witness TU. Explicit
NVOC, GPU and runtime endpoints cover construction stages, retained slots,
visibility restoration, sticky errors, unavailable observations and stale or
foreign callers. They do not execute IOKit, original whole-driver construction
or a GPU. Fatal ASan/UBSan and runtime-rejected source mutants are required.
Final native symbol/stack checks and the next physical Lenovo test remain
separate requirements.
