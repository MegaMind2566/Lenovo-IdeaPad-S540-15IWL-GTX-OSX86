# SD reader and fingerprint scope

Updated on **24 October 2026**. SD investigation is active before consolidating the **non-NVIDIA EFI**, with **all SD tests on the external EFI only**. The user has marked the fingerprint reader **NOT WORKING in macOS** and stopped further fingerprint work. NVIDIA, HDMI and the accepted non-working F8 camera toggle remain outside this work.

## O2Micro SD reader

The controller is PCI `1217:8621`, subsystem `17AA:3803`, revision 01. The same card works under Windows. A retained Tahoe report shows the older BigSurSDXC controller, slot and block-storage services active, with `IONameMatched=pci14e4,16bc`, but no readable SD media. A loaded kext is not a successful card-reading result.

The retained `S540-SD-O2-DIRETTO.zip` candidate changes only the kext personality match to `pci1217,8621`. Its executable is unchanged. Static disassembly shows that the previous Broadcom alias selects Broadcom-specific controller/slot behavior and vendor-register accesses. Direct physical matching avoids that branch; it does not add O2Micro-specific initialization or establish that the Broadcom branch was the only failure.

| Item | Verified SHA-256 |
|---|---|
| Direct-match candidate ZIP | `dbb603497b05eef4b5fa7432b88ec8d5615ee225d6ad5879fe8567e110c18964` |
| Unchanged BigSurSDXC executable | `dfb316e5e4ce745da6dbbb7470af1720e6719741e2a900aff3b3114e35060bd7` |
| Direct-match Info.plist | `d3dc9a76442bddf030389ea527045070a8e08153edb6b926ce3d60ddc70f4ae2` |

The x86_64 `__text` section of the reviewed BigSurSDXC, older NUCO2SDXC and supplied Sonoma CtlnaSDXC binaries is byte-identical: 55,746 bytes, SHA-256 `11b2fbe0068e69cb7efc772c6290323524bb7496d79e962e6728e069b54ca9d7`. Renaming or swapping those packages alone is not a new implementation.

The direct candidate was prepared for the previous 240 GB test EFI. It contains no config.plist and assumes an already enabled matching kext entry and compatible properties. Those assumptions have now been verified against the newly supplied external test EFI. Use the updated trial package below; the older 240 GB instructions are retained as provenance. The earlier request for an internal EFI copy is superseded; SD trials must not modify the internal EFI. No native compilation or repeat observer build is required merely to reuse the verified binary.

[HaC-Mini issue 1056](https://github.com/osy/HaC-Mini/issues/1056#issuecomment-1858981127) includes a report of the same physical ID working on Sonoma; [another report](https://github.com/osy/HaC-Mini/issues/1056#issuecomment-1859028063) limits success to cards up to 32 GB. Neither establishes Tahoe compatibility or complete SDXC support. The [Linux O2Micro driver](https://github.com/torvalds/linux/blob/5029bff09e79ad80883c5ee2828b8c4a263cf3dd/drivers/mmc/host/sdhci-pci-o2micro.c) contains SEABIRD1-specific initialization for this family. That is a reference for implementation review, not permission to copy unrelated device register writes into ACPI.

The current outcome remains **no confirmed macOS SD reading**. The reviewed external direct-match trial has now attached successfully but produced no SD media; see the target result below. Acceptance still requires actual readable media. A successful load or controller name alone does not close it.

### External SD-only trial prepared — 24 October 2026

The supplied external EFI has now been compared with the retained candidate. It already enables BigSurSDXC 1.9.0 for Darwin 25 and its compatible-name list includes `pci1217,8621`. The existing driver executable and Info.plist exactly match the retained original and rollback inputs.

The user explicitly requested preserving the existing external EFI, including its enabled NVIDIA PCI probe. **No config.plist, boot argument, ACPI setting, NVIDIA probe or bootloader change is included in this SD trial.** The earlier idea of converting this test EFI to the Intel-only baseline was cancelled before applying changes.

`S540-SD-Test-Esterna-v1.zip` supplies only the direct-match SD kext, the exact original kext for rollback, instructions, checksums and an optional passive report collector. ZIP SHA-256: `4f757f4dab19b8341144845d94382f4e74aaf60c9d824362d35d6f06d40aaf13`. Its sole driver change is the already reviewed `IONameMatch` string. The executable is unchanged; no config.plist, EFI executable or SSDT is delivered.

Independent review verified all eight archive files, seven checksum entries, permissions, the single byte/semantic substitution and rollback equality against the uploaded EFI. The collector passes Bash syntax checking and only reads runtime state into a Desktop report. No native compilation or CI was needed. These checks establish package integrity, not target card-reading success.

The target trial is one normal boot from the external EFI with the known Windows-readable SD inserted, then opening an existing file and reporting card capacity. If media is absent, the optional passive collector records the loaded driver/controller/disk state from that same boot; it does not install drivers, reset NVRAM, format the card or change the NVIDIA experiment.

### External direct-match target result — 24 October 2026

The supplied target report was collected on macOS 26.7.1 / 25G241. All five passive commands completed with exit 0. BigSurSDXC 1.9.0 is loaded, and the active controller has both `IONameMatch` and `IONameMatched` set to `pci1217,8621`. This verifies that the direct-match candidate actually attached; the outcome is not an untested-package assumption.

The slot reports `Card Present=Yes`, bus voltage 3300, base frequency 50 and clock divisor 0. Its block-storage device and IOBlockStorageDriver exist, but no IOMedia child is published and diskutil lists no SD disk. Read/write operations and byte counts remain zero. **Result: the direct-match trial did not produce readable SD media.** The earlier Broadcom-match report reached the same media-publication limit; avoiding its vendor branch has not fixed card reading.

These observations locate the failure before filesystem mounting, but do not identify a failing SD command, reset, interrupt or clock operation. The reported clock-divisor property alone does not prove an electrical clock fault. AppleSDXC 3.5.4 is also loaded, but this report does not show it claiming this controller or establish a driver conflict. No automatic AppleSDXC block, formatting, additional ID spoof or unrelated ACPI change is justified.

The card's capacity/type is absent from the report. The published <=32 GB limitation remains a possible comparison boundary, not a demonstrated cause here. Further work must distinguish card initialization failure with specific evidence before another functional patch or repeated target round. The raw report remains private. This result update changes documentation only; it does not modify either EFI or the retained NVIDIA trial, and starts no build or CI.

## Goodix fingerprint reader

**Status: NOT WORKING in macOS. Further fingerprint investigation stopped by user request on 24 October 2026.** The findings below are retained as the explanation of the limitation, not as an active development plan.

The retained USB inventory identifies **Goodix 27c6:55b4**, bcdDevice `0100`, on internal **HS02**. USB enumeration already works. It does not establish image capture, enrollment, matching or login authentication.

[Apple's biometric architecture](https://support.apple.com/it-it/guide/security/sec067eb0c9e/web) performs Touch ID enrollment and matching within Secure Enclave, with an authenticated sensor connection. The Lenovo lacks that Apple hardware/pairing architecture. A generic USB driver or EFI identity patch does not provide a supported native Touch ID integration. No usable macOS driver for this exact sensor was established in the review.

There is real community support for the sensor on Linux: [libfprint-goodix55b4-milan](https://github.com/TheWeirdDev/libfprint-goodix55b4-milan/tree/aa42bb9816c3bc6d05960d420cf314e9f9b15679), reviewed at commit `aa42bb9816c3bc6d05960d420cf314e9f9b15679`. Its libfprint device implements capture, enrollment, verification and identification, and the documented build integrates libfprint/fprintd on Linux. It is not a macOS kext or a ready Touch ID component.

The driver's provisioning instructions overwrite the sensor's persistent pre-shared key and may replace firmware. The author documents loss of the current Windows pairing and instructs dual-boot users to disable the Windows fingerprint driver. This is a concrete incompatibility with silently including that provisioning in the existing dual-boot EFI setup. No provisioning command, firmware flash, biometric enrollment or authentication-policy change has been run.

A macOS userspace capture/matcher port would be separate development with separate authentication and dual-boot requirements; it is not part of the requested remaining work. No further fingerprint package, test, firmware change or login-policy integration is planned. Fingerprint behavior under Windows and the working macOS password login remain separate from this result.

## Consolidation boundary

Retain the working internal rEFInd/OpenCore/Windows boot arrangement and the confirmed audio, keyboard, USB, sleep and Low Power Mode results. Prepare and test the SD delta only on the reviewed external EFI, preserving its existing NVIDIA experiment as explicitly requested. The requested EFI consolidation follows the SD target result, with fingerprint authentication explicitly recorded as not working. Do not insert experimental NVIDIA code, fingerprint provisioning, untested SD variants or private machine identifiers into the public stable package.
