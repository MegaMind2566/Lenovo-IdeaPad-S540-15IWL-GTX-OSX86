# Organizing the OpenCore HDD

The cleanup preserves current boot files and archives recognizable older project trials on the Windows Desktop. The full review of the delivered files and configurations is documented in [EFI review](../reference/efi-review.md). This is not another framebuffer trial and does not replace the EFI.

## Usage

1. Extract **S540-riordino-avvio.zip** to the root of the OpenCore HDD, alongside EFI and the Recovery files. Do not run the command from inside the ZIP. Allow it to replace the previous unified collector: the included version is v3, already checked without du.
2. From Windows, double-click **RIORDINA-AVVIO.cmd**. It uses Python 3, already used for Recovery; no additional program or Terminal is required.
3. Wait for copying and verification to finish. A folder named **S540-archivio-avvio-DATA-ORA-…** is created on the Desktop. For each item, the program compares files, sizes, and SHA-256 hashes before removing the verified data from the HDD. If an error occurs, retain the archive and any remaining items.
4. Read **RAPPORTO.json** and **RIPRISTINO.txt** in the archive. The report lists moved files, errors, and the items remaining in the root directory. Attach RAPPORTO.json to review remaining items without copying the EFI again.

The program only accepts the root of a disk containing EFI/BOOT/BOOTx64.efi and EFI/OC/config.plist. It rejects roots containing Windows or Users and requires the Desktop to be on another volume. It does not require administrator privileges, download anything, or send the report automatically.

## Archived files

The rules apply only to the following items in the disk root:

- Logs named opencore-AAAA-MM-GG-HHMMSS.txt.
- DIAGNOSI-MACOS- and LOG-UNIFICATI- folders with the collectors' six-character suffix, and the corresponding ZIP files.
- Older S540-test- and S540-diagnosi- ZIP packages, and the first-trial ZIP S540-81SW-Tahoe-prima-prova.zip.
- The old TEST-INTEL, TEST-BT, TEST-GRAFICA, and AVVIO-SICURO commands, and their restore commands listed by the program.
- The old RACCOGLI-LOG-MACOS.command launcher.

The entire current EFI, including configuration and backups in EFI/OC, stays in place. Recovery files, the contents of tools, the RACCOGLI-UNIFIED.command launcher, and the diagnosi-unified folder are retained. Unrecognized files are kept and listed. Links and reparse points are not followed or archived automatically.

## Restore

Copy an archived item from the Desktop to the root of the same HDD. If an item with that name already exists, compare the two copies before overwriting it. The Desktop folder preserves the internal structure of collections and a hash manifest for each item moved successfully. If copying is interrupted or a later error occurs, check both the archive and the remaining HDD contents: files already transferred can still be recovered from the archive.

## Current collector

The package also includes the existing unified collector v3. From Recovery Terminal, with the Samsung Data volume mounted, run:

```bash
bash "/Volumes/240 GB/RACCOGLI-UNIFIED.command"
```

The Recovery interface had been reached with temporary VESA mode and IntelBTPatcher disabled. The cleanup does not change those parameters or establish that Recovery opens with the current profile. Data persisted on the Samsung Data volume is needed to analyze the stall, rather than logs from the running Recovery environment.

## Program checks

The move procedure is checked with simulated folders: preservation of EFI/Recovery and unknown files, archiving only expected names, copy hashes, empty folders, copy failures, and links. These checks do not constitute execution on the laptop's Windows disk; the actual result will be documented in RAPPORTO.json.
