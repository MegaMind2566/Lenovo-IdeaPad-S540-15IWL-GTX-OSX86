# EFI release packages

The current official non-NVIDIA release recipe is [v0.3.0](../../config/efi/releases/v0.3.0/README.md), built from the working internal S540 configuration. Its [installation guide](../../docs/releases/v0.3.0/INSTALL.md) explains the OC-only merge layout and separate audio/hotkey companions. The project remains in development; see the [hardware status](../../docs/status/hardware.md) for working, unsupported and unverified functions.

`config/efi/current` and `build-current-efi.yml` retain the original v0.1.0 source contract for historical reproducibility. They are not the v0.3.0 release recipe. Versioned release recipes and manifests are authoritative for their corresponding public assets.

The public payload contains placeholder SMBIOS identity and excludes Microsoft boot files, the fallback BOOT directory, rEFInd binaries and NVIDIA experiments. Preserve the source laptop's existing private boot setup when updating.
