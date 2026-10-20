# Installing EFI v0.2.0

This is the stable **non-NVIDIA EFI for the Lenovo IdeaPad S540-15IWL GTX (81SW)** running macOS Tahoe. It is an EFI package, not a macOS installer or a complete audio installer.

The tested configuration uses Intel Core i7-8565U/UHD 620, Intel AC9560, the BOE NV156FHM-N61 panel and the project’s USB map. macOS boots from the external Samsung 960 EVO; Windows remains on the internal PM981a. Other hardware revisions and SSD models are not automatically covered by these results.

## 1. Preserve the working installation

Keep a complete private backup of the current boot EFI before replacement. Retain a separate known-working boot/recovery device so the previous EFI remains available if needed.

Keep the existing macOS installation, audio driver and companion backups. Installing this EFI does not require reinstalling macOS or formatting either SSD.

## 2. Personalize the public config

**The public `EFI/OC/config.plist` contains placeholder SMBIOS identity values. Do not boot it unchanged.**

The configured model is `MacBookPro16,2`. Set your own valid, unique values in `PlatformInfo → Generic` for:

- `SystemSerialNumber`
- `MLB`
- `SystemUUID`
- `ROM`

If this is the same laptop and macOS installation already working with a private EFI, preserve its known-working private identity. Transfer those identity fields into the release config locally; do not replace the working identity with the public placeholders or publish the private values. Other installations must generate and use their own identity.

Retain the release’s other settings rather than replacing the whole release config with an older config. A replacement with the old file would also discard the included Wi-Fi and naming changes. Validate the edited config with the matching OpenCore validator before installation.

## 3. Mount the intended EFI partition

Identify the boot disk in Terminal:

```bash
diskutil list
```

Locate the EFI partition belonging to the intended macOS boot disk. Disk numbers are assigned dynamically: use the current output, not an identifier copied from another session.

Mount that exact partition, replacing `diskXs1` with its actual identifier:

```bash
sudo diskutil mount diskXs1
```

Use the mounted volume belonging to that disk. Keep the Windows EFI and the separate 240 GB test EFI intact.

## 4. Install the complete release EFI

After saving the private backup and personalizing the config, copy the release’s complete `EFI` directory to the intended EFI partition. Replace the backed-up boot EFI as a complete directory rather than merging files from experimental packages.

The resulting paths must include:

```text
EFI/BOOT/BOOTx64.efi
EFI/OC/OpenCore.efi
EFI/OC/config.plist
EFI/OC/ACPI/
EFI/OC/Drivers/
EFI/OC/Kexts/
```

`AirportItlwm.kext` must remain paired with its enabled config entry as the active Wi-Fi path. Use the provided driver variant and configuration together. Do not enable `itlwm` alongside it or add the separate NVIDIA or SD experimental packages as part of this stable installation.

## 5. Retain or install the separate audio component

The working audio path uses the **VoodooHDA 3.6.10 S540 variant in `/Library/Extensions`**, loaded through macOS’s auxiliary collection. It is not installed by copying files into `EFI/OC/Kexts`.

On the existing working macOS installation, retain that installed driver and its private backups. The EFI update does not replace them. AppleALC is omitted from this package.

On a fresh macOS installation, audio needs its separate preparation, driver installation and any macOS approval/reboot steps. Consult the project’s [Tahoe audio](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/blob/main/docs/guides/tahoe-audio.md), [microphone correction](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/blob/main/docs/guides/microphone-fix.md) and [volume-control](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/blob/main/docs/guides/volume-control.md) guides. The correction packages assume an existing compatible audio installation and backups; they are not standalone fresh-install procedures. Use the verify/restore procedure matching the installed variant, not an older rollback helper against 3.6.10.

## 6. Boot and recover

Restart and select the intended external boot disk in the firmware boot menu, then select the existing Tahoe installation in OpenCore. Keep the external macOS disk connected while macOS is running.

If startup fails, use the preserved working boot route and restore the complete private EFI backup. Keep the failure message for review. An EFI replacement alone does not call for a blanket NVRAM reset or a macOS reinstall.

The established working features and remaining F4–F10, SD, fingerprint, HDMI and NVIDIA limitations are listed in [RELEASE-NOTES.md](RELEASE-NOTES.md).
