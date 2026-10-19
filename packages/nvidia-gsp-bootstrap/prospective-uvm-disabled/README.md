# Isolated disabled-UVM backend candidate

This directory implements the three exact pinned NVIDIA `!defined(NV_UVM_ENABLE)` branches. It is outside production source selection, changes no default and does not enable original RM entry.

The backend selection must explicitly set `S540_NVIDIA_NO_UVM_BACKEND=1`. Defining `NV_UVM_ENABLE`, including defining it to `0`, is rejected because NVIDIA's original branch tests whether it is defined. The selected backend has no UVM registration, queues, retained UVM handles or imported UVM driver callbacks. Enabling any of those requires replacing this candidate and reviewing their ownership.

| Callback | Original disabled branch |
| --- | --- |
| `nv_schedule_uvm_isr` | `void`; no UVM ISR is scheduled |
| `nv_schedule_uvm_drain_p2p` | `NV_ERR_NOT_SUPPORTED`; no P2P drain is performed |
| `nv_schedule_uvm_resume_p2p` | `void`; no UVM work is resumed |

The actual pinned header declares ISR and resume as `void`. A former audit concern about a status ABI does not apply to the verified source bytes. Original `knvlinkResiliencyUvmIdle_WORKITEM` explicitly handles `NV_ERR_NOT_SUPPORTED` as “UVM never installed this callback.” That interpretation relies on the real no-UVM backend configuration; it is not a successful drain of an enabled UVM service.

The isolated check compiles against the actual private namespace and original headers. It executes complete extracted original disabled bodies and four complete original forwarding bodies, including `gmcapiMmuFaultQueued`, with explicit CPU-side objects. It checks preserved state/UUID bytes, the exact status ABI, a genuine Mach-O kernel object with three definitions and no imports/initializers, and five invalid configuration compiles. The extracted notification function's original `NV_OK` acknowledges the no-UVM notification path; it does not establish delivery of a UVM interrupt.

```sh
python3 packages/nvidia-gsp-bootstrap/prospective-uvm-disabled/check_uvm_disabled.py \
  --output "$OUTPUT/prospective-disabled-uvm" \
  --upstream "$UPSTREAM" --namespace "$NAMESPACE"
```

Authoritative controls require Intel macOS. `--host-control` is an explicit Linux CPU/cross-compile development check. Neither mode loads a module, accesses a GPU, establishes target kernel admission or proves the remaining bootstrap prerequisites.
