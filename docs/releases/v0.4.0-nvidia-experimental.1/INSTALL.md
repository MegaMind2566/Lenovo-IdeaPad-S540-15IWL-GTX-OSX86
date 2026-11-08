# Installing v0.4.0-nvidia-experimental.1

This prerelease targets only the **Lenovo IdeaPad S540-15IWL GTX (81SW)** with
NVIDIA GTX 1650 Max-Q `10DE:1F91`, subsystem `17AA:3806`, running macOS Tahoe
**26.7.1 (25G241)**. It was not qualified on another S540 revision or on macOS
26.7.2 (25G332).

Read [SECURITY.md](SECURITY.md) and [ROLLBACK.md](ROLLBACK.md) completely before
starting. Keep the independent [v0.3.0 Intel
release](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/releases/tag/v0.3.0)
available on a known-working alternate boot route.

## What the release asset is

`S540-NVIDIA-release-kit-v0.4.0-nvidia-experimental.1.zip` is a local
**assembler/installer kit**. It is not a complete prebuilt EFI, a NullMoth
distribution or a generated Auxiliary Kernel Collection.

The kit downloads exact upstream inputs, verifies pinned sizes/SHA-256 values
and verifies the official NullMoth signatures. It then creates the target EFI
and prepared NullMoth tree locally. It does not upload the result anywhere.

Do not use repository **Code → Download ZIP** as the release asset.

## 1. Confirm the exact starting state

In Terminal, confirm the macOS build:

```bash
sw_vers -productVersion
sw_vers -buildVersion
```

Continue only when the build is `25G241`. Stop if it is `25G332` or another
build; this kit intentionally does not claim compatibility with 26.7.2.

Confirm the target NVIDIA device:

```bash
system_profiler SPDisplaysDataType
ioreg -l -p IODeviceTree | grep -i -E '1f91|3806|NVIDIA'
```

The checks must describe the GTX 1650 Max-Q in the intended Lenovo 81SW. Never
bypass a hardware, source-hash, OS-build or existing-state refusal.

## 2. Make recoverable backups first

Before downloading or installing anything, retain:

- a complete byte-for-byte backup of the current EFI partition;
- the working v0.3.0 `EFI/OC` directory with its private local SMBIOS identity;
- `EFI/Microsoft`, the existing `EFI/BOOT`, rEFInd files and firmware entries;
- `/Library/Extensions`, `/Library/NullMoth` if already present, and
  `/Library/KernelCollections/AuxiliaryKernelExtensions.kc`;
- a way to select the known-good loader without the experimental EFI; and
- important user data outside the machine.

Do not format the EFI partition. Do not replace the whole EFI directory on the
internal disk.

## 3. Download and verify the public kit

Download both release assets from the
[v0.4.0-nvidia-experimental.1
prerelease](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/releases/tag/v0.4.0-nvidia-experimental.1):

```text
S540-NVIDIA-release-kit-v0.4.0-nvidia-experimental.1.zip
S540-NVIDIA-release-kit-v0.4.0-nvidia-experimental.1.zip.sha256
```

From the download directory, verify the sidecar before extracting:

```bash
shasum -a 256 -c S540-NVIDIA-release-kit-v0.4.0-nvidia-experimental.1.zip.sha256
```

Expect `OK`. A mismatch means stop and discard the download.

## 4. Assemble the EFI locally

Extract the verified kit, open its folder and run the included
`ASSEMBLA-EFI-NVIDIA.command`. macOS may require Control-click → Open for the
first launch.

The assembler must complete all of these before producing an output archive:

1. download the pinned v0.3.0 baseline, OpenCore 1.0.8 RELEASE, AMFIPass 1.4.1
   and NullMoth 1401 2.7.2 assets;
2. validate exact byte sizes and SHA-256 values;
3. verify the NullMoth Ed25519 signature;
4. reject unsafe archive paths and unexpected files;
5. install the sanitized target configuration and reviewed S540Sensors bundle;
6. add the OpenCore 1.0.8 fallback loader for a standalone local archive; and
7. run OpenCore 1.0.8 `ocvalidate` and generate a manifest/checksum.

The resulting local archive is expected to be named
`S540-Tahoe-NVIDIA-EFI-v0.4.0-nvidia-experimental.1.zip`. This output is private:
do not attach it to an issue/release or commit it to the repository.

## 5. Personalize the sanitized identity

The public experimental config uses `MacBookPro16,2` and deliberately contains
no real SMBIOS identity:

- `SystemSerialNumber` and `MLB` are empty;
- `SystemUUID` is `00000000-0000-0000-0000-000000000000`; and
- `ROM` is six zero bytes.

Before booting, place the already-working laptop's private identity into the
local output. Never copy another user's values and never publish yours. Re-run
the included OpenCore 1.0.8 `ocvalidate` after editing the config.

Do not replace the experimental config with the v0.3.0 file: that would discard
the reviewed NVIDIA, HDMI, brightness and security settings.

## 6. Prepare and install the macOS-side driver tree

While still on macOS 26.7.1 (25G241), run the included
`INSTALLA-NULLMOTH-S540.command` from the verified kit.

Before requesting administrator confirmation, it must:

- download the official signed NullMoth 2.7.2 tarball;
- verify its pinned size, SHA-256 and Ed25519 signature;
- verify NullMoth's internal `SHA256SUMS`;
- restrict NVRM/NVAccel to the exact GTX 1650 Max-Q device in both live and
  retained OS-version copies;
- retain the unchanged official NMXAudio executable but replace its personality
  with the exact `10DE:10FA` NVIDIA HDA match;
- ad-hoc sign only the locally modified NVRM/NVAccel bundles;
- regenerate the prepared tree's hash list;
- verify exact post-signing NVRM/NVAccel executable hashes;
- freeze the approved bytes in an anonymous TAR before prompting; and
- retain the prepared package and uninstall path for recovery.

Only then may it ask permission to run the upstream installer with `sudo`. That
step verifies the same anonymous TAR, extracts it under a root-private temporary
directory, writes to `/Library/Extensions`, `/Library/GPUBundles`,
`/Library/NullMoth` and rebuilds the Auxiliary Kernel Collection. It does not
reopen the user-writable prepared tree after confirmation. Read the prompt and
the exact paths before approving it.

NMXAudio belongs in `/Library/Extensions` and the Auxiliary Kernel Collection.
It must **not** also exist in `EFI/OC/Kexts`. VoodooHDA 3.6.10 remains the
separate internal/3.5 mm audio driver.

## 7. Put the local EFI on a testable boot route

Prefer a separately selectable test EFI first. On an existing internal
dual-boot installation, preserve `EFI/Microsoft`, rEFInd and the current
fallback loader. Normally replace only the backed-up `EFI/OC` directory with
the locally assembled `EFI/OC`.

The generated `EFI/BOOT/BOOTx64.efi` exists so the local archive can form a
standalone test route. Do not overwrite a working internal rEFInd/fallback path
without confirming how the firmware currently starts it.

Verify once more that the local config contains the private identity and that
the stable v0.3.0 route remains selectable, then restart.

## 8. Verify after restart

Run the kit's read-only `VERIFICA-INSTALLAZIONE.command`. Also confirm manually:

- OpenCore and macOS reach the desktop without a recovery loop;
- the internal BOE panel remains online and the brightness slider/F11/F12 work;
- the GTX 1650 Max-Q appears as TU117 4 GB with Metal support;
- CPU temperature remains available and `TG0D` reports the NVIDIA temperature;
- HDMI reaches 1920×1080 60 Hz on the tested display;
- `NVIDIA (0x0094) (HDMI/DP 8ch)` appears at 48 kHz and playback is heard;
- internal speakers/microphone and the 3.5 mm path still work through VoodooHDA;
- Wi-Fi, Bluetooth headset, touchpad, USB and the known SD card retain their
  stated behavior; and
- `kmutil inspect` shows NMXAudio from `/Library/Extensions`, with no duplicate
  NMXAudio entry in the EFI.

Do not begin sleep qualification until ordinary boot, internal display,
brightness, audio and recovery access are all confirmed. The existing evidence
covers one controlled 54-second cycle, not overnight standby or hibernation.

## 9. Stop conditions

Return to [ROLLBACK.md](ROLLBACK.md) immediately if any of these occurs:

- repeated boot failure or loss of the internal display;
- missing brightness control after confirming `applbkl=1` is present;
- a NullMoth/NMXAudio bundle is absent from or duplicated in the collection;
- the exact GPU/HDA device checks do not match;
- the assembler/installer reports a hash, signature or source mismatch; or
- the system is not still macOS 26.7.1 (25G241).

Do not solve a refusal by deleting checks, substituting current “latest”
downloads or installing a generic NMXAudio personality.

## Companion software and evidence limits

The EFI and NullMoth installer do not install S540 Tasti 0.1.3 or the tested
VoodooHDA 3.6.10 S540 companion. Retain the working installations or use the
separate v0.3.0 release assets.

Native USB-C video and native Touch ID are structural limitations described in
[RELEASE-NOTES.md](RELEASE-NOTES.md). Fan RPM, F8 privacy switching, F10,
overnight sleep, hibernation, wireless streaming and broader SD testing remain
unavailable or unqualified rather than proven impossible.
