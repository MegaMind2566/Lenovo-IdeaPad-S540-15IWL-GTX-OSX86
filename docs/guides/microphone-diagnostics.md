# Microphone control collection

This collector targets the original VoodooHDA 3.6.8 driver and its V3 volume variant. It predates the S540 3.6.9 microphone correction and is not a collector for that newer driver. The V3 path requires the existing private audio backup.

The internal VoodooHDA microphone is present and captures voice. The October 14, 2026 report shows two channels at 48 kHz, both at 57 out of 100, with a declared range of 0 to +30 dB. It does not specify the amplifier's number of steps or the gain actually applied. Perceived gain changes abruptly from too high to too low.

The collection compares mixers with the input slider at about 30% and 70%. It does not install drivers, change plists, or write the EFI. Move the slider manually; note its original position and restore it at the end. Audio playback or recording is unnecessary during collection.

## Usage

Extract `S540-microfono-v2.zip` into Downloads and run:

```sh
bash "$HOME/Downloads/S540-microfono-v2/RACCOGLI-MICROFONO.command"
```

Follow the two prompts in Terminal. The diagnostic ZIP is created on the Desktop. Share it privately in the project chat; keep results out of the repository. Xcode and Python are not required on the laptop.

The program verifies the original VoodooHDA 3.6.8 driver or the V3 volume-correction variant. V3 is recognized through the manifest recorded in the audio backup on disk `240 GB`, which must be mounted. It compares the three bundle files, retained copies, and the single expected plist change. The V3 signature also changes the Mach-O binary, so its full-file hash differs from the original. Before each read, it rechecks the recognized variant's hash and the probe's hash.

If a check or read fails, it retains details in the collection folder and reports the problem. It requests no administrator privileges and does not repair permissions automatically. The check reads the backup without invoking the audio rollback program; the config containing `-igfxblr` is not involved.

## Contents

- `AUDIO.txt`: audio device list.
- Two snapshots of IOAudio controls and VoodooHDA mixers.
- The existing driver initialization buffer, if available.

The probe reads the driver's `0x3000` mixer buffer: cached left-channel percentages, not dB measurements or direct amplifier readbacks. The `0x2000` buffer is optional. The source records initialization messages even at verbosity zero, but buffer capacity is limited and completeness must be checked in the result. Generation of a new codec dump is not requested. The collection excludes the EFI, SMBIOS identity, Wi-Fi passwords, and system log archives.

## Source and validation

The ABI is pinned to [VoodooHDA commit 8c7e8e2](https://github.com/CloverHackyColor/VoodooHDA/blob/8c7e8e2ce6de0a917be663a3192857955288c937/tranc/Shared.h). The probe source is `tools/hda_mixer_snapshot.c`; the `build-microphone-probe.yml` workflow builds for Intel and verifies the ad hoc signature. With no VoodooHDA on the runner, CI checks enumeration without a driver, not buffer reading on the laptop.
