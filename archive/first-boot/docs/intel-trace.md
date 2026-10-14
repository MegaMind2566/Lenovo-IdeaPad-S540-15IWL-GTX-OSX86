# Direct Intel boot tracing

The patch and DSDT review found no proven correction. The new boots have no persistent unified events. This package enables direct Lilu/WhateverGreen tracing while preserving the current EFI's graphics properties: it does not repeat earlier tests by changing the framebuffer.

## Usage

1. From Windows, extract **S540-traccia-Intel.zip** to the root of the OpenCore HDD, beside EFI. Do not copy it to the Samsung or Windows disk. Accept replacement of the collector if it already exists.
2. Run **TRACCIA-INTEL.cmd** and check the activation message. The program saves the current config and both kexts in `EFI/OC/backup-traccia-intel`.
3. Boot through the same OpenCore and select **Machintosh SSD**, the installed system. Leave the attempt running for at least **two minutes**, even if the text or cursor appears stuck: Lilu attempts to save its buffer after 60 seconds.
4. If the interface does not appear, return to Windows and run **RECOVERY-TRACCIA-INTEL.cmd**. This prepares VESA for Recovery and disables automatic dumps in that mode.
5. Boot Recovery. Mount **Machintosh SSD - Data** in Disk Utility and open Terminal. Run:

```bash
bash "/Volumes/240 GB/RACCOGLI-INTEL.command"
```

If the HDD name differs, replace only `240 GB`. If the Data volume has another name, pass it as the sole additional argument, enclosed in quotes.

6. Return to Windows and attach the DIAGNOSI-MACOS ZIP identified by the command. It contains private configuration data: share it in the chat without publishing it in the repository.
7. To return to the exact files present before tracing, run **RIPRISTINA-TRACCIA-INTEL.cmd**. Do not delete the backup before restoration. The program refuses automatic restoration if it detects subsequent changes to the affected files.

## Temporary changes and collected data

Lilu 1.7.2 and WhateverGreen 1.7.1 are replaced with their respective official DEBUG builds. Test boot arguments include `-liludbgall -wegdbg liludump=60 -igfxdump`; VESA and safe boot are removed from the normal test. Other config values remain unchanged, including the current Intel pair. IntelBTPatcher must already be disabled. The program does not change SSDTs, USB mapping, Wi-Fi, SMBIOS identity, or the Windows disk.

The collector reads `private/var/log/Lilu_*.txt` and `AppleIntelFramebuffer_*`, available reports, and the backup containing the exact tracing configs from the installed Data volume. It does not copy diagnostics/uuidtext again. The summary also records missing files: if the kernel or filesystem never reaches the write stage, a dump may not exist. An empty trace does not establish GPU functionality.

The Lilu file may report properties and driver initialization; the framebuffer dump allows inspection of the table actually loaded. There is no guarantee that every error or firmware DVMT value will be printed. DEBUG builds may slow down boot and are used only for diagnosis.

Both official ZIPs are checked with SHA-256, and the applied payload has a per-file manifest. Licenses are included. The reproducible builder is `tools/build_intel_trace.py`; it includes no config or personal data in the distributed ZIP.

The controller was checked with nine test groups covering backups, alterations, restoration, and failures during replacement. A separate test using the delivered EFI copy and Whiskey Lake config restored all 55 original files byte for byte; the normal and Recovery tracing configs pass ocvalidate 1.0.8. The collector preserves the exact test files and records missing files. Tests ran on Linux: Windows launchers and physical boot with DEBUG builds remain to be run on the laptop.

## Sources

- [Lilu 1.7.2, debug flags and liludump](https://github.com/acidanthera/Lilu/blob/1.7.2/README.md).
- [WhateverGreen 1.7.1, wegdbg and igfxdump](https://github.com/acidanthera/WhateverGreen/blob/1.7.1/README.md).
- [ACPI patch review](../../../docs/reference/acpi-patch-review.md).
