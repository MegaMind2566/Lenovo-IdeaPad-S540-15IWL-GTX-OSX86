> The latest stable package is [EFI v0.2.0](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/releases/tag/v0.2.0), with [installation instructions](../../docs/releases/v0.2.0/INSTALL.md) and a [versioned recipe](../../config/efi/releases/v0.2.0/). The v0.1.0 assembly below is retained as history; it predates the native Wi-Fi and hardware-name integration.

# S540 macOS Tahoe EFI — v0.1.0

Current OpenCore configuration for the **Lenovo IdeaPad S540-15IWL GTX (81SW)**, Intel Core i7-8565U, UHD 620 and Intel AC9560. See `COMPATIBILITY.md` for hardware status.

## Package contents

- `EFI/`: OpenCore 1.0.8 DEBUG, enabled ACPI tables, UEFI drivers and kernel extensions.
- `manifest.json` and `SHA256SUMS`: component sources and integrity hashes.
- `LICENSES/`: upstream license notices.

The package preserves the working Intel graphics, framebuffer memory and startup backlight settings, including `-igfxblr`. It excludes trial configurations, private backups, disabled components, saved Wi-Fi networks and personal SMBIOS identifiers. Verbose boot and the existing debug settings remain enabled.

## Before booting

1. Keep your existing working boot device available.
2. Generate your own SMBIOS identity for **MacBookPro16,2**. Fill `PlatformInfo → Generic → SystemSerialNumber`, `MLB`, `SystemUUID` and the six-byte `ROM` in `EFI/OC/config.plist`. The shipped values are intentionally empty or zero; do not use another machine's identity.
3. Validate your personalized configuration with **ocvalidate 1.0.8**.
4. Copy the `EFI` directory to the EFI System Partition of the intended external boot device. Do not replace the internal Windows boot files.
5. Boot that device in UEFI mode. Use **HeliPort** to select your wireless network; no Wi-Fi credentials are included.

This is a hardware-specific configuration. It does not include macOS or an installer image.

## Components outside the EFI

**Audio:** the working system uses the project's VoodooHDA S540 variant 3.6.9 in `/Library/Extensions`, including the microphone input-gain correction. This extension is not installed by copying this EFI. The existing audio and microphone tools describe installation and upgrades with their original rollback state; they are not a fresh-install bootstrap for this public EFI. The microphone driver is built separately by the repository's audio workflow.

**Bluetooth:** the working system also has these Apple NVRAM values under `7C436110-AB2A-4BBB-A880-FE41995C9F82`: `externalDongleFailed` is one zero byte and `internalControllerInfo` is fourteen zero bytes. They are not added by this snapshot's configuration. A system without that existing state requires Bluetooth setup; copying the EFI alone does not establish identical Bluetooth behavior.

**Wi-Fi:** itlwm exposes an Ethernet-style network interface. Wireless selection is handled by HeliPort, rather than the native macOS Wi-Fi menu.

## Source and maintenance

Project: https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86

The repository tracks the public configuration, custom ACPI/USB files and immutable upstream dependency hashes. The release workflow reconstructs the EFI and checks every component against the manifest, then validates the configuration with OpenCore's matching validator.

