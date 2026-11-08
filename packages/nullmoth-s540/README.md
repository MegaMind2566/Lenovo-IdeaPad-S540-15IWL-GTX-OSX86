# NullMoth 2.7.2 on the Lenovo S540

This directory preserves the source, target-specific checks and guarded tools
used by the **v0.4.0-nvidia-experimental.1** profile for the Lenovo IdeaPad
S540-15IWL GTX (81SW), NVIDIA PCI `10DE:1F91`, subsystem `17AA:3806`.

The independent [v0.3.0 stable Intel
release](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/releases/tag/v0.3.0)
keeps NVIDIA disabled and remains the known-good recovery path. The NVIDIA
profile is a machine-specific experimental prerelease tested only on macOS
Tahoe **26.7.1 (25G241)** on the source laptop.

## What the public prerelease contains

The public release is an **assembler kit**, not a mirror of the locally working
driver tree and not a prebuilt Auxiliary Kernel Collection. It can include the
project's own S540Sensors source/binary, a sanitized config, pinned source
metadata, verification code and guarded assembly/install launchers.

It does **not** redistribute:

- the NullMoth 2.7.2 payload or NVIDIA firmware;
- upstream Apple-derived or otherwise redistribution-ambiguous driver binaries;
- AMFIPass or other upstream binaries without a clear redistribution grant;
- a generated Auxiliary Kernel Collection;
- the source laptop's private serial, MLB, SystemUUID or ROM; or
- local backups, captures, diagnostics or generated EFI archives.

The project-built S540Sensors binary is the explicit exception to the broad
binary exclusion above: it statically includes MacKernelSDK `libkmod` Covered
Code and Lilu/VirtualSMC header code. The public kit therefore embeds the APSL
source-availability notice and includes the complete APSL 2.0 and BSD 3-Clause
license/notice set.

The assembler downloads exact official/upstream assets on the user's Mac,
checks their pinned sizes and SHA-256 values and verifies NullMoth's Ed25519
signatures before it builds anything. Locally generated EFI/driver/KC content
must remain local.

See the [installation
guide](../../docs/releases/v0.4.0-nvidia-experimental.1/INSTALL.md), [source
provenance](../../docs/releases/v0.4.0-nvidia-experimental.1/SOURCE-PROVENANCE.md),
[security boundary](../../docs/releases/v0.4.0-nvidia-experimental.1/SECURITY.md)
and [rollback
procedure](../../docs/releases/v0.4.0-nvidia-experimental.1/ROLLBACK.md).

## Pinned target and safety boundaries

- NullMoth **2.7.2**, upstream commit
  `18ba05f38b5eadea8b5ae05834bb51c61fb4c5c3`.
- OpenCore **1.0.8 RELEASE**.
- macOS **26.7.1 (25G241)**. macOS 26.7.2 (25G332) is untested.
- `-wegnoegpu` is removed only from the experimental profile.
- `gfxrst=4` is retained because WhateverGreen still serves Intel UHD 620.
- `nvfb=1 nvaccel=1 nvfbheads=4 -nvkmsnosmooth` enables the tested NVIDIA
  framebuffer path; `applbkl=1` retains internal-panel brightness control.
- Existing `ResizeGpuBars` and `ResizeAppleGpuBars` values are retained.
- No unverified NVIDIA `DeviceProperties`, fake sensor key, EC fan-control write
  or generic audio match is introduced.
- NMXAudio is installed in `/Library/Extensions` and the Auxiliary Kernel
  Collection. It is never duplicated in `EFI/OC/Kexts`.
- The v0.3.0 Intel profile must remain available before any experimental change.

Do not force-load the separate retained B10 development port and NullMoth in the
same boot. They are independent experiments. Do not bypass a refusal caused by
a different machine, OS build, EFI, source hash or Kernel Collection.

## Verified GPU result — 7 November 2026

NVRM, NVAccel, NVRMFB and NVRMAGDC load on macOS Tahoe 26.7.1. The GTX 1650
Max-Q is exposed as TU117 with 4 GB and Metal 3.

The NVIDIA-only compute verifier checked 1,280 values in each of five runs. The
offscreen renderer read back 4,096 correct RGBA pixels per run in three runs.
Extended qualification then confirmed:

- Full HD rendering;
- cross-GPU presentation for **159/159** MetalKit frames;
- a Core Image Gaussian blur; and
- **72 seconds** of sustained compute with **629,145,600** verified values.

WindowServer did not restart and the reported GPU recovery count remained zero.
This establishes execution/rendering on the source laptop, not codec support,
hibernation, indefinite stability or compatibility with another machine.

## HDMI video and brightness — 8 November 2026

The physical HDMI connector is routed through the NVIDIA controller. The earlier
headless profile loaded NVRMFB but omitted `nvfb=1`. The verified argument set is:

```text
nvfb=1 nvaccel=1 nvfbheads=4 -nvkmsnosmooth gfxrst=4 applbkl=1
```

With these arguments, the LG television is online at **1920×1080 60 Hz**. The
system also discovers wireless-display targets again, but an actual wireless
stream has not been qualified.

An A/B candidate accidentally omitted `applbkl=1`, removing the brightness
slider even though AppleBacklightDisplay was present. Restoring it brought back
the slider and F11/F12 without breaking HDMI. This omission, not a panel or
ACPI failure, was the brightness regression.

## HDMI audio — 8 November 2026

Tahoe did not attach display audio to NVIDIA HDA `10DE:10FA`. A generic
NMXAudio personality would also match unrelated PCI HDA controllers, so the
local installer restricts it to the exact NVIDIA device while retaining class
match `0x04030000&0xffff0000`.

| Item | SHA-256 |
|---|---|
| Unchanged official NMXAudio executable | `77e19e244978ce64e4505c4701069edfe609379f91a9c76313b4a27ded4ab07a` |
| Exact-match NMXAudio `Info.plist` | `ebff8ac2ea5b57f7d6ccbb764f56025213a22a4156df8dd3b8c9c9e64f126d4a` |
| Final tested Auxiliary Kernel Collection | `11242eba86841ccfe5148ea2a185c0f36f141ab360254f06f50cccfc57db3271` |

OpenCore injection did not load this driver. The accepted path installs
`NMXAudio.kext` in `/Library/Extensions`, rebuilds the Auxiliary Kernel
Collection from the live paths and removes any duplicate EFI entry. The driver
attaches only to NVIDIA HDA and exposes `NVIDIA (0x0094) (HDMI/DP 8ch)` at
48 kHz. Playback through the LG TV was heard and user-confirmed. VoodooHDA
3.6.10 continues to provide internal/3.5 mm audio.

## Sensors and fans — 8 November 2026

VirtualSMC/SMCProcessor 1.3.8 continues to expose CPU temperatures. The
project-owned S540Sensors 1.0.0 plugin publishes only the genuine NVAccel
temperature as SMC key `TG0D`; it does not invent an Intel-GPU value.

The physical fans work and react to load. Standard EC/SMCSuperIO paths do not
provide a trustworthy RPM counter on this laptop, so no `F0Ac`/`F1Ac`/`F2Ac`
key is published and no fan-control write is performed. Unavailable RPM
telemetry is not evidence of zero RPM or a failed fan, and it is not classified
as a permanent hardware impossibility.

## Controlled sleep/wake result — 8 November 2026

The controlled test scheduled an RTC wake, entered sleep and resumed after 54
seconds. After wake:

- NMXAudio, NVRMFB and VoodooHDA remained loaded;
- the LG TV and NVIDIA HDMI output remained online;
- HDMI playback used an active NMXAudio engine and was heard;
- internal audio and AppleBacklightDisplay remained available; and
- Wi-Fi reconnected while the Bluetooth controller remained active.

This is one short controlled cycle. It does not qualify overnight standby,
hibernation, calibrated drain or a full matrix of cold boots/peripherals.

## macOS 26.7.2 update boundary

The offered 26.7.2 update is build **25G332**. It is not installed or qualified
with this profile. Its changes intersect Kernel, IOKit, IOGPUFamily/GPU drivers
and audio, precisely the subsystems used by NullMoth, NMXAudio and VoodooHDA.

Before an update, preserve the complete EFI, `/Library/Extensions`,
`/Library/NullMoth`, the working Auxiliary Kernel Collection and an alternate
boot route. After an update, inspect the new collection before writing to it.
Rebuild only what the update actually omitted, from the real live paths.

Do not force an older state-bound installer against 25G332 and do not run a
stock generic NMXAudio installer over the exact `10DE:10FA` bundle. A future
25G332 recovery package must start with a read-only audit and new validation.

## What is structurally impossible and what is merely open

Two limitations are structural rather than missing EFI work:

1. The laptop's USB-C connector has no DisplayPort Alt Mode lanes, so it cannot
   provide **native USB-C video**. DisplayLink would be separate USB graphics.
2. The Goodix `27c6:55b4` sensor is not paired with an Apple Secure Enclave, so
   it cannot provide **native Touch ID**.

F8 privacy switching, F10 display-mode behavior, fan RPM telemetry,
AirDrop/Continuity, wireless streaming, hibernation, overnight sleep and broader
SD-card coverage remain non-working, unavailable or unqualified as documented;
none is promoted to “impossible” by this release.

## Retained development launchers

Historical launchers retain exact-state discovery and rollback evidence. Some
expect private `_external`, `_candidates`, `_backups`, `build` or `_diagnostics`
inputs that are deliberately excluded from Git. Refusal when those exact inputs
are absent or changed is expected.

The public release workflow uses the guarded launchers in `release/`; the older
files at this directory's top level remain evidence of the path that established
the accepted settings. They are not a generic installer for another laptop.
