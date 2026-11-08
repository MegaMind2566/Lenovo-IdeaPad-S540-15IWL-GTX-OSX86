# NullMoth 2.7.2 on the Lenovo S540

This directory preserves the target-specific preparation, verification and
recovery launchers used for the experimental NVIDIA profile on the Lenovo
IdeaPad S540-15IWL GTX (81SW), PCI `10DE:1F91`, subsystem `17AA:3806`.

The official v0.3.0 EFI remains the stable Intel profile with NVIDIA disabled.
This directory does not contain the NullMoth distribution, a complete EFI,
private SMBIOS identity, local backups or generated Kernel Collections. Several
launchers are deliberately bound to exact hashes and to the source laptop's
`disk0s1` ESP; they are execution receipts and guarded recovery tools, not a
generic installer for another machine.

## Pinned input and safety boundaries

- NullMoth `2.7.2`, commit `18ba05f38b5eadea8b5ae05834bb51c61fb4c5c3`.
- The known-good Intel EFI remains the independent recovery path.
- `-wegnoegpu` is removed only from the experimental profile.
- `gfxrst=4` is retained because WhateverGreen still serves the Intel UHD 620.
- Existing `ResizeGpuBars` and `ResizeAppleGpuBars` values are retained.
- No NVIDIA `DeviceProperties`, fan-control write or unverified EC field is
  introduced.
- NMXAudio is installed in `/Library/Extensions` and in the Auxiliary Kernel
  Collection. It is not duplicated in `EFI/OC/Kexts`.

Do not force-unload the retained B10 development port and NullMoth in the same
boot. They are separate experiments. Do not run the installation launchers on a
different EFI, disk layout or Kernel Collection after bypassing their refusal
checks.

## GPU result — 7 November 2026

NVRM, NVAccel, NVRMFB and NVRMAGDC load on macOS Tahoe 26.7.1. The GTX 1650
Max-Q is exposed as TU117 with 4 GB and Metal 3.

The NVIDIA-only compute verifier checked 1,280 values per run for five runs.
The offscreen renderer read back 4,096 correct RGBA pixels per run for three
runs. Extended qualification then confirmed Full HD rendering, cross-GPU
presentation in a MetalKit window for 159/159 frames, a Core Image Gaussian
blur and 72 seconds of sustained compute with 629,145,600 verified values.
WindowServer did not restart and the reported GPU recovery count stayed zero.

These results establish execution and rendering on this laptop. They do not
turn the experimental profile into the official release or prove codec,
hibernation, long-duration stability or compatibility with other machines.

## HDMI video and brightness — 8 November 2026

The HDMI port is routed through the NVIDIA controller. NVRMFB was loaded but
the earlier profile remained headless because `nvfb=1` was absent. The working
profile uses:

```text
nvfb=1 nvaccel=1 nvfbheads=4 -nvkmsnosmooth gfxrst=4 applbkl=1
```

With those arguments the LG television is online at 1920×1080 and 60 Hz. The
system also shows wireless-display discovery again; an actual wireless stream
was not separately qualified.

One A/B profile accidentally omitted `applbkl=1`, which removed brightness
adjustment even though AppleBacklightDisplay was present. Restoring that
argument restored the slider and the physical F11/F12 controls while keeping
HDMI active. The final full boot-argument string is retained by the guarded EFI
candidate locally; the public repository intentionally does not publish the
private EFI.

## HDMI audio — 8 November 2026

Tahoe did not attach a display-audio driver to the NVIDIA HDA function
`10DE:10FA`. Generic NMXAudio matching would also cover other PCI HDA
controllers, so only its `Info.plist` was changed to require the exact NVIDIA
device while retaining class match `0x04030000&0xffff0000`.

- Unchanged official NMXAudio executable SHA-256:
  `77e19e244978ce64e4505c4701069edfe609379f91a9c76313b4a27ded4ab07a`
- Exact-match `Info.plist` SHA-256:
  `ebff8ac2ea5b57f7d6ccbb764f56025213a22a4156df8dd3b8c9c9e64f126d4a`
- Final Auxiliary Kernel Collection SHA-256 on the tested installation:
  `11242eba86841ccfe5148ea2a185c0f36f141ab360254f06f50cccfc57db3271`

OpenCore injection did not load this driver. The accepted path installs the
exact-match bundle at `/Library/Extensions/NMXAudio.kext`, rebuilds the
Auxiliary Kernel Collection from the real `/Library/Extensions` paths and
removes the duplicate EFI entry. `kmutil inspect` then records
`com.nullmoth.NMXAudio 1.0.0` at that live path.

The driver attaches only to the NVIDIA HDA function. macOS exposes
`NVIDIA (0x0094) (HDMI/DP 8ch)` at 48 kHz, and playback through the LG TV was
heard and user-confirmed. VoodooHDA 3.6.10 continues to expose the internal
speakers and microphone.

`INSTALL-NMXAUDIO-AUXKC-KEEP-BRIGHTNESS.command` contains the complete guarded
installation and rollback sequence. `REBUILD-NMXAUDIO-AUXKC-LIVE-PATHS.command`
is the one-time repair retained from the discovery that an intermediate build
embedded temporary repository paths; the final installer already builds from
the live paths and does not require that repair.

## Controlled sleep/wake result — 8 November 2026

`TEST-SLEEP-WAKE-HDMI.command` scheduled an RTC wake, entered system sleep and
resumed after 54 seconds. After wake, all automated checks passed:

- NMXAudio, NVRMFB and VoodooHDA remained loaded;
- the LG TV and NVIDIA HDMI output remained online;
- HDMI playback used an active NMXAudio engine and was heard by the user;
- internal speakers, internal microphone and AppleBacklightDisplay remained;
- Wi-Fi reconnected and the Bluetooth controller remained active.

This is one controlled short cycle, not overnight standby, calibrated drain,
hibernation or a cold-boot qualification. The user subsequently confirmed that
the complete setup remains stable.

## macOS 26.7.2 update boundary

The 26.7.2 update offered to the source laptop is build `25G332`. It has not
been installed or qualified with this profile. Apple lists fixes in Kernel,
IOKit, IOGPUFamily, GPU Drivers, CoreAudio and Audio, so the update intersects
the exact subsystems used by NullMoth, NMXAudio and VoodooHDA.

Before updating, preserve the EFI, `/Library/Extensions`, `/Library/NullMoth`
and the working Auxiliary Kernel Collection. After updating, inspect the new KC
before changing anything. If the exact bundles remain on disk but are absent
from the new KC, rebuild it from the live `/Library/Extensions` paths and verify
that every previous bundle identifier is retained.

Do not force `INSTALL-NMXAUDIO-AUXKC-KEEP-BRIGHTNESS.command` against the new
system: its current-KC hash intentionally binds it to the verified 26.7.1
starting state. Do not run the stock generic NMXAudio installer over the
targeted bundle, because that can remove the exact `10DE:10FA` match and expose
the Intel/Realtek audio path to a second driver. A 25G332 post-update recovery
package must perform a read-only audit first and rebuild only what the update
actually omitted.

## Retained launchers

The final-state launchers are:

- `INSTALL-NMXAUDIO-AUXKC-KEEP-BRIGHTNESS.command`: exact-state installation,
  backup, atomic publication and rollback guards;
- `PREFLIGHT-NMXAUDIO-NVIDIA-AUXKC.command`: `CHECK=1` temporary AuxKC build;
- `REBUILD-NMXAUDIO-AUXKC-LIVE-PATHS.command`: one-time metadata repair;
- `TEST-SLEEP-WAKE-HDMI.command`: controlled HDMI/audio recovery check;
- `COLLECT-HDMI-AUDIO-BOOTLOG.command`: read-only OpenCore log collector.

Other launchers and probes preserve the earlier GPU, HDMI, brightness, thermal
and fan-RPM A/B sequence. Some require locally retained `_external`,
`_candidates`, `_backups`, `build` or `_diagnostics` content that is deliberately
excluded from Git. Refusal on missing or mismatched inputs is expected.
