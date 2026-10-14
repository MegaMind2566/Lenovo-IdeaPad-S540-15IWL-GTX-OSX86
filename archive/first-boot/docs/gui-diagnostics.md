# Collect reports from an installation without a working interface

**For the current non-VESA stall:** use [Normal boot recovery](boot-recovery.md) and S540-recupero-avvio-normale.zip. The dedicated preparation preserves the current config, adds only VESA to read data in Recovery, and provides a separate restoration. Collector v4 also includes a private copy of the normal attempt's config. The instructions below describe earlier packages and the manual copy procedure already used.

**Unified collection received:** LOG-UNIFICATI-e8VM9n was decoded. Both boots use VESA; in the second, the welcome screen logs a texture-creation error. The [new analysis](unified-log-analysis.md) describes the data and next test with TEST-INTEL.cmd.

Logs `opencore-2026-10-13-103339.txt` and `opencore-2026-10-13-103615.txt` confirm that `-igfxvesa` and `-x` are absent. IntelBTPatcher is not injected; Lilu and WhateverGreen are injected successfully. This does not demonstrate graphics initialization or Metal functionality. The log ends at kernel handoff, before interface events.

The new photograph shows macOS services and extension-collection loading, without a panic line. It contains code-signature errors, an explicitly nonfatal kernelmanagerd memory limit, and repeated IOUserDockChannelSerial faults. None of these lines alone identifies why the desktop is missing.

The first collection contains no new reports explaining the black screen. Pressing Return with the configuration that opened Recovery also failed to show the welcome screen. The same collector now offers `--unified`: alongside DiagnosticReports and install.log/system.log, it copies all of `private/var/db/diagnostics` and `private/var/db/uuidtext` from the Samsung's Data volume. It does not filter by date or extension. A missing report does not rule out a process that is stuck or never started.

## Steps

1. In Windows, extract **S540-diagnosi-unified-v3.zip** to the root of the OpenCore HDD. Accept replacement of v2 files. `RACCOGLI-UNIFIED.command` and the `diagnosi-unified` folder must sit beside `EFI`. The package contains the updated collector in the new folder; unified mode is already enabled in the launcher.
2. Keep the configuration that opened Recovery: temporary VESA and IntelBTPatcher disabled. If you returned to the normal Intel test, run **RIPRISTINA-INTEL.cmd** on the same HDD. Do not repeat it if restoration is already applied. If it reports a missing backup or later changes, keep the error without replacing the config.
3. Boot through the same OpenCore and select **Recovery 26.7.1**, present in the menu recorded by the new logs. Recovery is needed to read reports saved on the Samsung. If this entry does not open Utilities, the original HDD Recovery is also present under **240 GB**; select the entry with the Recovery icon.
4. In **Disk Utility → View → Show All Devices**, identify the external Samsung and its **Data** volume. Mount it if necessary. The expected name is **Machintosh SSD - Data**; verify that it is the Samsung's Data volume from the same Machintosh SSD installation.
5. Open **Utilities → Terminal** from the top menu and run:

```bash
bash "/Volumes/240 GB/RACCOGLI-UNIFIED.command"
```

6. Wait for copying and ZIP creation; unified logs may take much more space than the first collection. The program prints the **DIAGNOSI-MACOS-….zip** path, saved on the OpenCore HDD. Return to Windows and attach that ZIP.

The program automatically recognizes `Machintosh SSD - Data` and `Machintosh SSD - Dati` only if it finds the expected Data-volume structure. These checks do not verify the APFS group: verify the Samsung selection in Disk Utility. It does not mount or unlock volumes automatically. If the name differs, pass the exact path as an argument, for example:

```bash
bash "/Volumes/240 GB/RACCOGLI-UNIFIED.command" "/Volumes/NOME ESATTO DEL VOLUME DATA"
```

The command uses the observed HDD path, `240 GB`. If the HDD name changes, replace it with the name present in `/Volumes`. Avoid a wildcard for the launcher when copies exist on several disks: they would become additional arguments. If collection stops, photograph the Terminal message. Incomplete copies are listed in the ZIP summary. The program reads the Data volume mounted under `/Volumes` and writes the collection to the HDD containing the package; it rejects a destination inside Data and a source in the Recovery system. For `--unified`, if du/df/awk are available, it checks space to retain the folder and ZIP, estimating twice the log size plus a margin. If any of these tools is missing, copying proceeds and the missing space estimate is recorded. It does not change EFI, boot arguments, signatures, or system settings.

At startup, the launcher must identify itself as unified collection v3 for diagnostics + uuidtext. The earlier sequence—a volume error with `--unified` alone, followed by an error allowing only the Data-volume path when adding that path—is consistent with the old collector, which accepts only one argument and does not recognize the option. It does not identify a disk problem. Photographs of the checks confirm Library, Users, and private/var in Data; the first two manual checks had path errors. The distinct launcher name and separate folder allow use of the updated version without relying on the old script in tools.

Launcher v2 was run in actual Recovery, where `du` is absent. Its mandatory size check therefore stopped collection before copying. Version 3 makes estimation optional when tools are missing while keeping both diagnostics and uuidtext copies enabled. Availability of du in the full system does not demonstrate its presence in Recovery.

## Direct copy from the open Recovery session

If collector v2 stopped because du was missing, the offline data pair can be collected directly with these commands. In this session the HDD is `240 GB`, and the Data wildcard matches only Machintosh SSD - Data. If several Data volumes have SSD in their names, use the exact path instead of the wildcard.

```bash
log_output=$(mktemp -d "/Volumes/240 GB/LOG-UNIFICATI-XXXXXX") &&
cp -RX /Volumes/*SSD*Data/private/var/db/{diagnostics,uuidtext} "$log_output/" &&
ditto -c -k "$log_output" "$log_output.zip" &&
printf '%s\n' "$log_output.zip"
```

Each line ends with `&&` so execution continues only if the previous command succeeds. The commands copy both complete directories from Data and create LOG-UNIFICATI-….zip on the HDD while retaining the folder. This direct collection contains only diagnostics and uuidtext: it excludes the collector's additional reports, does not estimate space, and does not convert the data into a logarchive. If copying stops, keep the message and folder; do not compress a copy reported as incomplete.

## Limits and return to the normal test

Collected reports describe the Samsung's installed system. A normal `log show` or `sysdiagnose` run in Recovery would describe the running Recovery; it is not used as a substitute for logs from the stalled attempt. Mode `--unified` preserves the complete pair in `UnifiedLogs/diagnostics` and `UnifiedLogs/uuidtext`, including timesync and dsc if present. This is offline data to decode after collection, not an already-converted `.logarchive`. Messages held only in memory cannot be recovered after reboot.

To return to the normal test after collection, **TEST-INTEL.cmd** removes VESA from the current EFI again. Its backup remains valid if no other changes are made between restoration and reapplication. Do not use restoration from the earlier graphics test after the Bluetooth change.

The first collection ran in actual Recovery. Unified mode was checked with simulated volumes, names containing spaces, the complete diagnostics/uuidtext pair, missing directories, source and destination checks, insufficient space, and ZIP creation. Results from unified-mode execution in actual Recovery remain pending.

## Sources

- [Apple DTS: collect the entire DiagnosticReports contents](https://developer.apple.com/forums/thread/763928).
- [Apple: mount a volume in Disk Utility](https://support.apple.com/guide/disk-utility/mount-a-volume-thats-been-ejected-dskutl1027/mac).
- [Apple WWDC22: running-system logs and explicit archives](https://developer.apple.com/videos/play/wwdc2022/10119/).
- [Apple WWDC16: unified-log structure and persistence](https://devstreaming-cdn.apple.com/videos/wwdc/2016/721wh2etddp4ghxhpcg/721/721_unified_logging_and_activity_tracing.pdf).
- [Mandiant: manual diagnostics and uuidtext collection for offline analysis](https://github.com/mandiant/macos-UnifiedLogs/blob/main/RUNNING.md).

## UN5FYU collection result

The Data volume was read, and the ZIP contains the old Bluetooth panic, install.log, and system.log. The only copying error concerns extended attributes of the panic file: its contents are present and readable. The updated collector uses `cp -RX`, copying data without extended attributes or resource forks; this collection need not be repeated to recover that panic.

The panic names bluetoothd and IntelBTPatcher 2.4, with `-igfxvesa` present and uptime matching the earlier photograph. It does not describe the normal attempt with the patcher excluded and VESA absent. The ZIP contains no WindowServer or Setup Assistant reports; this does not prove that these processes work.

Install.log records `Install Succeeded`, completion of Template Migration, and macOS 26.7.1 history. During one boot, Language Chooser records `hello started`, sets the progress window's opacity to zero, and hides it. The Setup Assistant marker is absent. These findings indicate arrival at the welcome stage without confirming that it was drawn or completed. The clocks differ: these messages must not automatically be assigned to the latest non-VESA attempt.

Pressing Return to advance had no effect. A new installation from scratch was started: wait for completion with the same EFI and IntelBTPatcher disabled. If the black screen returns, collect the new installation's unified logs with the command above. The Data-volume name may change after erasing: check it again in Disk Utility.

Installation-success messages do not establish every component's integrity; earlier data does not demonstrate corruption. Reinstallation may restore damaged files, but an EFI or graphics problem could recur. The new installation's result remains to be verified.

## New installation result

The black screen was reported again after the new installation from scratch. This result alone neither identifies the cause nor proves every file's integrity. Collection with `--unified` must now run on the new installation's Data volume after checking its name in Disk Utility. Earlier reports still concern the previous installation; the new ZIP is needed before selecting further EFI changes.
