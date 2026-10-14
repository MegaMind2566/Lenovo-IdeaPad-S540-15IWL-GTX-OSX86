# Analysis of the 02:45 OpenCore log

**Later update:** a photograph shows a USB/Bluetooth panic with IntelBTPatcher 2.4 in the backtrace. In that photograph, `-x` is absent and `-igfxvesa` remains present. For the next boot, follow the [Bluetooth test](../../../docs/guides/bluetooth.md); the log analyzed here documents an earlier attempt.

Log dated October 13, 2026, with boot starting at 02:45:57. Only diagnostically useful details are listed; the original file and SMBIOS identifiers are not added to the repository.

## Confirmed data

| Item | Log result | What it does not establish |
|---|---|---|
| OpenCore | DEBUG 1.0.8; configuration read | Subsequent macOS functionality |
| Selected entry | `Should boot from 4. Machintosh SSD` | The name does not demonstrate completed installation |
| Entry path | APFS volume on an external USB device | Link speed and stability remain to be checked in macOS |
| Diagnostic parameters | `-igfxvesa -x` present in `MBA:NV` and `MBA:OUT` | This boot only, not an attempt after restoration |
| NVRAM boot-args | Deletion and setting: `Success` | Must be compared with the next boot log |
| Intel properties | Platform and device-id setting: `Success` | Values are not printed; Metal is not checked |
| Lilu and WhateverGreen | Injection: `Success`, versions 1.7.2 and 1.7.1 | Injection is not equivalent to kernel initialization or functionality |
| AppleALC | Excluded because the kernel is 25.6.0 | Consistent with the configuration enabling it only on Sequoia |
| IONVMeFamily block | OpenCore reports `Success` | Earlier detection of the internal disk prevents treating effective exclusion as confirmed |
| Firmware MAT | `MAT support is 0` | Relevant if UEFI handoff issues arise; does not alone identify the cause of graphics artifacts |
| Final line | `EB\|LOG:EXITBS:START` at 02:46:02 | OpenCore's log excludes WindowServer, Setup Assistant, and later macOS errors |

The current menu entry is spelled **Machintosh SSD**. Earlier documents called it “Macintosh SSD”: select the actual entry present on the external disk.

## Next test

Both parameters were active. Using the backups created by earlier tests, the available procedure is:

1. From Windows, run **RIPRISTINA-AVVIO.cmd** on the same OpenCore HDD.
2. After successful restoration, run **RIPRISTINA-GRAFICA.cmd**.
3. Boot OpenCore again from that HDD and select **Machintosh SSD**.

If **TEST-INTEL.cmd** has already been applied, this sequence is unnecessary: that test removes the same two parameters while preserving the rest of the configuration. Use its **RIPRISTINA-INTEL.cmd** to undo it.

Restore scripts refuse to erase subsequent changes. If restoration fails, collect its message before proceeding.

The next boot's visible result and, if the problem continues, its new log are required. Check that `MBA:OUT` no longer contains `-x` or `-igfxvesa` before comparing normal graphics behavior. DVMT, the framebuffer, and Metal functionality remain to be verified.

## System image in the boot path

The booter adds `-bsdmgroot` from `com.apple.Boot.plist` and reads `OS.dmg.root_hash`. In XNU source, this parameter is associated with attempting to use BaseSystem as the root volume. This is another reason not to infer from the volume name alone that the final system was reached. It is not removed by the tests: it comes from Apple's boot path, rather than the two diagnostic parameters added to the EFI.

Reference: [Apple XNU, bsd_init.c, bsdmgroot_bootable function](https://github.com/apple-oss-distributions/xnu/blob/main/bsd/kern/bsd_init.c).

## Subsequent log: 063718

`opencore-2026-10-13-063718.txt` was received, covering the attempt with only the Bluetooth exclusion. It contains 723 useful lines; the remainder is preallocated NUL space. The original file and identifiers are not published.

| Item | Result |
|---|---|
| Selected entry | `Machintosh SSD`, external USB APFS volume |
| Boot arguments in both `MBA:OUT` lines | `-igfxvesa` present; `-x` absent |
| IntelBTPatcher | No injection reported, consistent with its exclusion |
| IntelBluetoothFirmware / BlueToolFixup | Successful injection, versions 2.4.0 and 2.7.2 |
| Lilu / WhateverGreen | Successful injection, versions 1.7.2 and 1.7.1 |
| Intel properties | Platform and device-id setting succeeded; values not printed |
| Kernel | Darwin 25.6.0 |
| BaseSystem parameter | `-bsdmgroot` absent from the boot arguments shown in this attempt |
| End of log | `EXITBS:START` at 06:37:30 according to the booter clock |

The absence of `-bsdmgroot` differs from the earlier log; it does not prove installation completion. Reading `OS.dmg.root_hash` alone does not identify a BaseSystem boot.

The booter also shows `This system was automatically rebooted after panic` before the new kernel handoff. It reports a panic detected before that handoff; it does not demonstrate a new panic during the subsequent black screen. A cursor without windows was reported.

The next step is **TEST-INTEL.cmd on the current EFI**, removing only diagnostic flags if present and keeping IntelBTPatcher excluded. Here, removal of `-igfxvesa` is expected. The combined test and reverse-order restoration were checked against the delivered configuration. Do not use an old full restoration after the Bluetooth change.

The VESA parameter confirms that acceleration is disabled. Whether this causes the missing interface remains to be checked on the next boot. OpenCore ends before WindowServer logs: it cannot locate the interface problem or demonstrate Metal.

## Normal boot confirmed: 103339 and 103615

Both new October 13, 2026 logs select Machintosh SSD and show boot arguments without `-igfxvesa`, `-x`, or `-bsdmgroot`. IntelBTPatcher is not injected; Intel firmware and BlueToolFixup remain present. Lilu 1.7.2 and WhateverGreen 1.7.1 are injected successfully, Intel properties are set, and the kernel read is Darwin 25.6.0. Framebuffer values are not printed and acceleration is not established.

Log `103615` reports no panic log and ends at `EXITBS:START` at 10:36:25 according to the booter clock. It contains no subsequent interface logs. The new photograph shows macOS code-signature messages, a kernelmanagerd limit identified as nonfatal, extension-collection loading, and IOUserDockChannelSerial faults. No single line identifies the cause of the stall.

Recorded Recovery entries are **Recovery 26.7.1** on the Samsung and the original HDD Recovery under **240 GB**. [Offline report collection](gui-diagnostics.md) reads DiagnosticReports and available logs from the installation's Data volume. Restoring the Intel test, while preserving the Bluetooth change, allowed Recovery access and the first collection; it need not be repeated if already applied.

## Offline Data-volume reports

The `DIAGNOSI-MACOS-UN5FYU.zip` collection contains the earlier bluetoothd/IntelBTPatcher panic, install.log, system.log, and the APFS inventory. The collector's incomplete-copy warning concerns only the panic's extended attributes; the report bytes are available. The copying issue is corrected with `cp -RX` for subsequent collections.

Install.log reports installer success, completion of Template Migration, and macOS 26.7.1 history. Language Chooser starts Hello and hides the progress window in one recorded boot. Setup Assistant does not appear to have completed. The ZIP contains no new WindowServer/Setup Assistant reports or evidence of a DVMT error. Differing log times prevent assigning all these events to the current normal test. Pressing Return had no effect; the [interface diagnosis](gui-diagnostics.md) now includes offline diagnostics and uuidtext collection. There is still no evidence of installation corruption and no identified cause of the black screen.
