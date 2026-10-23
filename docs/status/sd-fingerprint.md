# SD reader and fingerprint scope

Updated on **24 October 2026**. SD and fingerprint work has been resumed by request before consolidating the **non-NVIDIA EFI**. NVIDIA, HDMI and the accepted non-working F8 camera toggle remain outside this work.

## O2Micro SD reader

The controller is PCI `1217:8621`, subsystem `17AA:3803`, revision 01. The same card works under Windows. A retained Tahoe report shows the older BigSurSDXC controller, slot and block-storage services active, with `IONameMatched=pci14e4,16bc`, but no readable SD media. A loaded kext is not a successful card-reading result.

The retained `S540-SD-O2-DIRETTO.zip` candidate changes only the kext personality match to `pci1217,8621`. Its executable is unchanged. Static disassembly shows that the previous Broadcom alias selects Broadcom-specific controller/slot behavior and vendor-register accesses. Direct physical matching avoids that branch; it does not add O2Micro-specific initialization or establish that the Broadcom branch was the only failure.

| Item | Verified SHA-256 |
|---|---|
| Direct-match candidate ZIP | `dbb603497b05eef4b5fa7432b88ec8d5615ee225d6ad5879fe8567e110c18964` |
| Unchanged BigSurSDXC executable | `dfb316e5e4ce745da6dbbb7470af1720e6719741e2a900aff3b3114e35060bd7` |
| Direct-match Info.plist | `d3dc9a76442bddf030389ea527045070a8e08153edb6b926ce3d60ddc70f4ae2` |

The x86_64 `__text` section of the reviewed BigSurSDXC, older NUCO2SDXC and supplied Sonoma CtlnaSDXC binaries is byte-identical: 55,746 bytes, SHA-256 `11b2fbe0068e69cb7efc772c6290323524bb7496d79e962e6728e069b54ca9d7`. Renaming or swapping those packages alone is not a new implementation.

The direct candidate was prepared for the previous 240 GB test EFI. It contains no config.plist and assumes an already enabled matching kext entry and compatible properties. Those assumptions must be compared with the current internal EFI before preparing a delta; the old instructions are not the current installation procedure. No native compilation or repeat observer build is required merely to reuse the verified binary.

[HaC-Mini issue 1056](https://github.com/osy/HaC-Mini/issues/1056#issuecomment-1858981127) includes a report of the same physical ID working on Sonoma; [another report](https://github.com/osy/HaC-Mini/issues/1056#issuecomment-1859028063) limits success to cards up to 32 GB. Neither establishes Tahoe compatibility or complete SDXC support. The [Linux O2Micro driver](https://github.com/torvalds/linux/blob/5029bff09e79ad80883c5ee2828b8c4a263cf3dd/drivers/mmc/host/sdhci-pci-o2micro.c) contains SEABIRD1-specific initialization for this family. That is a reference for implementation review, not permission to copy unrelated device register writes into ACPI.

The current outcome remains **no confirmed macOS SD reading**. Acceptance needs actual readable media after applying the exact candidate to the reviewed current configuration. A successful load or controller name alone does not close it.

## Goodix fingerprint reader

The retained USB inventory identifies **Goodix 27c6:55b4**, bcdDevice `0100`, on internal **HS02**. USB enumeration already works. It does not establish image capture, enrollment, matching or login authentication.

[Apple's biometric architecture](https://support.apple.com/it-it/guide/security/sec067eb0c9e/web) performs Touch ID enrollment and matching within Secure Enclave, with an authenticated sensor connection. The Lenovo lacks that Apple hardware/pairing architecture. A generic USB driver or EFI identity patch does not provide a supported native Touch ID integration. No usable macOS driver for this exact sensor was established in the review.

There is real community support for the sensor on Linux: [libfprint-goodix55b4-milan](https://github.com/TheWeirdDev/libfprint-goodix55b4-milan/tree/aa42bb9816c3bc6d05960d420cf314e9f9b15679), reviewed at commit `aa42bb9816c3bc6d05960d420cf314e9f9b15679`. Its libfprint device implements capture, enrollment, verification and identification, and the documented build integrates libfprint/fprintd on Linux. It is not a macOS kext or a ready Touch ID component.

The driver's provisioning instructions overwrite the sensor's persistent pre-shared key and may replace firmware. The author documents loss of the current Windows pairing and instructs dual-boot users to disable the Windows fingerprint driver. This is a concrete incompatibility with silently including that provisioning in the existing dual-boot EFI setup. No provisioning command, firmware flash, biometric enrollment or authentication-policy change has been run.

A macOS userspace capture/matcher port would be separate development with separate authentication and dual-boot requirements. It must not be described as already supported, native Touch ID, or a completed EFI feature. Fingerprint behavior under Windows and the working macOS password login remain separate from this investigation.

## Consolidation boundary

Retain the working internal rEFInd/OpenCore/Windows boot arrangement and the confirmed audio, keyboard, USB, sleep and Low Power Mode results. The requested EFI consolidation follows the SD target result and an explicit record of unsupported features. Do not insert experimental NVIDIA code, fingerprint provisioning, untested SD variants or private machine identifiers into the public stable package.
