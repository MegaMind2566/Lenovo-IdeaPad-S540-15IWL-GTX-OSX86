# Stable EFI v0.2.0 recipe

This versioned recipe is the stable Intel-graphics EFI with native AirportItlwm Wi-Fi. `config.plist` is a public template: personalize its four SMBIOS identity fields before booting. The current owner's private working identity must be preserved locally.

- `payload-manifest.json` pins all 53 EFI files after public cleanup. All 52 non-config files are byte-identical to the supplied working EFI.
- `sources.lock.json` pins existing successful build artifacts, inner ZIPs and official assets. No new native compilation is required.
- `package-manifest.json` pins every distributed file except the manifest itself, including licenses, documentation, tools and Wi-Fi sources. Compressed ZIP hashes can vary between compression-library versions; the published sidecar identifies the uploaded ZIP.
- `builders/build_stable_efi.py` verifies inputs, assembles only the expected payload, checks every active reference and public identity, runs matching `ocvalidate` and writes the ZIP/checksum.
- `.github/workflows/publish-stable-efi.yml` publishes once from the dedicated release branch on Ubuntu, after checking the tag is absent. It verifies draft asset sizes/digests before publication. Drafts are located through the release collection and published by ID; the reviewed first attempt can be resumed only with the same target and unchanged verified assets.

Read the [release notes](../../../../docs/releases/v0.2.0/RELEASE-NOTES.md), [installation guide](../../../../docs/releases/v0.2.0/INSTALL.md) and [source provenance](../../../../docs/releases/v0.2.0/SOURCE-PROVENANCE.md). The older `config/efi/current` directory remains the original v0.1.0 assembly for its historical builder; it does not identify the latest release.
