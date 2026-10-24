# SD reader and fingerprint scope

Updated on **24 October 2026**. SD card operation is now user-confirmed on the external direct-match setup. Preparation of its promotion into the **official internal non-NVIDIA EFI** is authorized and recorded below; installation and internal-boot SD verification remain pending. The user has marked the fingerprint reader **NOT WORKING in macOS** and stopped further fingerprint work. NVIDIA, HDMI and the accepted non-working F8 camera toggle remain outside this work.

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

The earlier outcome was **no confirmed macOS SD reading**; the later user-confirmed result with the previous kext is recorded below. At that earlier stage, the reviewed external direct-match trial has now attached successfully but produced no SD media; see the target result below. Acceptance still requires actual readable media. A successful load or controller name alone does not close it.

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

The user subsequently confirmed that the tested card is **8 GB, formatted FAT32, and readable under Windows**. Under macOS it does not appear among detected disks, matching the report's absent IOMedia/disk result. The published failure with cards above 32 GB does not explain this 8 GB case. Reformatting is not an evidence-based next step: media publication has failed before filesystem mounting. This does not yet identify a reset, clock, command, interrupt or vendor-initialization fault.

The reviewed driver stores the published clock-divisor property in an 8-bit field. Its initial divisor may be `0x200`, which is truncated to `0` in that property; publication also precedes the hardware-stable check. Therefore neither the reported zero nor the requested bus-voltage property is a physical measurement or a reason for a blind clock patch. Further work needs the first initialization error and its contemporaneous state before cleanup; another late matching/registry snapshot would repeat the current limitation. The raw report remains private. This result update changes documentation only; it does not modify either EFI or the retained NVIDIA trial, and starts no build or CI.

### Initialization trace package and external references — 24 October 2026

The user authorized one guided SD initialization trace on the existing external test setup. `S540-SD-Init-Trace-v1.zip` is a userspace diagnostic; no new kext, SSDT, config.plist, boot argument or NVIDIA setting is included. Archive SHA-256: `40cd3fc251c26ec0351c3fc0553ae82c2e3d4b4ed46aebfbca18814d12703501`.

The program uses the reviewed 16-byte binary `debug.SDXC` protocol, preserving all 64 bits (including tuning) and temporarily ORing only trace bit `0x2`. Cleanup attempts restoration and verifies readback. Existing foreground traces are refused; an OS-managed background trace can hand off normally. Only its own ktrace child is signalled; no global reset/remove or other-process termination is issued. Abrupt uncatchable process termination is not a guaranteed restoration path.

A removal must be confirmed both by the slot property and the matching card-absent trace event before reinsertion is requested. Missing/unknown logging, CLI, schema or permissions is inconclusive and cannot be treated as SD incompatibility. Only eight selected SD event fields are retained; command arguments, CID/CSD responses, kernel pointers and unrelated system events are excluded. Nonzero returns may be handled retries, so the recorded sequence still requires interpretation.

Native [run 40085526902](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/actions/runs/40085526902) passed compilation, ad-hoc signature verification, 21 hardware-free checks and a real synthetic ktrace capture. Its actual NDJSON format passed the delivered parser using an explicitly translated fixture. These are tool-validation results, not a target SD result. Source parent: `bd5ffa067d32b5b05badab040461c0b96fcf53f0`; request: `fc68c6970d2df2bd603fbb81c927049a5b91a0c2`; helper source SHA-256: `3ffd9fba24b5e04578674426f0a6e11d36d37debb830284758cd94357d779563`. The first native attempt stopped on an undeclared probe API; the corrected source uses the documented ktrace CLI. It was not an unchanged-source retry. The user explicitly allowed this SD validation in parallel with the already active NVIDIA build as a one-off exception; no NVIDIA job or request was changed or cancelled.

The user also supplied two upstream repositories:

- [BA4RQZ/SSDT-O2SD-Fix, pinned DSL](https://github.com/BA4RQZ/SSDT-O2SD-Fix/blob/53b3bea4c4ab88e0a05504499bc46300e7d5d9e2/SSDT-O2SD.dsl) is a useful vendor-initialization reference for **8520/FUJIN2**. It is not a ready 8621 patch. [Linux v6.12's SEABIRD1 branch](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/mmc/host/sdhci-pci-o2micro.c) instead tests the PLL high byte, selects high PLL bits `1F340000` or `25100000`, uses tuning `55`, updates `F0` and `324`, and relocks write protection. Merely changing the SSDT path would retain the wrong sequence. The supplied DSL also lacks Darwin/device-ID admission and a chain to any existing firmware _INI; its author reports sleep/hotplug limitations. No AML or pmset workaround was applied.
- [lucatek/Lenovo-Ideapad-S540-15IWL-Hackintosh](https://github.com/lucatek/Lenovo-Ideapad-S540-15IWL-Hackintosh) names the same 81SW laptop family, but its README specifies **Realtek RTS522A + Sinetek-rtsx** under Catalina/Clover. That working-reader claim does not establish support for this O2Micro controller. Its sleep configuration is not copied into the already working current setup.

The subsequent guided trace and later user-confirmed card operation are recorded below; this paragraph describes the state before those results.

### Target trace result and S18R-disabled candidate — 24 October 2026

The supplied initialization report contains **369 selected events** and 222 ignored non-whitelisted events, with no unknown schema or input-limit condition. Original debug flags were zero and restoration readback was verified. The result remains `INCONCLUSIVE` for its removal/reinsertion control: no matching card-absent event/slot state was confirmed, and the reinsertion stage was not reached. A false final slot sample is not proof that the card was never physically removed. The collector's elapsed values are buffer-read times, not kernel event timestamps.

The captured sequence is nevertheless useful: initial CMD55/ACMD41 completions succeed, then CMD11 completes, clock divisor 4 is recorded with Clock Control `0x407`, and ConfigureSDMedia returns `0xE00002BC`. In the reviewed binary, this matches the later 1.8 V switch path and its unsuccessful DAT-line check. DAT values were not retained, so the trace does not prove physical voltage or a specific electrical fault.

Across the selected sequence, 47 wait operations report success and 41 report `0xE00002BC`: 38 follow CMD8 and three follow CMD55. Error Interrupt Status `0x0004` is Command End Bit Error, distinct from CRC or timeout. All 90 recorded command/data resets return zero. Four ConfigureSDMedia exits report the error; the final CMD8 has no captured completion, so no final ConfigureCard outcome can be assigned. Reported divisor zero remains compatible with a full requested divisor 512 truncated by the driver's published byte field.

A targeted external-only candidate now avoids requesting the 1.8 V transition: **S18R is zeroed at both ACMD41 request/polling sites**, retaining HCS, XPC and the voltage-window argument. At x86_64 VM `0x98CF` and `0x9955`, each `41 0F 94 C0` becomes `45 31 C0 90` (`xor r8d,r8d; nop`). Independent disassembly review verified that R8 supplies ACMD41 bit 24. It is a protocol negotiation trial, not a forced electrical-voltage guarantee or a confirmed repair. `UHS Mode=false` would not avoid the earlier switch and is not used.

`S540-SD-3V3-v1.zip` SHA-256: `c41899c40cd768f5ebeeb6c29428bcefb03cd959539dc97ecc704096fb6ff49f`. Candidate executable SHA-256: `6327de1f1d81d354821c5eb2acc546ac02cd6df724f1c09688189297abfd404f`. Runtime UUID: `857CC249-3CDC-5511-82DD-B38C034EB7E6`. The x86_64 LC_UUID is stamped separately so a passive loaded-driver report can distinguish this code from the original UUID `D2EAAA60-AF10-360F-B645-1592B9B3A804`.

Exactly 24 file bytes differ: eight instruction bytes and 16 UUID metadata bytes. FAT layout, non-UUID load-command bytes, ARM slice and embedded signature blob are unchanged. The input already fails eight of 33 embedded CodeDirectory page hashes; the candidate fails those plus pages 0 and 9. Neither is presented as having a valid Apple signature, and no resigning or security-setting change was performed. The trial retains the existing OpenCore injection path; target admission and card reading still need the next boot.

The package contains the candidate, exact direct-match baseline for rollback, manifest/checksums and a passive Bash-only collector that checks the new runtime UUID and selected slot/disk fields. All eight ZIP members and seven checksums, permissions, rollback bytes, changed-byte set, Mach-O structure and collector syntax passed independent review. The private raw report and driver binaries are not committed here; the [builder recipe](../../builders/build_sd_s18r_candidate.py) uses exact local input hashes. No native compilation or new GitHub workflow was needed for this fixed-byte package.

Only replace BigSurSDXC in the **external** EFI, then shut down, remove/reinsert the card while off and boot externally with the known 8 GB FAT32 card inserted. Configuration, ACPI, internal EFI and the NVIDIA experiment remain unchanged. Acceptance is an actual SD disk and an existing readable file. **Target result for this candidate is pending.**

### User-confirmed reading with previous kext — 24 October 2026

The user now reports that the SD card works, and immediately clarifies that this result uses the **previous kext, not the S18R-disabled / 3V3 candidate**. This supersedes the earlier no-readable-media outcome for the user's current external setup. The successful report must not be attributed to the new 3V3 binary or used as validation of its voltage-negotiation change.

Exact active bundle/configuration identity still needs to be captured before promotion: the original alias-match and direct-match variants share the same executable and original UUID, so loaded-binary identity alone does not distinguish their Info.plist. The report establishes user-observed card operation; hotplug, post-sleep operation, write validation and transfer performance have not been newly established.

The user has authorized preparing an update of the **official internal EFI** using this successful SD setup. This extends the earlier external-only trial scope for that specific promotion. No internal update has yet been applied. The current internal configuration and the actually working external SD bundle/settings must be compared before packaging; do not copy the external NVIDIA experiment or replace the current internal configuration with the older release. Preserve SMBIOS identity, rEFInd, Microsoft boot files and all unrelated settings. The S18R-disabled candidate is excluded from this promotion.

### Verified inputs for internal SD promotion — 24 October 2026

The newly supplied current internal and external EFI archives have now been compared. The working external archive confirms the **previous direct-match variant**: Info.plist SHA-256 `d3dc9a76442bddf030389ea527045070a8e08153edb6b926ce3d60ddc70f4ae2`, executable `dfb316e5e4ce745da6dbbb7470af1720e6719741e2a900aff3b3114e35060bd7`, and external config `bb51139e85f3ba102b551694fc51289291b444f0a09ef88ad69b3dc71d7f7a3e`. It contains neither the S18R-disabled executable nor its new UUID. The user-confirmed SD success is associated with these supplied external inputs; no new runtime report is implied by this archive audit.

The current internal EFI uses OpenCore **1.0.8 RELEASE**, has no SD entry or SD device property, and retains the native-Windows/rEFInd route with ScanPolicy **769**. The personal update therefore adds only the byte-identical external BigSurSDXC bundle, its exact Kernel/Add entry and the exact SD `compatible` field at the already reviewed PCI path. Semantic comparison after removing those two config additions recovers the entire original internal config. SMBIOS, ACPI, NVRAM, graphics and all other existing settings are unchanged. OpenCore 1.0.8 ocvalidate reports no issues.

A guarded installer and explicit restore command are packaged as `S540-SD-Interno-v1.zip` (SHA-256 `3b98fc7c96477c8c13122f358169439531edcc1560f9e80fb168ee734ec5eeea`), with a full verified EFI backup before writes. The installer compares all current non-SD files against that operation's backup before and after the change, so legitimate Windows BCD/log changes between operations are retained. Eight local mocked filesystem scenarios passed, including interrupted commit, partial restoration, unknown-state refusal and preservation of updated Windows BCD. These are simulated shell checks, not native Mac installation results. `-wegnoegpu` remains present, enabled NVIDIA kext entries remain zero and ACPI is identical, as explicitly requested. They do not replace the internal EFI with the external NVIDIA configuration. The personal config and Windows boot files remain private, and the existing public v0.2.0 release asset is not silently replaced. **Internal installation, reboot and SD operation on that internal boot remain pending target verification.**

### Internal installer size guard correction — 24 October 2026

The first internal installer attempt stopped during target admission, before backup, staging or EFI-file changes. Its partition-size guard incorrectly used `diskutil info`'s `TotalSize`, reported as **313946112**, while the user-supplied partition table confirms `disk0s1.Size = 314572800`. This is an installer field-selection error, not an SD-driver failure or a changed GPT extent.

`S540-SD-Interno-v1.1.zip` supersedes that installer (SHA-256 `a8799e7cf7c7f0e5aaf44a3ff201f6fc4ddca780ad8e78f69316eb84913f3c3d`). The corrected guard reads the partition-table size, checks whole/partition device identifiers, EFI content and the observed GPT partition GUID, and repeats those checks before committing. The whole-disk size check remains intact. Config, driver and command wrappers are byte-identical to v1; config staging uses `cp -X` to avoid propagating extended attributes into the ESP. NVIDIA stays inactive in the internal configuration.

The corrected admission is covered by the actual **313946112 / 314572800** fixture, wrong partition size/device/content/GUID/root-device refusals and a changed-GUID refusal at the second read, alongside the prior install/restore/interruption cases. These are local simulated checks. **The corrected native installation, internal reboot and internal-boot SD result remain pending.**

## Goodix fingerprint reader

**Status: NOT WORKING in macOS. Further fingerprint investigation stopped by user request on 24 October 2026.** The findings below are retained as the explanation of the limitation, not as an active development plan.

The retained USB inventory identifies **Goodix 27c6:55b4**, bcdDevice `0100`, on internal **HS02**. USB enumeration already works. It does not establish image capture, enrollment, matching or login authentication.

[Apple's biometric architecture](https://support.apple.com/it-it/guide/security/sec067eb0c9e/web) performs Touch ID enrollment and matching within Secure Enclave, with an authenticated sensor connection. The Lenovo lacks that Apple hardware/pairing architecture. A generic USB driver or EFI identity patch does not provide a supported native Touch ID integration. No usable macOS driver for this exact sensor was established in the review.

There is real community support for the sensor on Linux: [libfprint-goodix55b4-milan](https://github.com/TheWeirdDev/libfprint-goodix55b4-milan/tree/aa42bb9816c3bc6d05960d420cf314e9f9b15679), reviewed at commit `aa42bb9816c3bc6d05960d420cf314e9f9b15679`. Its libfprint device implements capture, enrollment, verification and identification, and the documented build integrates libfprint/fprintd on Linux. It is not a macOS kext or a ready Touch ID component.

The driver's provisioning instructions overwrite the sensor's persistent pre-shared key and may replace firmware. The author documents loss of the current Windows pairing and instructs dual-boot users to disable the Windows fingerprint driver. This is a concrete incompatibility with silently including that provisioning in the existing dual-boot EFI setup. No provisioning command, firmware flash, biometric enrollment or authentication-policy change has been run.

A macOS userspace capture/matcher port would be separate development with separate authentication and dual-boot requirements; it is not part of the requested remaining work. No further fingerprint package, test, firmware change or login-policy integration is planned. Fingerprint behavior under Windows and the working macOS password login remain separate from this result.

## Consolidation boundary

Retain the working internal rEFInd/OpenCore/Windows boot arrangement and the confirmed audio, keyboard, USB, sleep and Low Power Mode results. Prepare and test the SD delta only on the reviewed external EFI, preserving its existing NVIDIA experiment as explicitly requested. The requested EFI consolidation follows the SD target result, with fingerprint authentication explicitly recorded as not working. Do not insert experimental NVIDIA code, fingerprint provisioning, untested SD variants or private machine identifiers into the public stable package.
