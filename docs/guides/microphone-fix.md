# Microphone gain correction

This upgrade procedure requires the existing V3 audio installation and its private backups. It is not a standalone fresh-install procedure for an EFI archive.

The report collected before the correction, at 30% and 70% input, confirms that the driver changes every mixer, including output mixers, while macOS continues to display speaker volume at 100. The ALC257 codec has a microphone boost with four levels from 0 to 30 dB and an ADC amplifier with 64 levels, from -17.25 to +30 dB in 0.75 dB steps. Combining these controls produces the abrupt level changes.

This procedure uses VoodooHDA **3.6.9, S540 variant**, built from the pinned 3.6.8 source. It is not an official upstream release. The input slider uses the ADC; boost on the internal and jack microphone pins stays at 0 dB. The PCM speaker-volume correction remains active, and the two sliders are independent. Equalization, function keys, and sleep remain later tasks.

The correction activates only for Intel controller 8086:9dc8, Realtek codec 10ec:0257, and the controls observed on the laptop. If the graph differs, the driver retains the original algorithm and verification reports that the correction is inactive. Recording through the analog jack was subsequently confirmed working; see the on-device result below.

## On-device result

After package **S540-microfono-fix-v2** and a reboot on October 14, 2026, internal microphone operation was reported working. Bluetooth headset voice capture and microphone input through the 3.5 mm jack were subsequently confirmed. The working correction and previous driver's backup are retained. Equalization and audio recovery after sleep remain deferred.

The later [fine-volume upgrade](volume-control.md) preserves this input correction in driver 3.6.10. While that upgrade is installed, use its own verify/restore commands; restore it before using this guide's older rollback helper.

## Installing from the Tahoe desktop

Version v2 checks the driver's Intel header using system utilities. It requires neither Xcode nor Command Line Tools and retains v1's integrity and signature checks.

Extract **S540-microfono-fix-v2.zip** into Downloads. Keep the **240 GB** disk connected and mounted. Also copy the complete `S540-microfono-fix-v2` folder to the 240 GB disk so the rollback command is available from Recovery.

```sh
bash "$HOME/Downloads/S540-microfono-fix-v2/INSTALLA-MICROFONO.command"
```

The command checks the current V3 variant, the new driver, and symbols available in the Tahoe kernel. It then saves the working driver byte for byte, replaces the bundle, and requests an auxiliary collection rebuild. It requests the administrator password in Terminal. If macOS requires approval, follow the Privacy & Security message and rerun the command when instructed. Reboot only when the command requests it.

The private backup is on the Data volume at `/Library/Application Support/S540-microfono`, owned by root with permissions 700. Retain it. The config, SIP, NVRAM, AMFI, and sealed system volume are unchanged. The `-igfxblr` argument remains in the config.

## Verifying after reboot

```sh
bash "$HOME/Downloads/S540-microfono-fix-v2/VERIFICA-MICROFONO.command"
```

Verification requires loaded version 3.6.9, `S540InputGainFixActive=true`, and two input controls with the exact -17.25/+30 dB range. These checks establish that the variant is active, not the quality of the recording.

If verification passes, select the internal microphone under Sound/Input. Start at 50%, record the same sentence, and adjust gradually. Also check speaker volume and mute, including F1–F3. Record whether gain changes gradually and whether distortion or noise appears.

## Rolling back from the desktop

```sh
bash "$HOME/Downloads/S540-microfono-fix-v2/ANNULLA-MICROFONO.command"
```

The command recognizes the trial driver, restores the exact saved V3 bundle, and requests an AuxKC rebuild. Reboot and run the same verification command. Rollback is independent of the current config's hash and preserves subsequent EFI changes. Use this package to undo the correction: the older audio program does not recognize the new 3.6.9 binary.

## Rolling back from Recovery

If the desktop does not boot, start Recovery using the configuration that already works. Mount the Samsung's System and Data volumes in Disk Utility. If their names match those shown here and the package folder has been copied to 240 GB:

```sh
bash "/Volumes/240 GB/S540-microfono-fix-v2/ANNULLA-MICROFONO.command" --recovery-data "/Volumes/Macintosh SSD - Data" --recovery-system "/Volumes/Macintosh SSD"
```

The command checks the Data UUID recorded in the backup. If the system also exposes the common APFS volume group, it attempts an AuxKC rebuild on the corresponding System volume. If that evidence is unavailable, or approval cannot be completed from Recovery, it restores the files but leaves `restorepending`: rebuilding is incomplete and must be verified before rebooting. It does not force Boot/System collection rebuilds or remove other kext approvals.

The Recovery procedure has not been run on the laptop. Missing utilities or unrecognized volumes are reported; retain the message.

## Package validation

CI applies the patch to the pinned source and builds for Intel using a pinned MacKernelSDK. It checks MH_KEXT_BUNDLE format, architecture, ad hoc signature, version, and the three-file manifest. Tests execute the patch's actual functions with sanitizers and check the scale, 64 levels, mute, input/output separation, mixer restoration, and fallback. Installer fixtures also check the native header reader, rejecting ARM, universal, wrong-type, and truncated binaries; they simulate interrupted renames, incorrect manifests and permissions, V3 restoration, and config independence. CI does not load the driver into the kernel. The on-device functional result is recorded above; it does not quantify recording quality or establish audio recovery after sleep.

## Sources

- [Pinned VoodooHDA source](https://github.com/CloverHackyColor/VoodooHDA/tree/8c7e8e2ce6de0a917be663a3192857955288c937).
- [Pinned MacKernelSDK](https://github.com/joevt/MacKernelSDK/tree/bfbfbe4cf35979f33ded6c7a8761eb1df091fb39).
- [Apple kmutil manual](https://keith.github.io/xcode-man-pages/kmutil.8.html).
