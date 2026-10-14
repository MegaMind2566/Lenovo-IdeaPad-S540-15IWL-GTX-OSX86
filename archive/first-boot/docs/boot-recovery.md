# Recover data from the stalled normal boot

The EFI review is complete and found no structural defect. The goal remains to reach the interface and verify Intel graphics. Available OpenCore logs end before system events; the only decoded unified archive described VESA boots. Persistent events from the normal boot already attempted on the Samsung are now required. Reorganizing the media is not a prerequisite: the old logs have already been deleted directly.

The **S540-recupero-avvio-normale.zip** package temporarily prepares Recovery access and collects this data. It does not require repeating the stalled normal boot before collection.

## Steps

1. From Windows, extract the package contents to the root of the OpenCore HDD, beside EFI. Accept replacement of the earlier RACCOGLI-UNIFIED.command launcher and diagnosi-unified folder. PREPARA-RECOVERY-LOG.cmd and RIPRISTINA-PROVA-INTEL.cmd must also sit at the same level as EFI.
2. Open **PREPARA-RECOVERY-LOG.cmd**. It adds only -igfxvesa to the current config's boot arguments. It preserves the exact previous file in EFI/OC/config.before-runtime-logs.plist. Intel properties, identity, kexts, and all other settings are preserved; IntelBTPatcher must already be disabled. It does not use old full-EFI backups.
3. Boot through the same OpenCore and select **Recovery 26.7.1**. The original HDD Recovery named **240 GB**, already used, is also available. Recovery access had been verified with VESA and IntelBTPatcher disabled; preparation preserves the other current settings.
4. In Disk Utility, show all devices, identify the external Samsung, and mount **Machintosh SSD - Data**. Open Utilities → Terminal and run the following command.

```bash
bash "/Volumes/240 GB/RACCOGLI-UNIFIED.command"
```

5. Wait for the **DIAGNOSI-MACOS-….zip** path printed on screen. Return to Windows and attach that ZIP. It collects the Samsung's installed system, with enough data to distinguish separate boots; a photograph of the stall is not required.

The launcher must identify itself as unified collection v4 for the installed system. If the Data name has changed, its path can be passed as the sole argument. The collector preserves the complete diagnostics/uuidtext pair, including timesync and dsc if present, without filtering by date or extension. If du/df/awk are missing, the space estimate is optional and copying proceeds. Incomplete copies are reported in the summary.

## Configuration associated with the test

When it finds the dedicated backup, v4 includes **config-avvio-normale.plist**, identical to the backup before VESA was added, and **config-recovery.plist** in the report. These files remain private inside the ZIP and are not published in the repository. They provide the exact Intel values and distinguish the test state from the state needed to read data in Recovery. The collector edits neither file.

Booting Recovery in VESA does not retroactively change normal-boot events saved on Data. Subsequent comparisons must use each boot, its time, and its effective boot arguments. Logs from the running Recovery are not used to judge acceleration in the installed system.

## Restore

After collection, run **RIPRISTINA-PROVA-INTEL.cmd** from Windows to restore the previous config byte for byte, preserving the same identity and Bluetooth change. The backup is retained. If later changes are incompatible with preparation, the program refuses automatic restoration instead of overwriting them. Preparation also rejects a backup from another state, or VESA already present without the dedicated backup; keep the complete message in these cases.

## Validation and limits

Preparation and restoration were checked using the real test config in temporary folders: only boot arguments change, identity and Intel properties are preserved, the backup is identical, repeated operations are handled, and conflicts leave the config unchanged. The collector was checked with simulated volumes, binary copies, missing tools, invalid sources, and source-content comparisons before and after. Both config copies are byte-for-byte identical and the original files remain unchanged. The Windows launcher components were not executed on this Linux host.

Collection and Recovery boot on the laptop remain pending. Messages held only in memory at reboot may be absent. If the collection has no normal-boot events, a dedicated recording diagnosis will be needed, selected after checking the available data. Recovery preparation is a diagnostic tool, not a graphics fix.
