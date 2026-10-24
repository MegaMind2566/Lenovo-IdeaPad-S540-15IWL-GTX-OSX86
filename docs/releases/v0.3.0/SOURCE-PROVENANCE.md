# Sources and validation boundary for v0.3.0

This release is derived from the user-supplied **current internal non-NVIDIA EFI**, with the SD-only update subsequently applied and user-confirmed working. It is not a reissue of the external NVIDIA-test EFI.

## Working source configuration

The private internal config before the SD update has SHA-256 `1946b565014119923b5d0dafea987d55a021915dd021f57501fe3046893a1a06`. The applied internal config has SHA-256 `c3ca024b02f51c9a82ec85f833c65a3a669bdff1f539a0605f5edc6dbfe268dd`.

Removing the two SD additions from the latter recovers the complete original internal configuration semantically:

1. The enabled x86_64 `Kernel/Add` entry for BigSurSDXC, restricted to Darwin 25.
2. The existing external setup's SD `compatible` property at the verified PCI path.

All other internal settings, including ACPI, graphics, NVRAM, SMBIOS identity and `ScanPolicy=769`, were preserved during that personal update. The public release sanitizes private SMBIOS identity values and packages only the intended OpenCore payload. The public placeholders are not a new laptop identity or a tested login configuration.

## Exact SD inputs

| File | SHA-256 |
|---|---|
| BigSurSDXC executable | `dfb316e5e4ce745da6dbbb7470af1720e6719741e2a900aff3b3114e35060bd7` |
| Direct-match Info.plist | `d3dc9a76442bddf030389ea527045070a8e08153edb6b926ce3d60ddc70f4ae2` |

This is the previous **BigSurSDXC 1.9.0** binary with direct `pci1217,8621` matching. The executable is unchanged. It is not the separate S18R-disabled/3V3 candidate, and the successful SD report does not validate that candidate. The retained [SD record](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/blob/v0.3.0/docs/status/sd-fingerprint.md) preserves the negative trials, initialization trace, protocol analysis and later functional confirmations without treating them as interchangeable results.

The legacy binary is retained through the existing OpenCore injection path. It is not presented as having a newly valid Apple signature, and this packaging does not introduce a new security-setting change or a driver rebuild.

## Assembly inputs and archive contents

The assembly reuses three pinned archives; it does not compile replacement drivers:

| Archive | SHA-256 |
|---|---|
| S540-Tahoe-EFI-v0.2.0.zip | `659b1223c16b719a860c509571858b6685b0333b98c19222e480381fa601c039` |
| OpenCore-1.0.8-RELEASE.zip | `2011e8b7216ecb2645d97ea710df965947edd406846e92050b9bc4190be6d27b` |
| BigSurSDXC-v1.0.0.zip | `cae42ad863f5d4ae8a622ce1a9632f7268952fdeeb43306fe7f0d2be7275d3f8` |

The SD archive is pinned to [OpenCore Legacy Patcher f1d67923c827be2deebb1172333e7f0afb340583](https://github.com/dortania/OpenCore-Legacy-Patcher/blob/f1d67923c827be2deebb1172333e7f0afb340583/payloads/Kexts/Misc/BigSurSDXC-v1.0.0.zip). Its Info.plist changes only the reviewed `pci14e4,16bc` match to `pci1217,8621`, producing the exact direct-match hash above; its executable stays unchanged.

The archive contains **54 EFI/OC files**, including the public config. All **53 non-config active files** match the supplied current internal payload byte for byte. The public config prunes inactive entries and replaces private identity values; its SHA-256 is `1bb74df68623d72b37f669b70b5eb3b10c7b8f64642f46e9d145aed7bb9b9563`.

Current `sources.lock.json`, payload/package manifests, retained `source/base-v0.2.0-manifest.json`, `source/wifi/`, dependency notices under `LICENSES/`, matching `tools/ocvalidate` and `tools/ocvalidate.linux`, and `examples/refind.conf` document the assembled payload. Versioned config and locks are retained in `config/efi/releases/v0.3.0/` in the repository.

## Retained components

- OpenCore **1.0.8 RELEASE** is the active internal bootloader build.
- The native Wi-Fi driver remains the tested AirportItlwm **2.4.0** variant. Its source lineage and exact archive records are retained from the previous release's [provenance](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/blob/v0.2.0/docs/releases/v0.2.0/SOURCE-PROVENANCE.md); this release does not substitute a newer radio driver.
- Brightness, USB, Intel graphics, Bluetooth and power-management components follow the supplied current internal EFI. The package manifests and source locks record the actual included files and hashes.
- NVIDIA remains disabled by `-wegnoegpu`; experimental NVIDIA packages are not included.
- VoodooHDA **3.6.10 S540** and S540 Tasti **0.1.3** are macOS-installed companions. Their working behavior is not supplied by copying `EFI/OC` alone.

The package omits Microsoft boot files, the existing `EFI/BOOT` fallback executable and the rEFInd binary. The example rEFInd configuration documents the tested loader arrangement without redistributing the user's complete EFI partition.

## Evidence categories

| Evidence | What it establishes |
|---|---|
| Source/archive and semantic comparison | Exact SD inputs and the limited personal config delta |
| OpenCore 1.0.8 validation and package checks | Config structure, expected files, hashes and public-identity sanitization |
| Native personal installation and recursive diff | New config/kext bytes verified; Windows/rEFInd and other pre-existing files unchanged apart from the config's macOS metadata companion |
| Latest user confirmation | SD operation from the updated internal non-NVIDIA setup after an earlier negative result, plus insertion during an active session, mounting/unmounting and availability after sleep |
| Existing functional confirmations | The hardware table's stated audio, network, input, display, USB and power/sleep observations |

These results do not establish every card capacity, SD writes/speed or arbitrary card classes, all storage/cooling workloads or NVIDIA acceleration. The repository remains **in development**.
