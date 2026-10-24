# Installing the v0.3.0 non-NVIDIA OpenCore payload

This release targets the **Lenovo IdeaPad S540-15IWL GTX (81SW)** with i7-8565U/UHD 620, Intel AC9560, BOE NV156FHM-N61 display and O2Micro `1217:8621` SD reader, using the project's tested USB map and macOS Tahoe configuration.

**The package contains `EFI/OC` only.** It does not include `EFI/BOOT`, Microsoft boot files, a rEFInd executable, macOS or an installer image. Copying it to an empty USB drive does not create a complete boot device. New users must separately configure a UEFI entry that launches `EFI/OC/OpenCore.efi`, or install/configure rEFInd. The included rEFInd configuration is an example, not an automatic firmware installer.

## 1. Preserve the current boot path

Save a complete private backup of the current EFI partition and keep a known-working alternate boot route available. On an existing internal Windows/macOS installation, preserve these items:

- `EFI/Microsoft` and its Windows Boot Manager files.
- The existing `EFI/BOOT` directory and fallback executable.
- The working rEFInd installation, configuration and firmware boot entries.
- The existing private SMBIOS identity and separately installed macOS audio/hotkey components.

This release updates the OpenCore directory. It does not require formatting a disk, reinstalling macOS or replacing Windows boot files.

## 2. Personalize the public config

**Do not boot the public `EFI/OC/config.plist` with its identity placeholders.** The model is `MacBookPro16,2`. Set your own valid, unique `PlatformInfo → Generic` values for:

- `SystemSerialNumber`
- `MLB`
- `SystemUUID`
- `ROM`

For the same already-working laptop/installation, retain its known-working private identity locally. Keep those values out of public commits and reports. Other installations must use their own identity.

Preserve the remaining release settings and validate the edited config with **OpenCore 1.0.8**'s validator. Replacing the whole release config with an older file would discard its SD, native-Wi-Fi and boot-policy settings.

## 3. Mount the intended partition

Identify the current disks in Terminal:

```bash
diskutil list physical
```

Locate the EFI partition of the intended boot disk and mount that exact identifier:

```bash
sudo diskutil mount diskXs1
```

Replace `diskXs1` with the identifier from the current output. Disk numbers can change between sessions. On the tested laptop, Windows and macOS share the internal 512 GB Samsung NVMe; this does not make another user's `disk0s1` automatically correct.

## 4. Update only OpenCore

After the full backup and personalization, replace the intended partition's **`EFI/OC` directory** with the release's `EFI/OC`. Keep the bundled drivers, ACPI, kexts and config together instead of merging experimental files into the active directory.

The resulting OpenCore paths include:

```text
EFI/OC/OpenCore.efi
EFI/OC/config.plist
EFI/OC/ACPI/
EFI/OC/Drivers/
EFI/OC/Kexts/
```

Retain the existing native Windows/rEFInd route. OpenCore's `ScanPolicy=769` is intentional: Windows should be selected through its native path rather than receiving the macOS SMBIOS/ACPI environment. The rEFInd example uses relative paths on the same EFI volume; review it against the actual loader location before using it.

The config retains **`-wegnoegpu`**. Do not merge the separate NVIDIA-test configuration into this release. `AirportItlwm.kext` and `BigSurSDXC.kext` must remain paired with their included enabled entries and properties.

## 5. Keep or install macOS companions

**Audio:** the tested installation uses the **VoodooHDA 3.6.10 S540 variant in `/Library/Extensions`**, loaded through macOS's auxiliary collection. An EFI copy does not install this driver. Existing users keep their installed driver/backups. Fresh users need the separate audio package from the release assets and its own approval/restart/verification instructions. The release includes the unchanged [audio package](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/releases/download/v0.3.0/S540-audio-Tahoe-3.6.10-v1.zip) and its [checksum](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/releases/download/v0.3.0/S540-audio-Tahoe-3.6.10-v1.zip.sha256). [Audio](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/blob/v0.3.0/docs/guides/tahoe-audio.md), [microphone](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/blob/v0.3.0/docs/guides/microphone-fix.md) and [volume](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/blob/v0.3.0/docs/guides/volume-control.md) guides preserve the original driver history; use the procedure matching the installed variant.

**Hotkeys:** F4/F7/F9 use the separately installed **S540 Tasti 0.1.3** app and its matching driver, with the documented macOS permissions. Keep the working app/driver pair or use [S540-Tasti-v1.3.zip](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/releases/download/v0.3.0/S540-Tasti-v1.3.zip) and its [checksum](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/releases/download/v0.3.0/S540-Tasti-v1.3.zip.sha256). The EFI alone does not install it. The accepted F9 mapping also uses Command-L to lock; F8 camera disablement remains non-working. See [Function keys](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/blob/v0.3.0/docs/guides/function-keys.md).

**Power preferences:** the confirmed battery Low Power Mode setting is a macOS preference. It is not installed by this EFI payload.

## 6. Boot and recover

Use the preserved firmware/rEFInd route to start the intended OpenCore installation and select the existing macOS volume. The tested setup boots internally with the external test disk disconnected. Verify ordinary desktop operation and open an existing file on the known SD card.

If the OpenCore update fails, use the alternate boot route and restore the private `EFI/OC` backup. Keep the specific error for review. Preserve Windows and rEFInd while restoring OpenCore. An EFI update alone does not call for a blanket NVRAM reset or a macOS reinstall.

## Scope

The SD working result covers the source laptop's known **8 GB FAT32** card; insertion during an active session, mounting/unmounting and continued availability after sleep are also confirmed; writes, speed and arbitrary capacities are not newly validated. NVIDIA acceleration, fingerprint login and F8 camera disablement are not working features of this release. HDMI is unavailable, USB-C video remains unverified, and fan RPM telemetry is not exposed by the current configuration; this is not a physical fan-failure diagnosis. Read [RELEASE-NOTES.md](RELEASE-NOTES.md) for the full table.
