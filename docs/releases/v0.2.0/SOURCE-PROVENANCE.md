# Exact sources for EFI v0.2.0

This package preserves all 52 non-config EFI files from the supplied working EFI. Its public config changes only SMBIOS identity placeholders and removal of inactive AppleALC, IntelBTPatcher, itlwm and SSDT-DGPU-OFF entries. Removing the old inactive itlwm bundle also excludes its private saved network configuration. Finder metadata is excluded.

The packager does not compile drivers or substitute newer versions. It reconstructs those exact bytes from:

- The verified [v0.1.0 build](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/actions/runs/38497385533), commit `78f664c3ecd996c4472be75f76cdaff07303f8f5`, artifact `11864172878`.
- The verified [native Wi-Fi build](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/actions/runs/39171971175), commit `38e387cd152853033ee25697e8528b5f9399faae`, artifact `12153335295`.
- The official [BrightnessKeys 1.0.3 release](https://github.com/acidanthera/BrightnessKeys/releases/tag/1.0.3).

Outer archive hashes, inner ZIP hashes, lengths and source commits are recorded in `sources.lock.json`. The complete public package hashes are in `manifest.json`; the inherited upstream versions and URLs are also preserved in `source/base-v0.1.0-manifest.json`. License and firmware notices are under `LICENSES/`. USBToolBox and HfsPlus retain the upstream licensing notices and limitations documented there.

AirportItlwm comes from [laobamac/itlwm at 738d4c61b5a64433b27c1ab09dba94916ab77d8d](https://github.com/laobamac/itlwm/tree/738d4c61b5a64433b27c1ab09dba94916ab77d8d). Its exact source archive, MacKernelSDK archive, original builder and source lock are included in `source/wifi/`. They are taken unchanged from the successful Wi-Fi build package. Reproduction requires its documented macOS/Xcode build environment; the stable-release packaging workflow runs only on Ubuntu and reuses that successful build.

The original OpenCore 1.0.8 DEBUG boot payload is retained. Matching OpenCore 1.0.8 validators are supplied separately under `tools/` from the pinned official RELEASE tools archive. A RELEASE validator does not change the boot payload's DEBUG build identity.

To reproduce the public ZIP from a checkout of this release with authenticated access to this repository's retained artifacts:

```bash
GITHUB_REPOSITORY=MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86 \
  python3 builders/build_stable_efi.py --download
```

The publication path refuses an existing tag or release. For later local reproduction, download the four pinned input archives into `build/stable-inputs` and run the builder without `--download`. This bypasses the publication guard, while retaining every input, payload and final package hash check. The ZIP has fixed timestamps and modes for reproducibility.
