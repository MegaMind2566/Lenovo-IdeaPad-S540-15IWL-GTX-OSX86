# Source-only staged loader prototype

This directory is excluded from the production source list. It contains no
installable bundle, original-entry implementation or policy override. It makes
the proposed single transaction concrete while keeping RM entry closed.

The real IOKit backend publishes a control service on **IOResources**, with one
administrator connection at a time. It never matches an NVIDIA PCI provider.
Module entry, constructors and control-service start perform CPU-side metadata,
lock and control-object work only. They do not prepare a provider, copy firmware,
join PM, register IRQ/DMA, dispatch an RM request or call original RM.

| Recorded state | Actual source of the observation | Meaning |
| --- | --- | --- |
| Module entered | Project module entry invoked after the loader's C++ initialization path | This callback occurred; it does not certify that the load command returned success. |
| Control started | The actual control start callback receives the framework's IOResources object | CPU-side control endpoint is available; no target-loader proof is invented. |
| Entry blocked | One authenticated request with the exact registry-entry generation | The sole request is consumed and the fixed policy returns `NV_ERR_NOT_READY`; original RM is never called. |
| Stopping/stopped | Actual service/client teardown and module-stop checks | New requests are denied. Live clients, services or class instances prevent module-stop completion. |

`targetLoaderAdmissionProven` remains zero. The request contains only format,
size and generation; it cannot carry privilege or admission flags. Opening a
connection requires Apple's administrator privilege check on the owning task.
Every external method repeats that check on `current_task()`, so transferring
a connection does not transfer root authorization. There are only snapshot and
one-shot request selectors; no memory mapping or RM user dispatcher is supplied.

The generation is the actual attached control object's `IORegistryEntry` ID.
Unauthorized, malformed and stale requests do not consume the request. After a
valid request, retries are refused permanently for that load instance. Closing
and stopping do not reset it. The request backend has no original-entry callback,
enable macro or externally supplied ready Boolean.

## Same image and module runtime

The root keeper takes each address through its actual original-header type.
Its 25 exact private RM roots match the reviewed compiled-bridge and gated
lifecycle baseline. Mach-O controls verify all 25 unsigned pointer relocations,
`N_NO_DEAD_STRIP`, and an empty loader table; the metadata helper only reads the
addresses. This is object evidence. A future final link must retain that keeper
and verify the same complete roots/imports in the **same final image**. Loading
a smaller probe does not validate omitted RM code or a later image.

The kernel backend's initializer/finalizer graph must match an independent SDK
reference for precisely the control and user-client metaclasses. Other source
objects must have no initializers. The shared kernel compiler profile suppresses
`__cxa_atexit` lowering. The module uses the pinned SDK's `libkmod.a` C wrappers,
whose actual objects reference `realmain`/`antimain` and the module's `kmod_info`.
It does not use the obsolete `libkmodc++` wrapper or its old
`OSRuntimeInitializeCPP(kmod_info_t *, void *)` ABI.

The [machine contract](LOADER-PROTOTYPE-CONTRACTS.json) pins source/API evidence
and keeps exact-target execution false. Its Apple source describes the reviewed
load/link → C++ registration → module start → personality matching order. It is
not represented as exact Darwin25.6/build25G241 source. Full target ABI semantics
and normal framework termination/unload serialization remain untested.

## Reproducible development controls

Run the isolated control on Intel macOS using the verified original namespace,
unchanged pinned original checkout and SDK checkout:

```sh
python3 packages/nvidia-gsp-bootstrap/prospective-loader/check_loader.py \
  --output-dir "$OUTPUT/prospective-loader" \
  --upstream "$UPSTREAM" --namespace "$NAMESPACE" --sdk "$KERNEL_SDK"
```

This executes 46 state controls in each plain/fatal ASan/UBSan/function variant,
six source-contract checks, real SDK Mach-O compilation, exact two-metaclass
codegen comparison, typed original-root relocation checks and the pinned C
module-runtime audit. On Intel macOS it also compiles the userspace IOKit control
tool, without executing it. No check loads a kext or accesses GPU hardware.

`--host-control` explicitly produces local Linux userspace and Mach-O cross
controls. An extracted local SDK archive has its reviewed input bytes checked,
but is not described as a verified Git checkout or native Apple execution.
Authoritative native controls require the pinned clean SDK Git checkout.

The prototype control tool only queries an already existing control endpoint
and can request its fixed refusal. It does not invoke a loader or prepare a PCI
device. It re-queries state after the refused request because a failed IOKit call
need not copy structure outputs. No Lenovo test command is supplied here.

## Remaining integration

A future single command may first obtain real supported target-loader success
for the same complete final image, verify that image/load instance is started
and idle, and then issue the privileged one-shot request. The kernel entry
validator must independently establish every actual callback/profile, stack,
PM/cancellation/deadline, status-preserving unwind and hardware-DMA stop condition.
A root request or loader success cannot replace those conditions. This prototype
has no setter that could enable entry after an external assertion; a real
reviewed transaction and validator are still required.

All original source overlays, production gates, build source lists and workflows
remain unchanged by this directory.
