# Lenovo IdeaPad S540-15IWL GTX — macOS Tahoe

OpenCore project for **macOS Tahoe 26** on the **Lenovo IdeaPad S540-15IWL
GTX (81SW)**. The repository now maintains two deliberately separate profiles:
the stable Intel configuration and a machine-specific experimental NVIDIA
configuration.

## Release profiles

| Profile | Status | Graphics path | Tested system | Intended use |
|---|---|---|---|---|
| [v0.3.0](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/releases/tag/v0.3.0) | **Stable baseline** | Intel UHD 620; NVIDIA disabled | macOS 26.7.1, build 25G241 | Daily use and known-good recovery path |
| [v0.4.0-nvidia-experimental.1](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/releases/tag/v0.4.0-nvidia-experimental.1) | **Experimental prerelease** | Intel UHD 620 plus GTX 1650 Max-Q through NullMoth 2.7.2 | macOS 26.7.1, build 25G241, on the source 81SW only | NVIDIA Metal, HDMI video/audio and target-specific testing |

The experimental prerelease does **not** contain a redistributable NullMoth
installation, upstream Apple driver binaries, a generated Auxiliary Kernel
Collection or the laptop's private SMBIOS identity. Its project-built
S540Sensors binary does include the disclosed MacKernelSDK `libkmod` Covered
Code; the kit carries its APSL 2.0 source notice and all Lilu/VirtualSMC BSD
notices. The kit downloads the remaining exact upstream inputs, verifies their
pinned hashes and NullMoth signatures, then assembles and patches the
machine-specific files locally on the user's Mac. Keep v0.3.0 available as the
independent recovery profile.

macOS **26.7.2 (25G332) has not been tested** with either the NullMoth,
NMXAudio or VoodooHDA path. It changes subsystems used by this setup, including
Kernel, IOKit, IOGPUFamily/GPU drivers and audio. Do not present 25G332 as a
supported build until it has passed a fresh read-only audit, Kernel Collection
inspection and functional qualification.

## Tested hardware

| Component | Model |
|---|---|
| Laptop | Lenovo IdeaPad S540-15IWL GTX, **81SW** |
| CPU / memory | Intel Core i7-8565U / 12 GB DDR4-2400 |
| Graphics | Intel UHD 620 / NVIDIA GTX 1650 Max-Q TU117, 4 GB |
| Internal display | BOE NV156FHM-N61, 1920×1080 |
| Audio | Realtek ALC257; NVIDIA HDA `10DE:10FA` for HDMI |
| Wireless | Intel AC9560 Wi-Fi and Intel Bluetooth |
| Touchpad | ELAN0662 I2C |
| SD reader | O2Micro PCI `1217:8621`, subsystem `17AA:3803` |
| Fingerprint reader | Goodix USB `27c6:55b4` |
| Internal storage | Samsung PM981a 512 GB; Windows and macOS APFS coexist |

“Working” below means observed on this source laptop within the stated scope. It
does not certify another hardware revision, every peripheral or every
long-duration workload.

| Feature | Status | Confirmed scope / boundary |
|---|---|---|
| Internal macOS boot / Windows dual boot | **Working** | OpenCore boots macOS from the internal NVMe; Windows keeps its native rEFInd route |
| Intel graphics / internal display | **Working** | UHD 620 acceleration, Full HD panel and corrected startup backlight |
| NVIDIA acceleration | **Experimental, working on the source laptop** | NullMoth 2.7.2 exposes the GTX 1650 Max-Q as TU117 4 GB with Metal 3; verified compute, offscreen and Full HD rendering, 159/159 cross-GPU presentation frames, Core Image and a 72-second sustained compute run with 629,145,600 checked values |
| Internal brightness | **Working in both profiles** | macOS slider and F11/F12; the experimental profile requires retained `applbkl=1` |
| HDMI video | **Working in the experimental profile** | NVIDIA-routed output confirmed on an LG TV at 1920×1080 60 Hz; the v0.3.0 Intel profile does not provide it |
| HDMI audio | **Working in the experimental profile** | NMXAudio 1.0.0, restricted to NVIDIA HDA `10DE:10FA`, exposes 8-channel HDMI/DP audio at 48 kHz; heard and user-confirmed |
| Wi-Fi | **Working** | Intel AC9560 with AirportItlwm 2.4.0; native menu, restart and post-wake recovery confirmed |
| Bluetooth headset | **Working** | Playback and microphone confirmed, including after post-wake reconnection; automatic reconnection was not separately established |
| Speakers / internal microphone | **Working** | VoodooHDA 3.6.10 installed separately in macOS; playback and recording also confirmed after wake and Bluetooth disconnection |
| 3.5 mm headset | **Working** | Output, headset microphone and speaker/headphone switching confirmed |
| Webcam | **Working** | Video recording confirmed; F8 privacy switching is a separate non-working function |
| Touchpad / gestures | **Working** | ELAN0662 I2C operation, gestures and F6 enable/disable confirmed |
| Function keys | **Mostly working** | F1–F3, F5, F6, F11/F12 confirmed; F4/F7/F9 require S540 Tasti 0.1.3; F8 does not disable the camera; F10 display-mode action remains unverified |
| CPU power / battery reporting | **Working** | X86PlatformPlugin, reporting and discharge confirmed; Low Power Mode showed a CPU/package-power response, not a measured autonomy result |
| Sleep / wake | **Working in tested cycles** | Lid/idle cycles passed; the NVIDIA profile passed one controlled 54-second cycle with HDMI, audio, brightness, Wi-Fi and Bluetooth recovery |
| USB-A / USB-C data | **Working** | Tested at 5 Gb/s; USB-C data works in both orientations |
| Internal NVMe | **Working** | 512 GB detected, SMART verified and TRIM active |
| SD reader | **Working within the tested scope** | BigSurSDXC 1.9.0 with the known 8 GB FAT32 card; live insertion, mount/unmount and post-wake availability confirmed |
| CPU temperature | **Working** | VirtualSMC/SMCProcessor 1.3.8 telemetry confirmed |
| NVIDIA temperature | **Working in the experimental profile** | S540Sensors 1.0.0 publishes the genuine NVAccel temperature as SMC key `TG0D` |
| Fans | **Physically working** | The fans react to load; macOS RPM telemetry is unavailable and the project does not publish fake RPM keys or perform fan-control writes |

Detailed evidence remains in [hardware status](docs/status/hardware.md), the
[NullMoth S540 record](packages/nullmoth-s540/README.md), [battery and
sleep](docs/status/battery-sleep.md), [function keys](docs/guides/function-keys.md)
and [SD / fingerprint](docs/status/sd-fingerprint.md).

## Tested software stack

| Component | Tested version / placement |
|---|---|
| macOS | 26.7.1, build 25G241 |
| OpenCore | 1.0.8 RELEASE |
| NullMoth | 2.7.2; locally downloaded and signature/hash verified |
| NMXAudio | 1.0.0, exact `10DE:10FA` match in `/Library/Extensions` and the Auxiliary Kernel Collection; **not** injected from the EFI |
| VoodooHDA | 3.6.10 S540 variant, separately installed in macOS |
| S540Sensors | 1.0.0, NVIDIA `TG0D` temperature only |
| AirportItlwm | 2.4.0 tested variant |
| BigSurSDXC | 1.9.0, direct O2Micro match |
| VirtualSMC stack | 1.3.8 |
| S540 Tasti | 0.1.3, separately installed app/driver pair |

## Install the stable Intel profile

Use [v0.3.0](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/releases/tag/v0.3.0)
and follow its [installation guide](docs/releases/v0.3.0/INSTALL.md). It is the
known-good recovery route and intentionally retains `-wegnoegpu`.

The v0.3.0 payload contains `EFI/OC`, not a complete EFI partition. Preserve
the existing `EFI/Microsoft`, `EFI/BOOT`, rEFInd files and firmware entries.
Public SMBIOS fields are placeholders and must be personalized locally.

## Install the experimental NVIDIA profile

Start with the [v0.4.0 NVIDIA installation
guide](docs/releases/v0.4.0-nvidia-experimental.1/INSTALL.md), then read the
[security boundary](docs/releases/v0.4.0-nvidia-experimental.1/SECURITY.md) and
[rollback procedure](docs/releases/v0.4.0-nvidia-experimental.1/ROLLBACK.md)
before changing the active system.

The release asset is an **assembler kit**, not a preassembled EFI or a NullMoth
mirror. On the Mac it:

1. downloads the pinned v0.3.0/OpenCore/AMFIPass/NullMoth upstream inputs;
2. verifies exact sizes, SHA-256 values and the signed NullMoth archives;
3. builds a sanitized S540 NVIDIA EFI locally;
4. prepares the exact GTX 1650 Max-Q and NVIDIA HDA matches locally; and
5. leaves installation behind an explicit administrator confirmation.

The EFI alone does not install NullMoth, NMXAudio, VoodooHDA or S540 Tasti.
Never publish the generated local EFI, installed driver tree, Kernel
Collections or private SMBIOS values as a substitute release asset.

## Security boundary of the experimental profile

The NVIDIA profile is intentionally less secure than the stable baseline. It
uses `SecureBootModel=Disabled`, reduced SIP (`csr-active-config=0x0A43`) and
boot arguments that relax AMFI/task-port enforcement for the experimental
driver path. This materially expands the attack surface. Use only trusted
software, do not expose this configuration as a general recommendation and
return to v0.3.0 when NVIDIA/HDMI is not needed.

The public configuration contains no real serial, MLB, SystemUUID or ROM. Keep
those values private and preserve the source laptop's known-good identity only
in its local copy.

## Structural limits that an EFI cannot fix

Only these two items are currently classified as structural limits:

- **Native USB-C video:** this laptop does not route DisplayPort Alt Mode lanes
  to its USB-C connector. USB-C data works, but no OpenCore, ACPI or kext change
  can create the missing physical display path. A DisplayLink adapter is a
  separate USB graphics device, not native USB-C video.
- **Native Touch ID:** the Goodix `27c6:55b4` sensor is not paired with an Apple
  Secure Enclave and cannot become Apple's authenticated Touch ID through an
  EFI or kext. A future userspace biometric experiment would not be native Touch
  ID and could disturb the fingerprint enrollment used by Windows.

Do not broaden “will never work” beyond those hardware/security boundaries.
The following are **unavailable, paused or not yet qualified**, not proven
impossible:

- F8 camera privacy switching and the still-unverified F10 display action;
- fan RPM telemetry (the physical fans work) and sustained-load cooling data;
- overnight standby, hibernation and calibrated standby drain;
- SD writes, throughput and additional card types/capacities;
- AirDrop/Continuity and an actual wireless-display streaming session;
- automatic Bluetooth headset reconnection and broader peripheral combinations.

## Separate macOS companions

Copying either EFI does not install the complete audio or hotkey setup:

- **Internal audio:** retain or install the [VoodooHDA 3.6.10 S540
  package](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/releases/download/v0.3.0/S540-audio-Tahoe-3.6.10-v1.zip).
  AppleALC is not the active audio path.
- **Hotkeys:** retain or install [S540 Tasti
  0.1.3](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/releases/download/v0.3.0/S540-Tasti-v1.3.zip)
  for F4/F7/F9 and grant its documented macOS permissions.
- **HDMI audio:** the experimental local installer places the exact-match
  NMXAudio bundle in `/Library/Extensions` and rebuilds the Auxiliary Kernel
  Collection. It must not be duplicated in `EFI/OC/Kexts`.

## Documentation and source layout

- [v0.4.0 NVIDIA release notes](docs/releases/v0.4.0-nvidia-experimental.1/RELEASE-NOTES.md),
  [installation](docs/releases/v0.4.0-nvidia-experimental.1/INSTALL.md),
  [provenance](docs/releases/v0.4.0-nvidia-experimental.1/SOURCE-PROVENANCE.md),
  [security](docs/releases/v0.4.0-nvidia-experimental.1/SECURITY.md) and
  [rollback](docs/releases/v0.4.0-nvidia-experimental.1/ROLLBACK.md)
- [v0.3.0 installation](docs/releases/v0.3.0/INSTALL.md), [release
  notes](docs/releases/v0.3.0/RELEASE-NOTES.md) and [source
  provenance](docs/releases/v0.3.0/SOURCE-PROVENANCE.md)
- [Documentation index](docs/README.md), [hardware status](docs/status/hardware.md)
  and [roadmap](docs/status/roadmap.md)

**Code → Download ZIP downloads repository sources, not an assembled EFI or a
macOS installer.**

| Path | Purpose |
|---|---|
| [packages/](packages/) | Feature sources, launchers and runtime components |
| [builders/](builders/) | Reproducible release-kit assembly |
| [tests/](tests/) | Validation and fixtures |
| [config/](config/) | ACPI, versioned EFI profiles, asset locks and USB mapping |
| [docs/](docs/README.md) | Setup, evidence, recovery, research and roadmap |
| [patches/](patches/) / [licenses/](licenses/) | Driver patches and dependency notices |
| [.github/workflows/](.github/workflows/) | Build, validation and publication workflows |
| [archive/](archive/README.md) | Superseded procedures and history |
