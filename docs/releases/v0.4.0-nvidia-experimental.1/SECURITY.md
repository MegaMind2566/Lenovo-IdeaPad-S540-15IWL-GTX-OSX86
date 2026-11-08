# Security boundary for v0.4.0-nvidia-experimental.1

The experimental NVIDIA profile intentionally weakens macOS security controls
to load and exercise a non-Apple GPU driver stack. It is materially less secure
than the stable Intel profile and should be enabled only on the dedicated source
laptop, with trusted software and a tested recovery route.

## Settings that expand the attack surface

The reviewed profile uses:

- `SecureBootModel=Disabled`;
- SIP value `csr-active-config=0x0A43` (plist bytes `43 0A 00 00`);
- `amfi_get_out_of_my_way=0x1` and `amfi=0x80`;
- `ipc_control_port_options=0`; and
- AMFIPass 1.4.1 from the exact pinned upstream archive.

The complete tested boot-argument string is:

```text
-ibtcompatbeta revpatch=sbvmm,cpuname alcid=11 voodoo-layout-id=11 -igfxblr nvfb=1 nvaccel=1 nvfbheads=4 -nvkmsnosmooth amfi_get_out_of_my_way=0x1 amfi=0x80 ipc_control_port_options=0 nvrmsettle=10000 gfxrst=4 applbkl=1
```

These controls affect signature enforcement, platform trust and process/task
access. They can make malicious or tampered software easier to load and reduce
the protections normally expected from macOS. They are not a recommendation
for a general-purpose Hackintosh configuration.

## Safe operating assumptions

- Use this profile only on the verified 81SW hardware and macOS 26.7.1 build
  25G241.
- Install applications and packages only from trusted sources while this profile
  is active.
- Do not use the machine as the sole store of important credentials or data.
- Keep v0.3.0 and a complete EFI/system backup independently accessible.
- Do not expose SSH, file sharing or other remote services unnecessarily.
- Return to the stable profile and remove the experimental macOS-side stack when
  NVIDIA/HDMI is no longer required.

Disabling another security check to get past a refusal is not an accepted fix.

## Supply-chain controls in the kit

The release kit minimizes, but cannot eliminate, supply-chain risk:

- every remote URL is HTTPS and exact-version pinned;
- expected byte size and SHA-256 are checked before extraction;
- both NullMoth archives require their official Ed25519 signatures;
- NullMoth's internal `SHA256SUMS` is verified before target patches;
- extraction rejects absolute/traversal paths, unsafe links, duplicates and
  unexpected file types;
- only reviewed plist values may be changed;
- post-signing hashes bind the exact NVRM/NVAccel executables;
- the privileged installer consumes an anonymous, pre-confirmation TAR through
  standard input and verifies it in a root-private staging directory;
- OpenCore's config is checked with the matching 1.0.8 `ocvalidate`; and
- the generated local output receives a manifest/checksum.

Hash/signature checks prove correspondence with the pinned upstream bytes; they
do not prove that upstream software is vulnerability-free. Review the release
source and prompts before granting administrator access.

## Root installation and Kernel Collections

The macOS-side installer requires `sudo` because it writes to
`/Library/Extensions`, `/Library/GPUBundles`, `/Library/NullMoth` and the
Auxiliary Kernel Collection. It must show the exact verified/prepared state
before asking for approval. The tree visible to the user is never reopened by
the privileged process: the prepared bytes are frozen beforehand in an
anonymous file descriptor, hashed, passed to root, rehashed and extracted under
`/private/var/tmp` with a root-private parent. This closes the confirmation-time
path-replacement window; the payload's mutable `SHA256SUMS` is not the privilege
handoff trust root.

NMXAudio is intentionally limited to NVIDIA HDA `10DE:10FA`. A generic match can
attach to other HDA controllers and conflict with the working VoodooHDA path.
Never put NMXAudio in both `/Library/Extensions` and `EFI/OC/Kexts`.

Only the reviewed local NVRM/NVAccel modifications receive ad-hoc signatures.
Do not globally weaken private-symbol or callback/export validation to admit an
unrelated binary.

The Auxiliary Kernel Collection is bound to the OS build and installed driver
set. Do not share it and do not replace a new collection after an OS update with
the old 25G241 file.

## Private identity and logs

The public config contains empty/zero SMBIOS identity fields. Keep the laptop's
real serial, MLB, SystemUUID and ROM only in private local backups and the active
config. Before sharing a diagnostic, search it for those fields, user names,
volume names, Wi-Fi identifiers and other unique values.

Do not publish locally generated EFI archives, `/Library/NullMoth`, Kernel
Collections, NVRAM dumps, full IORegistry captures or unreviewed OpenCore logs.

## Dual-boot boundary

Windows must retain its native rEFInd/firmware route. Avoid starting Windows
through an experimental macOS identity/ACPI path. Never replace or erase
`EFI/Microsoft` while installing this profile, and do not assume the current
disk number remains constant between boots.

## OS updates

macOS 26.7.2 (25G332) is untested and changes security- and driver-relevant
subsystems. Preserve backups, audit the post-update collection read-only and
rebuild only if evidence shows an omission. Do not force the 25G241 installer
past its build/hash guards.

Use [ROLLBACK.md](ROLLBACK.md) to remove the experimental stack. Re-enabling
stronger security settings before the upstream uninstaller completes can make
the installed files immutable even for root, so follow the documented order.
