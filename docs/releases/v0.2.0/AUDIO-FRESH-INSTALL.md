## Audio is a separate installed component

**For onboard audio on a fresh macOS Tahoe installation, also download [S540-audio-Tahoe-3.6.10-v1.zip](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/releases/download/v0.2.0/S540-audio-Tahoe-3.6.10-v1.zip) and its SHA-256 checksum from this release.** Copying the EFI alone does not install the audio driver.

The companion package contains the unchanged **VoodooHDA 3.6.10 S540 driver**, previously tested for microphone and fine volume control. Its fresh-install wrapper is independent of the old Samsung installation and its `S540-microfono` backups. The existing working installation can retain its installed driver and backups.

Extract the complete folder into Downloads, then run:

```sh
bash "$HOME/Downloads/S540-audio-Tahoe-3.6.10-v1/INSTALLA-AUDIO.command"
```

If prompted, approve the driver in **System Settings > Privacy & Security**, then rerun the command. Follow the installer's restart instructions. After restarting, run:

```sh
bash "$HOME/Downloads/S540-audio-Tahoe-3.6.10-v1/VERIFICA-AUDIO.command"
```

The driver is installed in `/Library/Extensions/VoodooHDA.kext`. The installer requires the tested S540 audio configuration (`csr-active-config=03000000`, `voodoo-layout-id=11`) and no conflicting AppleALC/AppleHDA. It reads those settings without changing EFI, SIP or NVRAM. The package also includes a guarded removal command and its own instructions.

Archive integrity and installer state handling have been checked locally. **The new wrapper has not yet been validated by a native installation and reboot on the laptop.** Verify loading after reboot and test speakers, headphones and microphone before treating the new installation's audio as confirmed.

Original driver preparation and corrections are documented in the [Tahoe audio guide](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/blob/main/docs/guides/tahoe-audio.md), [microphone guide](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/blob/main/docs/guides/microphone-fix.md) and [volume guide](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/blob/main/docs/guides/volume-control.md).

