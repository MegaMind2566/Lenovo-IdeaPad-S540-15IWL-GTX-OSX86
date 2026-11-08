# Source provenance for v0.4.0-nvidia-experimental.1

This prerelease publishes a deterministic **local assembly workflow**, not the
locally working NullMoth/EFI/AuxKC binary state. The workflow pins exact inputs,
checks hashes and signatures and produces the target files only on the user's
Mac.

## Target identity

| Property | Bound value |
|---|---|
| Laptop | Lenovo IdeaPad S540-15IWL GTX, 81SW |
| NVIDIA GPU | `10DE:1F91`, subsystem `17AA:3806` |
| NVIDIA HDA | `10DE:10FA`, class `0x04030000&0xffff0000` |
| Tested OS | macOS Tahoe 26.7.1, build 25G241 |
| OpenCore | 1.0.8 RELEASE |
| NullMoth | 2.7.2, commit `18ba05f38b5eadea8b5ae05834bb51c61fb4c5c3` |
| Public SMBIOS model | `MacBookPro16,2`, with identity fields sanitized |

The public configuration replaces private values as follows:

| Field | Public value |
|---|---|
| `SystemSerialNumber` | empty string |
| `MLB` | empty string |
| `SystemUUID` | `00000000-0000-0000-0000-000000000000` |
| `ROM` | six zero bytes |

These are sanitization markers, not a boot-ready shared identity.

## Exact downloaded inputs

The release kit downloads these URLs directly and refuses a size/hash mismatch.
It does not silently substitute the current “latest” release.

| Input | Official/upstream URL | Size | SHA-256 |
|---|---|---:|---|
| Stable v0.3.0 EFI baseline | [S540-Tahoe-EFI-v0.3.0.zip](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/releases/download/v0.3.0/S540-Tahoe-EFI-v0.3.0.zip) | 47,092,619 | `f5a9ad08cfa72e14569bc1040728c7480f7966a58a1adb9bf1e4ff84e303e46d` |
| OpenCore 1.0.8 RELEASE | [OpenCore-1.0.8-RELEASE.zip](https://github.com/acidanthera/OpenCorePkg/releases/download/1.0.8/OpenCore-1.0.8-RELEASE.zip) | 10,544,084 | `2011e8b7216ecb2645d97ea710df965947edd406846e92050b9bc4190be6d27b` |
| AMFIPass 1.4.1 RELEASE | [AMFIPass-v1.4.1-RELEASE.zip](https://github.com/bluppus20/AMFIPass/releases/download/1.4.1/AMFIPass-v1.4.1-RELEASE.zip) | 191,154 | `07b266145906db41f4b13a7938fbb173ea28888cc1fa65f84417f8820adc961e` |
| NullMoth 1401 Mac 2.7.2 | [1401-Mac-2.7.2.zip](https://github.com/nullmoth/nvidia-macos-driver/releases/download/v2.7.2/1401-Mac-2.7.2.zip) | 2,635,537 | `008e8bdb88920a17211f07c45b0df2601bdde2d9a41af3ebe393944b74947dfd` |
| NullMoth 1401 signature | [1401-Mac-2.7.2.zip.sig](https://github.com/nullmoth/nvidia-macos-driver/releases/download/v2.7.2/1401-Mac-2.7.2.zip.sig) | recorded in source lock | `aa1cc71060113fddb3bba9985f5c2ed98e1768c2059d7ae0657ceb1f32142156` |
| NullMoth 2.7.2 payload | [nullmoth-nvidia-2.7.2.tar.gz](https://github.com/nullmoth/nvidia-macos-driver/releases/download/v2.7.2/nullmoth-nvidia-2.7.2.tar.gz) | 264,616,298 | `928557fece27637b1184f5655833566e7d516b22708cc341b28d555055d8e50e` |
| NullMoth payload signature | [nullmoth-nvidia-2.7.2.tar.gz.sig](https://github.com/nullmoth/nvidia-macos-driver/releases/download/v2.7.2/nullmoth-nvidia-2.7.2.tar.gz.sig) | recorded in source lock | `378e8d966777538ddb300bf65dea9fec23cfcc704c3843913ca9779a6630ac0f` |

Both downloaded NullMoth archives were independently verified before release
preparation using the upstream Ed25519 public key:

```text
ztPmcj+mcHYM1X2lrp24yjq0xBuzke7gh5XJ3E2fd4E=
```

The verifier retained by the kit follows the upstream 1401 verifier and carries
its PolyForm Noncommercial 1.0.0 license and required notice. Hash comparison is
performed before signature verification; neither replaces the other.

## Exact target-specific bytes

### AMFIPass

The candidate AMFIPass bundle matches the downloaded 1.4.1 release:

| File | SHA-256 |
|---|---|
| `AMFIPass.kext/Contents/Info.plist` | `eb3fda04c0e8c8ce0ef4cfc984dcfb771db6aee476d379bd4bc3b7a74a00e4e9` |
| `AMFIPass.kext/Contents/MacOS/AMFIPass` | `4c35bc196d35c69b5f9dca83fe733801211c7828716f51585c7f5450039ca884` |

AMFIPass is downloaded locally because its release repository does not provide
an explicit redistribution license for this project's release asset.

### NMXAudio

The NMXAudio executable remains byte-for-byte identical to the official
NullMoth 2.7.2 payload. Only its local `Info.plist` is replaced to bind it to the
NVIDIA HDA function and avoid matching Intel/Realtek HDA controllers.

| File | SHA-256 |
|---|---|
| Official `NMXAudio` executable | `77e19e244978ce64e4505c4701069edfe609379f91a9c76313b4a27ded4ab07a` |
| Exact-match `Info.plist` | `ebff8ac2ea5b57f7d6ccbb764f56025213a22a4156df8dd3b8c9c9e64f126d4a` |

The final tested Auxiliary Kernel Collection had SHA-256
`11242eba86841ccfe5148ea2a185c0f36f141ab360254f06f50cccfc57db3271`.
That value records the source laptop result; the collection is not a portable
release artifact and is not redistributed.

### S540Sensors

The project-owned S540Sensors source is MIT licensed. It reads the genuine
NVAccel temperature and publishes only `TG0D` through VirtualSMC. The binary
also compiles Lilu and VirtualSMCSDK header code under their BSD 3-Clause
licenses and statically links MacKernelSDK `libkmod.a` under APSL 2.0.

| File | SHA-256 |
|---|---|
| `S540Sensors.kext/Contents/MacOS/S540Sensors` | `749c18c5cd1a29914b6536f67a599af840574677fa4865d5865c9282b33f0238` |
| `S540Sensors.kext/Contents/Info.plist` | `d092d52684ea384d15ff33ad8b7cce5fe52ae08e726f32ca036f3003e6421711` |

The linked MacKernelSDK commit is
`3f750085caa17ec3a7880f11c11bf4f48cd6a164`; its `libkmod.a` SHA-256 is
`7a751671bbe96c9c7b5416078df600b768c00c0dc5178d8acd8f52539c7ccd4e`.
The Covered Code source is available under APSL 2.0 at
<https://github.com/acidanthera/MacKernelSDK/tree/3f750085caa17ec3a7880f11c11bf4f48cd6a164/Library/kmod>.
The release kit includes the complete APSL, both BSD licenses and a detailed
third-party notice; the same source-availability notice is embedded in the
S540Sensors executable. It performs no EC scan, fan write or fabricated RPM
publication.

## Local assembly and transformation boundary

The EFI assembler starts from the existing v0.3.0 archive, replaces the public
configuration with the reviewed/sanitized experimental config, installs the
exact upstream AMFIPass bytes, adds the reviewed S540Sensors bundle and extracts the
exact NullMothSafe/OpenCore fallback tools from their verified archives. It then
runs OpenCore 1.0.8 `ocvalidate` and emits its own manifest and checksum.

The macOS-side preparer verifies NullMoth's internal hash list before changing
anything. It applies only the reviewed target bindings:

- GTX 1650 Max-Q `0x1f9110de` in live NVRM/NVAccel and both retained
  OS-version NVAccel copies; and
- NVIDIA HDA `0x10fa10de` plus class match for NMXAudio.

Only locally modified NVRM/NVAccel bundles are ad-hoc signed. Before the user
can approve installation, the preparer freezes the verified tree into an
anonymous TAR file descriptor. The root process verifies that exact TAR and
extracts it into a root-private staging directory; it never trusts a mutable
`SHA256SUMS` or reopens the user-facing tree. The installed Auxiliary Kernel
Collection is rebuilt from real `/Library/Extensions` paths, never a temporary
repository path.

## Why binaries are assembled locally

The NVIDIA firmware license permits redistribution only for use with an
OSI-licensed operating system, which does not describe macOS. The NullMoth
payload also contains proprietary NVIDIA compiler/runtime libraries for which
this project has no independent redistribution grant. Other retained EFI
components include Apple-derived or license-ambiguous binaries, and AMFIPass's
release repository lacks an explicit license.

Consequently the project does not publish the raw local NullMoth payload, the
private candidate EFI or an Auxiliary Kernel Collection. The public kit contains
only material the project can publish, source locks, verifier/license notices
and code that downloads the exact upstream bytes for local use. This is a
distribution boundary, not a claim about the legal status of an end user's use.

## Validation categories

These milestones must remain separate:

| Milestone | Evidence |
|---|---|
| Source binding | Exact URLs, byte sizes, SHA-256 values and NullMoth signatures |
| EFI assembly | Sanitized identity, allowlisted contents, OpenCore 1.0.8 source match and `ocvalidate` success |
| Package preparation | Exact target plist deltas, unchanged NMXAudio executable, regenerated hashes and refusal guards |
| Target kernel loading | Loaded NVRM/NVAccel/NVRMFB/NVRMAGDC/NMXAudio and the operational pre-notice S540Sensors 1.0.0 build, plus live-path AuxKC inspection on 25G241; the released S540Sensors compliance rebuild is compile/signature checked but was not separately target-loaded |
| GPU/display initialization | Metal execution/rendering, HDMI 1080p60, HDMI audio, brightness and the stated short sleep/wake result |

A source/hash success does not prove target loading; target loading does not
prove GPU initialization; GPU initialization does not establish hibernation or
indefinite stability.

macOS 26.7.2 build 25G332 is outside this provenance boundary.
