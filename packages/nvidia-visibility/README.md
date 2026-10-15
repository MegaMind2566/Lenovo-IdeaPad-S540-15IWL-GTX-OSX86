# NVIDIA visibility boot experiment

**Superseded for this laptop:** PCI visibility is now confirmed after manual removal of `-wegnoegpu`. The latest inventory finds the active `10DE:1F91` PCI service with the argument absent. Repeating this preparation is not required for the reached milestone; see the [PCI result](../nvidia-pci/README.md#laptop-result-october-15-2026) and [transport plan](../../docs/reference/nvidia-port-assessment.md#current-implementation-milestone-bounded-pci-transport).

The V1 automatic locator stopped on the laptop because its required `Mounted` Boolean was missing or invalid in disk metadata. It stopped before creating a candidate or changing EFI/NVRAM. This known failure is not a GPU or boot failure. The retained instructions below describe the original preparation design, not a successful automatic laptop run.

The first laptop inventory completed without warnings but found no `10DE:1F91` node in IOService or the Device Tree. Its exact `-wegnoegpu` boot-argument check returned true. This records non-visibility with the disable argument active; it does not prove electrical power-off or establish that the argument is the only cause.

This package prepares a separate copy of the **current Samsung EFI** with only the exact `-wegnoegpu` argument removed. It includes the native preparation tools, OpenCore 1.0.8 validator and the PCI inventory executable. It does not provide a NVIDIA GPU driver.

## Prepare the copy on Tahoe

These are retained helper instructions. The manual alternative is to keep the working Samsung EFI intact, edit a separate HDD copy, remove only the exact disable argument, retain `-igfxblr` and the working Intel patches, and leave any NVIDIA power-off SSDT disabled. The later inventory, rather than an assumed EFI edit, establishes that the argument is absent and the PCI device is visible. The latest reports do not audit all other EFI settings. A blanket NVRAM reset is unnecessary.

Extract **S540-nvidia-visibility-v1.zip** into Downloads, then run:

```sh
bash "$HOME/Downloads/S540-nvidia-visibility-v1/PREPARE-NVIDIA.command"
```

The locator follows the running APFS Data volume to its single physical store and external GPT disk, then identifies that disk's EFI partition. This is appropriate for the confirmed independent Samsung boot; it is not a general detector of which OpenCore firmware loaded. If necessary, the launcher requests the administrator password only to mount that EFI **read-only**. It does not install anything on the Samsung, the HDD or Windows.

The program creates a private **NVIDIA-VISIBILITY…** folder on the Desktop. A successful folder contains `READY.txt`, validation logs, the original configuration and the experimental **EFI** directory. Use only a completed folder with `READY.txt`. The generated folder contains private machine configuration; keep it out of the public repository.

If automatic selection cannot establish the source, mount the current Samsung EFI and pass the inner EFI folder explicitly:

```sh
bash "$HOME/Downloads/S540-nvidia-visibility-v1/PREPARE-NVIDIA.command" "/Volumes/EFI/EFI"
```

Adapt that example to the actual mount point. Do not pass the old HDD copy or an earlier downloaded EFI archive.

## Boot the separate HDD copy

1. Connect the 240 GB boot HDD. Keep its existing EFI as a backup, for example by renaming that directory to `EFI-before-NVIDIA` on the HDD.
2. Copy the prepared Desktop folder's **EFI** directory to the HDD root. Do not place it inside another EFI directory. The Samsung EFI remains the recovery boot path.
3. Restart and use the firmware's one-time boot menu to select the HDD explicitly. Select the Samsung macOS volume from that experimental OpenCore picker.
4. On the Tahoe desktop, run the included inventory:

   ```sh
   bash "$HOME/Downloads/S540-nvidia-visibility-v1/CHECK-NVIDIA.command"
   ```

5. Share the new `nvidia-pci.json` from the Desktop's `NVIDIA-PCI…` folder.
6. After the report, shut down, disconnect the HDD and start through the original Samsung OpenCore again. If the experiment cannot reach Tahoe, use the firmware boot menu to select the unchanged Samsung instead.

Preparation requires the original Samsung configuration to already have both its working `boot-args` value and `NVRAM/Delete/boot-args`. Returning through that verified original configuration reinjects its baseline arguments. The preparation changes no NVRAM. Booting the experimental OpenCore does apply its existing Delete/Add policy and therefore can update the shared `boot-args` variable. The original Samsung configuration is the recovery mechanism; this is not a private per-disk NVRAM namespace. A blanket NVRAM reset is not part of the procedure.

## Scope and checks

The stager preserves `-igfxblr`, all other plist values and every copied file except `OC/config.plist`. It does not enable an ACPI power-off table, change graphics memory settings, install a kernel extension or load firmware. It accepts the established native NVRAM profile and refuses an absent Delete rule, an unsupported disable-argument variant or an invalid baseline.

Both configurations must pass the bundled pinned `ocvalidate` 1.0.8. Source hashes before and after preparation must match. Only `BOOT` and `OC` are copied. Symlinks, hard-linked files, overlapping output paths and non-regular source entries are refused; generated files are private. Failed preparation retains private diagnostics with a `FAILED.txt` marker and no READY marker.

Intel CI checks native compilation, locator metadata fixtures, exact configuration transformation, filesystem conservation and real-validator integration with public configuration. These checks do not establish a successful laptop boot or GPU visibility. Keep the resulting report separate from later GPU initialization, GSP and command-execution milestones.

See the [source assessment](../../docs/reference/nvidia-port-assessment.md), [PCI inventory](../../packages/nvidia-pci/README.md) and [OpenCore 1.0.8 NVRAM implementation](https://github.com/acidanthera/OpenCorePkg/blob/6fe4d15cb66596d99d8cfedce69d8fc6dad71886/Library/OcMainLib/OpenCoreNvram.c).
