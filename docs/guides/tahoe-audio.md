# ALC257 audio on Tahoe

This guide documents the original audio setup and its private rollback backups on the project's existing installation. It is not a complete fresh-install procedure for an EFI release. An EFI archive alone does not include the installed audio extension or these backups. The subsequent microphone upgrade is covered in the [microphone correction guide](microphone-fix.md).

## Initial audio state: October 13, 2026

On the working desktop, `system_profiler SPAudioDataType` returns Audio/Devices with no devices. The kext check shows Lilu 1.7.2, but neither AppleALC nor AppleHDA. The EFI retains AppleALC 1.9.8 with MaxKernel 24.99.99, excluding it on Darwin 25. The Windows report already confirms the Realtek ALC257 codec; another collection is unnecessary.

Tahoe removed AppleHDA. Extending AppleALC's MaxKernel limit alone does not restore the audio stack. The AppleHDA approach documented in the sources requires a KDK and changes to the system volume. The initial setup instead uses VoodooHDA in `/Library/Extensions`, through the auxiliary kext collection, retaining the sealed system volume.

## SIP check correction: package v2

The first preparation on the laptop passed the EFI, driver, and HDAS checks, then stopped before writing a backup or config. `csrutil status` and the targeted NVRAM read showed a custom configuration: Data `ZwIAAA==`, corresponding to bytes `67020000` and mask `0x267`. The config instead contains Data `00000000`. The original check incorrectly assumed these values had to match.

Package v2 stores the initial NVRAM value as `OriginalSip` in the format 2 backup. During rollback, it reinjects this value before restoring the config's original bytes. OpenCore 1.0.8 does not overwrite an existing Add variable: the original config can therefore return to zero while NVRAM retains its initial `67020000`. This path requires WriteFlash=true, LegacyOverwrite=false, and no csr-active-config entry in the original Delete list; the program verifies these conditions for the nonzero case. NVRAM is not reset.

Read errors, a type other than Data, a length other than four bytes, or an unverified initial value stop the procedure. Format 1 backups remain unchanged and require the original program for rollback. The failed attempt had not yet created that backup.

## Driver and configuration changes

The package contains the three original files from the VoodooHDA 3.6.8 bundle in the stable Release368 release, checked against the official asset's SHA-256 and the individual file manifest. The binary is x86_64 and has an ad hoc signature without a Developer ID certificate. The package does not modify or re-sign this original bundle.

The bundle matches the HDAS name. The Lenovo's original DSDT contains HDAS at PCI 1F.3; the program also checks that the device exists in the running system. The driver includes pin configuration for ALC257/layout 11 and accepts `voodoo-layout-id=11` in the boot arguments. This supports the initial choice but does not establish that every port works on the laptop.

Preparation changes only:

- `csr-active-config` in the config from Data `00000000` to `03000000`, as specified by the Tahoe VoodooHDA guide. Preparation accepts the verified original NVRAM value `00000000` or `67020000` and saves it separately as Data in the backup. Compared with `67020000`, the trial mask reduces the permissions already granted. Authenticated root is not disabled.
- The NVRAM/Delete list, to reinject this value at the next boot.
- AppleALC/Enabled to false, keeping the two audio paths separate.
- The `voodoo-layout-id=11` argument, preserving the other boot arguments.

The Whiskey Lake pair and the three memory-correction properties remain unchanged. The program preserves the current EFI; it does not rebuild the identity, ACPI, Bluetooth, or Wi-Fi profile. It installs no preference panes or additional services.

## Volume correction result: October 13, 2026

After package v3, audio playback, gradual volume changes, and F1–F3 were reported working. The issue where volume changed audibly only at zero/mute was resolved on the laptop. This configuration is retained. No new technical verification output was supplied; this result does not establish analog jack, microphone, or sleep support.

## Voice capture and gain: October 14, 2026

The Photo Booth video captured voice together with the webcam image. Microphone gain was excessive: adjusting it in settings abruptly changed the level from too high to too low. Audio capture was available; the selected input and IOAudio controls still needed checking. In the pinned source, VolumeChangeFix updates every mixer even when the input changes. This was a possible cause to distinguish from the laptop's actual amplifier configuration. At this stage, no new driver patch was applied; equalization and function-key work remained deferred.

The next report identifies the default input as Internal Microphone VoodooHDA, with two channels at 48 kHz. Left and right controls are both at 57 out of 100, with a declared 0–30 dB range. Speakers are at 100, with a declared −21.5–0 dB range. These ranges do not reveal the codec's actual steps. A [two-level mixer snapshot](microphone-diagnostics.md) was therefore needed before selecting a driver change. The speaker-volume correction remained active.

The first microphone collection stopped at its binary check: it required the original full-file hash, while re-signing the V3 volume variant also updates the Mach-O binary. Collector v2 recognizes the variant through `VolumeManifestHash` and the three-file manifest in the `volume-test` backup. It checks the retained original, retained variant, installed bundle, and single plist change. It does not change the config, driver, backup state, or signature. At this stage, the laptop's mixer snapshots were still pending.

The subsequent v2 collection succeeded. With input at 30% and 70%, all cached mixers in both the input and output tabs change to 30 and 70 respectively, while the IOAudio output volume remains at 100. The initialization buffer confirms ALC257 microphone pin 18 with four boost levels, 0/10/20/30 dB, and ADC 8 with 64 levels from -17.25 to +30 dB in 0.75 dB steps. The two initialization buffers are identical; they are not hardware readbacks taken after each slider movement.

The [microphone correction](microphone-fix.md) uses S540 variant 3.6.9: input on the ADC's RECLEV, fixed 0 dB boost, and the existing output PCM correction. The all-mixer loop is bypassed only after checking the expected controller and codec graph. Installation and rollback use a separate backup on the Data volume and do not change the EFI containing `-igfxblr`. Recording quality on the laptop requires verification after installing the correction.

## Equalization: future work

Equalization refinement is deferred. It remains a separate sound-character task in the roadmap; no further mixer, amplification, or driver changes are introduced for it here.

## Volume control: package v3

After package v2, audio playback and F1, F2, and F3 were working. Gradual volume control was still ineffective: the sound changed only when volume reached zero/mute. Headphones/analog jack and microphone had not been documented separately.

In the VoodooHDA 3.6.8 source, `VoodooHDAEnableVolumeChangeFix` forwards the value to the PCM mixer and the other mixer controls. With the flag false, output changes are forwarded to the VOLUME master, which may not control the codec's effective gain. The flag is read during device initialization, so updating the driver and rebooting are required to evaluate it.

Package v3 changes only `IOKitPersonalities.VoodooHDA.VoodooHDAEnableVolumeChangeFix` from false to true. HalfVolumeFix, HalfMicVolumeFix, MuteFix, Boost, the initial PCM level, and the other settings remain unchanged. Because the bundle signature seals the plist, the modified copy is re-signed ad hoc and verified on the Mac. An unsigned modified driver is not supplied.

### Upgrading an installation with working audio

Extract **S540-audio-Tahoe-v3.zip** into Downloads, then run:

```sh
bash "$HOME/Downloads/S540-audio-Tahoe-v3/VOLUME-AUDIO.command"
```

The program uses the existing format 2 audio backup, verifies the installed driver, saves a complete copy, and prepares the variant in a temporary folder. Replacement occurs only after checking the files and signature. It does not change the config, SIP, or Intel settings. It requests an AuxKC rebuild with `kmutil rebuild`: follow any macOS approval prompt and reboot. Do not unload/load the driver while the system is running for this trial.

After rebooting, run:

```sh
bash "$HOME/Downloads/S540-audio-Tahoe-v3/VERIFICA-AUDIO.command"
```

Check the flag exposed in IORegistry. With the same content playing, compare volume at about 25%, 50%, and 100%, then mute. Check both F2/F3 and the macOS volume slider. Successfully writing the plist alone does not establish gradual attenuation.

To restore the previous driver while retaining installed audio:

```sh
bash "$HOME/Downloads/S540-audio-Tahoe-v3/ANNULLA-VOLUME-AUDIO.command"
```

Reboot as instructed. To remove the entire audio setup, use **RIPRISTINA-AUDIO.command from package v3**: it recognizes both the original driver and the volume variant created and verified by this procedure. The older v2 commands check only the original files and would stop when encountering the variant.

## Original installation procedure from macOS

First retain the private working-EFI backup described in the [Intel graphics guide](intel-graphics.md). Download **S540-audio-Tahoe-v3.zip** and extract it into Downloads. The package creates the **S540-audio-Tahoe-v3** folder. The OpenCore volume must be mounted as **240 GB**; if it has another name, pass its actual path as the command's only argument.

1. Prepare the EFI:

   ```sh
   bash "$HOME/Downloads/S540-audio-Tahoe-v3/PREPARA-AUDIO.command"
   ```

   Wait for successful preparation, then reboot from the same OpenCore HDD and select the Samsung containing Tahoe.

2. Install the driver after rebooting:

   ```sh
   bash "$HOME/Downloads/S540-audio-Tahoe-v3/INSTALLA-AUDIO.command"
   ```

   The program checks the active SIP state, prepared config, and driver. Enter the password in Terminal when sudo requests it; typed characters are hidden. The bundle is copied to `/Library/Extensions`, and loading is requested with `kmutil load`. If macOS requests approval, open **System Settings → Privacy & Security**, approve the extension, and reboot. kmutil codes 27 and 28 mean approval required and reboot required respectively; neither means audio is already working.

3. Verify after rebooting:

   ```sh
   bash "$HOME/Downloads/S540-audio-Tahoe-v3/VERIFICA-AUDIO.command"
   ```

   Check speakers and volume, then headphones/analog jack and microphone. Record each result. Audio recovery after sleep is a later check.

If a check stops, retain its message. Repeating the older Intel tests or reinstalling Tahoe is unnecessary. The program does not reboot the laptop automatically.

## Rollback

```sh
bash "$HOME/Downloads/S540-audio-Tahoe-v3/RIPRISTINA-AUDIO.command"
```

The program removes only the driver installed by this procedure, after verifying its files, and requests an auxiliary collection rebuild with `kmutil rebuild`. After installation, rollback proceeds as follows:

1. Move the driver into the backup and request an AuxKC rebuild; follow any approval prompt and reboot.
2. Run the same command again. It checks for a new boot session and the absence of VoodooHDA from the collection, then prepares the original SIP value and requests another reboot.
3. Run it a third time to verify SIP and restore the config's original bytes. If preparation occurred without driver installation, the AuxKC stage is unnecessary.

If the config or driver has since changed, automatic rollback stops to avoid overwriting subsequent changes.

The private backup is at `EFI/OC/backup-audio-tahoe` and must be retained. It also contains the volume trial's snapshots and manifest. Keep it out of the repository: it contains the device's real config. The procedure neither deletes the earlier complete EFI backup nor modifies the Windows disk.

## Verification limits

Bash syntax, asset and individual-file authenticity, ZIP integrity, and fixtures for the intended changes were checked on Linux. The prepared and original-SIP return configs pass ocvalidate 1.0.8; fixtures preserve identity, ACPI, Booter, Intel graphics, and the other kext entries. A separate review checked temporary-copy handling, the journal, recovery from interruptions, and the AuxKC check before SIP restoration. The first laptop run verified the payload, signature, EFI ownership, and HDAS before the SIP check stopped it. Correct reading and restoration of the initial zero and 0x267 cases were checked with fixtures; after v2, working playback and F1–F3 were reported.

For volume package v3, a fixture checks the single changed Bool and preservation of the other mixer properties. The program's actual hash functions recognize the original payload and fixture-recorded variant, and reject an altered binary. Signing and AuxKC rebuilding were not performed directly in the Linux environment. Playback and gradual attenuation were reported working after the Mac trial; no new technical report was supplied. A supported codec and matching HDAS name do not establish audio quality, analog jack, microphone, or recovery after sleep.

AppleHDA remains a later option if this approach does not meet requirements. NVIDIA research remains in the [roadmap](../status/roadmap.md).

## Primary sources

- [Dortania Tahoe: analog audio and VoodooHDA](https://dortania.github.io/OpenCore-Install-Guide/extras/tahoe.html#analog-audio).
- [VoodooHDA Release368](https://github.com/CloverHackyColor/VoodooHDA/releases/tag/Release368).
- [VoodooHDA: volume handling](https://github.com/CloverHackyColor/VoodooHDA/blob/8c7e8e2ce6de0a917be663a3192857955288c937/tranc/VoodooHDAEngine.cpp#L1027).
- [VoodooHDA: flag reading and mixer curve](https://github.com/CloverHackyColor/VoodooHDA/blob/8c7e8e2ce6de0a917be663a3192857955288c937/tranc/VoodooHDADevice.cpp#L237).
- [Apple codesign manual](https://keith.github.io/xcode-man-pages/codesign.1.html): replacing and verifying ad hoc signatures.
- [VoodooHDA: layout selection](https://github.com/CloverHackyColor/VoodooHDA/blob/8c7e8e2ce6de0a917be663a3192857955288c937/tranc/VoodooHDADevice.cpp).
- [VoodooHDA: ALC257 table](https://github.com/CloverHackyColor/VoodooHDA/blob/8c7e8e2ce6de0a917be663a3192857955288c937/tranc/AppleALCPinConfigs.cpp).
- [AppleALC: AppleHDA removal in macOS 26](https://github.com/acidanthera/AppleALC/blob/master/README.md).
- [OpenCore 1.0.8: adding NVRAM without overwriting](https://github.com/acidanthera/OpenCorePkg/blob/1.0.8/Library/OcMainLib/OpenCoreNvram.c#L193) and [handling an existing variable](https://github.com/acidanthera/OpenCorePkg/blob/1.0.8/Library/OcVariableLib/LegacyNvramSupport.c#L134).
- [Apple kmutil manual](https://keith.github.io/xcode-man-pages/kmutil.8.html): auxiliary collection, approval, loading, and removal.
- [OCLP: restoring AppleHDA in the system volume](https://github.com/dortania/OpenCore-Legacy-Patcher/blob/8da38565fa1551a8e5ce8613ea835d04dd97e089/opencore_legacy_patcher/sys_patch/patchsets/hardware/misc/modern_audio.py).
