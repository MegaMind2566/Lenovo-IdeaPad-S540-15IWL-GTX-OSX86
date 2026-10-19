# Isolated unavailable OS-event feature policy

This candidate adds four explicit feature guards to three exact frozen V3 original translation units. It implements no `nv_get_ctl_state`, event delivery or file-private callback, and changes no production source selection or default.

| Entry | Selected policy |
| --- | --- |
| EventApi constructor, `NV01_EVENT_OS_EVENT` | Return `NV_ERR_NOT_SUPPORTED` before lookup, notification initialization, conversion or registration |
| EventBuffer constructor, public `notificationHandle != 0` | Return `NV_ERR_NOT_SUPPORTED` before output changes, backing allocation, mapping or OS handle conversion |
| Semaphore-surface register/unregister, user notification handle | Keep original index validation, then return `NV_ERR_NOT_SUPPORTED` before conversion or waiter changes |

The policy leaves kernel callbacks and semaphore waiters available. EventBuffer handle zero remains valid, including the real operational-event importer: it creates a host `NV01_EVENT_KERNEL_CALLBACK_EX`, and its physical GSP buffer uses handle zero plus a separate `bClientRM` listener/alias. The importer source stays byte-identical.

`S540_NVIDIA_NO_OS_EVENT_BACKEND=1` is mandatory for these isolated source units. The backend cannot migrate an existing OS-event registry or retain a user notification from a different configuration. This policy does not infer hardware absence, suppress required kernel callbacks, or permit an ignored failure to establish successful notification delivery.

The CPU controls execute complete baseline/proposed original constructor/control bodies. They exercise real fixture allocations and reference counts, early refusal, preserved caller state, baseline acquisition counterexamples, kernel/zero-handle paths and allocation/mapping failure cleanup. Private NVOC/resource types and memory helpers are explicit fixtures; the independent six full-TU Mach-O compiles use real original private headers, namespace and frozen V3 types.

The guard runs inside a constructor. Generic NVOC object allocation and base construction can precede it; the original generated factory unwinds base construction and frees its object on constructor failure. The candidate prevents subsequent OS notification and backing-resource acquisition. It does not claim zero allocation before generic object creation or prove the entire original factory/resource lifetime through the CPU fixture.

```sh
python3 packages/nvidia-gsp-bootstrap/prospective-os-event-policy/check_event_policy.py \
  --output "$OUTPUT/prospective-os-event-policy" \
  --upstream "$UPSTREAM" --namespace "$NAMESPACE" \
  --v3-output "$OUTPUT/prospective-combined-v3"
```

Use `--host-control` only for explicit Linux development checks. This command neither loads a module nor accesses a GPU. Its source composition is a separate successor candidate to V3. The existing callback ledger stays unresolved until actual composed-source and final-root/type/dispatch seals pass; these guards alone do not prove whole-bootstrap event exclusion, stack safety, target loader admission or readiness for a Lenovo test.
