# v0.4.0-nvidia-experimental.1 — NullMoth NVIDIA profile

This **experimental prerelease** records the source Lenovo IdeaPad S540-15IWL
GTX (81SW) configuration that runs the GTX 1650 Max-Q through NullMoth 2.7.2,
keeps Intel UHD 620 for the internal panel, and provides NVIDIA-routed HDMI
video/audio on macOS Tahoe **26.7.1 (25G241)**.

It does not replace the [v0.3.0 stable Intel
profile](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/releases/tag/v0.3.0).
Keep v0.3.0 as the independent recovery route.

## Release format

The published asset is a small **local assembler kit**. It downloads and
cryptographically verifies pinned upstream inputs on the user's Mac, then builds
the machine-specific EFI and prepared NullMoth tree locally.

No NullMoth/NVIDIA payload, upstream Apple driver binary, private SMBIOS
identity, generated Auxiliary Kernel Collection or generated local EFI is
redistributed by this release. The project-built S540Sensors binary is included
with the complete APSL/BSD licenses, source locations and embedded APSL notice.
This format preserves the exact tested source bindings without asserting
redistribution rights that the project does not have.

The kit itself closes the administrator handoff against path replacement by
freezing the verified driver tree in an anonymous TAR before confirmation. It
also carries the complete Lilu, VirtualSMC and MacKernelSDK license/notice set
for S540Sensors. Its released S540Sensors binary differs from the target-loaded
1.0.0 build only by an embedded APSL source-availability notice; that compliance
rebuild is locally compiled, signed and hash checked, but was not separately
loaded on the target kernel.

## Confirmed additions

- NullMoth 2.7.2 loads NVRM, NVAccel, NVRMFB and NVRMAGDC for the GTX 1650
  Max-Q TU117 4 GB and exposes Metal 3.
- Compute, offscreen rendering, Full HD rendering, 159/159 cross-GPU presentation
  frames, Core Image and a 72-second sustained compute run were verified.
- `nvfb=1 nvfbheads=4 -nvkmsnosmooth` establishes the NVIDIA framebuffer used by
  the laptop's physical HDMI connector.
- HDMI video was confirmed at 1920×1080 60 Hz on an LG television.
- NMXAudio 1.0.0 is locally restricted to NVIDIA HDA `10DE:10FA`, installed in
  `/Library/Extensions` and the Auxiliary Kernel Collection, and provides
  confirmed 48 kHz HDMI playback.
- Restoring `applbkl=1` fixed the temporary brightness regression while retaining
  HDMI; the macOS slider and F11/F12 work.
- S540Sensors 1.0.0 publishes the genuine NVIDIA NVAccel temperature as `TG0D`.
  CPU temperature remains available through VirtualSMC/SMCProcessor 1.3.8.
- One controlled 54-second sleep/wake cycle retained HDMI, HDMI audio, internal
  audio, brightness, Wi-Fi and Bluetooth controller operation.

## Tested software

| Component | Version / tested placement |
|---|---|
| macOS | 26.7.1, build 25G241 |
| OpenCore | 1.0.8 RELEASE |
| NullMoth | 2.7.2, exact signed upstream package |
| NMXAudio | 1.0.0, exact NVIDIA HDA match in `/Library/Extensions` + AuxKC |
| VoodooHDA | 3.6.10 S540, separate macOS companion |
| S540Sensors | 1.0.0, `TG0D` NVIDIA temperature only |
| AirportItlwm | 2.4.0 tested variant |
| BigSurSDXC | 1.9.0, direct O2Micro match |
| VirtualSMC / SMCProcessor | 1.3.8 |
| S540 Tasti | 0.1.3, separate app/driver companion |

## Hardware status on the source laptop

| Feature | Result and evidence boundary |
|---|---|
| Intel UHD 620 / internal BOE panel | Working with acceleration and brightness control |
| GTX 1650 Max-Q | Experimental Metal 3 execution/rendering verified as described above |
| HDMI video/audio | Working at 1080p60 with 48 kHz display audio on the tested LG TV |
| Wi-Fi / Bluetooth headset | Working, including post-wake Wi-Fi and headset reconnection; automatic headset reconnection not separately proved |
| Internal / 3.5 mm audio | Working through separately installed VoodooHDA 3.6.10 |
| Touchpad / webcam | Working; gestures and F6 confirmed; F8 does not disable camera capture |
| Function keys | F1–F3, F5, F6, F11/F12 confirmed; F4/F7/F9 use S540 Tasti; F10 remains unverified |
| USB-A / USB-C data | 5 Gb/s confirmed; USB-C data tested in both orientations |
| NVMe / SD | SMART/TRIM working; known 8 GB FAT32 SD card mounts, unmounts and survives wake |
| Sleep/wake | Existing lid/idle results plus one 54-second NVIDIA/HDMI cycle; no overnight/hibernation claim |
| CPU / NVIDIA temperatures | Working through SMCProcessor and S540Sensors `TG0D` respectively |
| Fans | Physically working and responsive; RPM telemetry unavailable, with no fake keys or control writes |

## Security difference from v0.3.0

This profile uses `SecureBootModel=Disabled`, reduced SIP
(`csr-active-config=0x0A43`) and AMFI/task-port-relaxing boot arguments required
by the experimental driver path. This is a real expansion of the attack surface,
not a cosmetic setting difference. Read [SECURITY.md](SECURITY.md) and install
only on a system whose recovery path and backups have been tested.

## Structural limitations

Only two items are classified as not fixable by an EFI/kext:

1. **Native USB-C video:** the laptop lacks DisplayPort Alt Mode lanes on its
   USB-C connector. USB data works; DisplayLink would be separate USB graphics.
2. **Native Touch ID:** Goodix `27c6:55b4` has no Apple Secure Enclave pairing,
   so it cannot become Apple's authenticated Touch ID.

## Not working, unavailable or not qualified — not “impossible”

- F8 changes a firmware state but does not disable macOS camera capture; work is
  paused. F10 display-mode behavior remains unverified.
- Fan RPM is not readable through the current trusted sensor paths, although the
  fans themselves work.
- Overnight standby, hibernation, calibrated standby drain and long-duration
  thermal/cooling qualification remain outside the evidence.
- SD writes, throughput and additional card types/capacities are unqualified.
- AirDrop/Continuity and a real wireless-display stream are unqualified.
- Cold-boot/peripheral combinations beyond the documented tests are not implied.

## macOS 26.7.2 is not covered

macOS 26.7.2 build **25G332** is untested. Its changes intersect Kernel, IOKit,
IOGPUFamily/GPU drivers and audio. The current installer must not be forced past
its build/state guards. Updating requires a new read-only audit, Kernel
Collection inspection and functional requalification; a blanket reinstall is
not the assumed recovery action.

Read [INSTALL.md](INSTALL.md), [SOURCE-PROVENANCE.md](SOURCE-PROVENANCE.md),
[SECURITY.md](SECURITY.md) and [ROLLBACK.md](ROLLBACK.md) before using the kit.
