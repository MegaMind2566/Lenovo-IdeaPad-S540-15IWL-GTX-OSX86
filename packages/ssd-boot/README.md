# Boot directly from the external macOS SSD

**Helper on hold.** Version 1.0.0 stopped at its initial mounted-target identity/writability check on the laptop, before backup or copy. The failed condition remains unidentified. Independent Samsung boot succeeded after a manual transfer of the current private EFI. Do not rerun this helper on that working installation. Its source remains available for a scoped guard correction; CI success is not a successful laptop transfer.

This installer copies the **current private working OpenCore files** from `/Volumes/240 GB/EFI` to the EFI partition of the external SSD running macOS. It does not use the public EFI release.

It discovers the running APFS container and its physical disk. The expected layout is an external 240 GB source with one Microsoft Basic Data partition and an external 250 GB target with EFI + APFS partitions. Disk numbers may change. An ambiguous or different layout stops the installer.

## Run

Extract `S540-ssd-boot.zip` into Downloads, then run as your normal desktop user:

```bash
bash "$HOME/Downloads/S540-ssd-boot/INSTALL-SSD-BOOT.command"
```

Enter the administrator password once. A private `S540-SSD-BOOT-BACKUP-…` folder is kept on the Desktop. It contains the source EFI and the previous target EFI, if one existed. Keep this folder private: the working configuration contains machine identifiers.

The installer replaces the target's `EFI/BOOT` and `EFI/OC` directories. Other existing folders, including `EFI/APPLE` and `EFI/Microsoft`, are preserved. It stages the complete target tree, verifies file hashes and directory paths, then promotes it. An unsuccessful promotion or verification restores the previous boot state when the target remains available.

No disk is formatted or repartitioned. The HDD, macOS configuration, drivers in `/Library/Extensions`, boot arguments and NVRAM are unchanged. No developer tools are required.

## First SSD boot

After **SSD boot files verified**, shut down. Disconnect the 240 GB HDD, leave the Samsung SSD connected and choose its UEFI entry in the firmware boot menu. Reaching macOS without the HDD confirms independent SSD boot.

If the SSD does not boot, reconnect the HDD and start from its existing OpenCore. The previous target EFI is in the Desktop backup; retain it for restoration. Do not replace the working private EFI with the public release.
