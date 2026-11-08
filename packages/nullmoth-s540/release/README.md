# Lenovo S540 NVIDIA experimental release kit

This kit does not redistribute NullMoth, NVIDIA firmware, AMFIPass, OpenCore,
Apple drivers or a preassembled third-party EFI. It downloads the exact public
upstream archives listed in `sources.lock.json`, verifies their byte size and
SHA-256, verifies both NullMoth Ed25519 signatures, and assembles the reviewed
Lenovo 81SW profile locally.

The profile was tested with macOS 26.7.1 (25G241), OpenCore 1.0.8 and NullMoth
2.7.2. It is experimental. SecureBootModel is disabled, SIP is reduced to
`0x0A43`, and the tested boot arguments relax AMFI/task-port policy. Use only
trusted software and keep the stable v0.3.0 EFI as a recovery path.

1. Run `ASSEMBLA-EFI-NVIDIA.command`. It creates a local EFI ZIP after a full
   hash-manifest check and OpenCore validation. It never writes the ESP.
2. Personalize the public SMBIOS placeholders. Back up the ESP, preserve
   `EFI/BOOT`, `EFI/Microsoft` and rEFInd where applicable, then merge the EFI
   deliberately.
3. Run `INSTALLA-NULLMOTH-S540.command`. It verifies the signed upstream 2.7.2
   driver, prepares exact GTX 1650 Max-Q (`0x1f9110de`) and HDMI audio
   (`10DE:10FA`) matches, and asks for the literal confirmation `INSTALLA`
   before invoking the official installer with `sudo`. The privileged handoff
   uses an anonymous, pre-confirmation TAR and a root-private staging directory;
   it never reopens the user-writable prepared tree.
4. Restart and run `VERIFICA-INSTALLAZIONE.command`.

NMXAudio is installed in `/Library/Extensions` and the Auxiliary Kernel
Collection, never in EFI. VoodooHDA and the S540 hotkey helper remain separate
packages. Do not reuse a prepared Auxiliary Kernel Collection after a macOS
update; rerun the installer so it is rebuilt for the running OS.

Preparation and installation refuse any host other than x86_64, macOS 26.7.1
build 25G241 and the exact Lenovo PCI identity `10DE:1F91 / 17AA:3806`. A later
macOS build must be qualified and explicitly added to the source lock first.

The archive includes `S540Sensors.kext` 1.0.0. Its project source is MIT
licensed; its binary also incorporates Lilu/VirtualSMC header code under the
BSD 3-Clause license and Apple Covered Code from MacKernelSDK's `libkmod` under
APSL 2.0. Exact licenses, notices and source locations are in `LICENSES/` and
the APSL source-availability notice is embedded in the binary. S540Sensors
exposes NVIDIA temperature as `TG0D`; it does not invent fan tachometer data or
write fan-control registers.
