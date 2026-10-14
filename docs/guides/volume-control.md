# Fine output volume control

This upgrade addresses loud speaker/headphone output near the bottom of the macOS volume slider. The correction was reported working during YouTube playback on October 15, 2026. Quiet-volume regulation is retained as resolved. F1–F3, jack switching and microphone operation were already working; equalisation and audio recovery after sleep remain deferred.

## Scope and source evidence

VoodooHDA 3.6.9 S540 preserves the earlier PCM volume correction. Its upstream `VoodooHDAEnableVolumeChangeFix` interpolation uses only the upper half of the DAC's gain range. The collected codec graph identifies analog DAC NID 2 with output capability `0x00025757`: mute=0, step=87, size=2 and offset=87. This provides 88 hardware gain levels spanning **−65.25 to 0 dB**. Mute remains handled by the existing output-pin controls. Speakers and the headphone jack share this DAC.

The new **3.6.10 S540 variant** restores that DAC's full range and reports its actual range to macOS. It is a project variant, not an official upstream release. The maximum hardware gain stays at 0 dB. The existing microphone patch, ADC gain, fixed pin boost, jack routing and other devices are retained. The policy is opt-in and activates only when the controller, codec, analog playback association and observed DAC capabilities match; a mismatch retains the previous algorithm.

The older −21.5 dB output metadata was a fallback from querying the master mixer rather than PCM. Changing that label alone would not change the audible range. This upgrade changes both the DAC mapping and the matching metadata.

## Install on the working Tahoe desktop

Use the complete **S540-volume-fine-v1.zip**, extracted into Downloads. The existing 3.6.9 microphone correction and its private backup must be present. The installer matches the current driver to that backup's payload reference before replacing it. No developer tools are required.

```sh
bash "$HOME/Downloads/S540-volume-fine-v1/INSTALL-VOLUME.command"
```

Enter the administrator password when asked. The command saves the exact working driver, installs the new bundle and rebuilds the auxiliary kernel collection. Follow any driver-approval message and rerun the command if instructed. Restart manually only after rebuilding completes.

Installation does not require the 240 GB HDD or read/edit its EFI. The current EFI, SIP, NVRAM, AMFI and sealed system volume are unchanged. The new private backup is `/Library/Application Support/S540-volume-fine`; the earlier microphone backup is retained independently.

## Optional driver check after restarting

```sh
bash "$HOME/Downloads/S540-volume-fine-v1/VERIFY-VOLUME.command"
```

Verification checks the installed hashes, loaded version 3.6.10, both active correction markers and the two input/output control ranges. Output must expose −65.25/0 dB; input must remain −17.25/+30 dB. These checks establish the loaded variant, not subjective audio quality.

The listening result above is sufficient to close the reported quiet-volume issue. The optional command remains available for driver diagnostics; no further collection is required for this result. Equalisation and audio recovery after sleep remain separate work.

## Restore the previous driver

```sh
bash "$HOME/Downloads/S540-volume-fine-v1/RESTORE-VOLUME.command"
```

Restart after rebuilding, then run `VERIFY-VOLUME.command` again. Restoration returns the exact saved 3.6.9 microphone driver. Use this volume package while its 3.6.10 variant is installed; restore it before invoking the earlier microphone or initial audio rollback helpers.

For a Recovery copy, keep the complete package folder on the 240 GB recovery disk before relying on this example. Mount the matching Samsung System and Data volumes, then adapt their names if needed:

```sh
bash "/Volumes/240 GB/S540-volume-fine-v1/RESTORE-VOLUME.command" --recovery-data "/Volumes/Macintosh SSD - Data" --recovery-system "/Volumes/Macintosh SSD"
```

Recovery restoration checks the Data UUID and saved hashes. If the matching volume group or kernel approval cannot be established, files may be restored while rebuilding remains pending; retain that status and complete the rebuild before restarting. The Recovery route has not been run on the laptop.

## Validation

The build uses the same pinned VoodooHDA source and MacKernelSDK as microphone v2, applies the unchanged input patch first and then the separate output patch. Tests execute the actual C++ functions with sanitizers: full DAC range, unchanged maximum, stereo levels, mute/unmute, mixer resume, input isolation and graph mismatch fallback. Native installer fixtures cover the private source reference, fresh upgrade without EFI access, interrupted swaps, ownership checks and exact rollback. CI builds and signs the Intel kernel bundle and validates its manifest; it does not load it into the kernel.

## Sources

- [Pinned VoodooHDA source](https://github.com/CloverHackyColor/VoodooHDA/tree/8c7e8e2ce6de0a917be663a3192857955288c937).
- [Preserved microphone correction](microphone-fix.md).
- [Scoped output patch](../../patches/audio-volume/output-range.patch).
