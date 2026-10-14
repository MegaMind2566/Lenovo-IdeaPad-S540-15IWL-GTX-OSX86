# NVIDIA PCI inventory

This is the first runtime inventory for the GTX 1650 Max-Q port. It reads metadata already published by macOS through userspace IOKit. It does not initialize the GPU or provide graphics acceleration.

Use the compiled **S540-nvidia-pci-v1.zip**, extracted into Downloads:

```sh
bash "$HOME/Downloads/S540-nvidia-pci-v1/CHECK-NVIDIA.command"
```

No administrator password or developer tools are required. The native Intel executable is included. The launcher checks its hash and signature, displays the JSON result and saves `nvidia-pci.json` in a new private `NVIDIA-PCI.*` folder on the Desktop. Share that JSON to choose the next port milestone.

## What the result means

| Status | Meaning |
|---|---|
| `found` | The exact `10DE:1F91` device is present in the active IOService registry |
| `device_tree_only` | The exact device remains in the Device Tree, while no active PCI service was found |
| `not_visible` | Neither inspected registry plane exposed the exact device; this is not proof of electrical power-off |
| `error` | Enumeration or selected metadata was incomplete; retain the report |

The current `-wegnoegpu` flag can terminate the external GPU's IOService node. The report records only whether that exact boot-argument token is present, never the full boot arguments. Device Tree fallback helps retain identity information when the service is hidden.

The report includes the matched GPU's PCI IDs and registry path, limited parent-bridge identity and bounded raw `reg`/`assigned-addresses` properties when published. Those byte strings are metadata, not MMIO reads or measured VRAM capacity. Machine serials, account names, network details and unrelated devices are excluded.

The executable does not open a hardware user client, write PCI configuration, map registers, enable DMA, load firmware or call ACPI. The launcher only creates a new report folder. Keep the working EFI as it is for this inventory.

## Build and scope

The [builder](../../builders/build_nvidia_pci.py) compiles and signs a thin x86_64 executable using the native macOS SDK. CI runs the production decoding/encoding fixtures, a live read-only enumeration on its Intel runner and the packaged launcher without administrator access. A successful runner report does not establish laptop visibility.

Source files in this directory do not include the executable. Download the built ZIP from a successful **Build read-only NVIDIA PCI inventory** Actions run. The archive includes build provenance, per-file checksums and the launcher-bound executable hash.

See the [port assessment](../../docs/reference/nvidia-port-assessment.md) for later work on the Darwin transport, GSP startup and command execution. NVIDIA electrical power-off and external video output remain deferred.
