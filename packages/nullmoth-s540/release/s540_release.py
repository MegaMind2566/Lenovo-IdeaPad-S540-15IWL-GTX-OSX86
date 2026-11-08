#!/usr/bin/env python3
"""Build and use the provenance-locked Lenovo S540 NVIDIA release kit."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import plistlib
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import unicodedata
import urllib.parse
import urllib.request
import zipfile

from nullmoth_release_sig import verify_file as verify_nullmoth_file


SOURCE_NAMES = (
    "stable_efi",
    "opencore",
    "amfipass",
    "nullmoth_1401",
    "nullmoth_driver",
)
MAX_ZIP_SIZE = 1024 * 1024 * 1024
MAX_TAR_SIZE = 4 * 1024 * 1024 * 1024
CHUNK = 1024 * 1024
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


ROOT_INSTALL_SCRIPT = r'''set -euo pipefail
expected_sha="$1"
if [[ ${#expected_sha} -ne 64 || "$expected_sha" == *[!0-9a-f]* ]]; then
  echo "Digest payload non valido" >&2
  exit 64
fi
stage="$(/usr/bin/mktemp -d /private/var/tmp/s540-nullmoth-install.XXXXXX)"
case "$stage" in
  /private/var/tmp/s540-nullmoth-install.*) ;;
  *) exit 70 ;;
esac
cleanup() { /bin/rm -rf "$stage"; }
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 129' HUP
trap 'exit 143' TERM
/bin/cat > "$stage/payload.tar"
actual_sha="$(/usr/bin/shasum -a 256 "$stage/payload.tar" | /usr/bin/awk '{print $1}')"
if [[ "$actual_sha" != "$expected_sha" ]]; then
  echo "Payload cambiato durante il passaggio privilegiato" >&2
  exit 65
fi
/bin/mkdir "$stage/root"
/usr/bin/tar -xpf "$stage/payload.tar" -C "$stage/root"
/bin/rm "$stage/payload.tar"
if [[ ! -f "$stage/root/install.sh" || -L "$stage/root/install.sh" ]]; then
  echo "install.sh regolare mancante" >&2
  exit 66
fi
cd "$stage/root"
/bin/bash ./install.sh </dev/tty
'''


def _default_kit_root() -> Path:
    here = Path(__file__).resolve().parent
    if (here / "sources.lock.json").is_file():
        return here
    if (here.parent / "sources.lock.json").is_file():
        return here.parent
    return here


KIT_ROOT = _default_kit_root()
DEFAULT_LOCK = KIT_ROOT / "sources.lock.json"


def sha256_data(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def load_source_lock(path: Path = DEFAULT_LOCK) -> dict:
    path = Path(path)
    lock = json.loads(path.read_text(encoding="utf-8"))
    if lock.get("schema") != 1:
        raise ValueError("Unsupported sources.lock.json schema")
    for key in ("release", "sources", "profile", "device"):
        if not isinstance(lock.get(key), dict):
            raise ValueError(f"Missing lock object: {key}")
    release_keys = {
        "tag", "title", "package_name", "package_prefix",
        "tested_macos_version", "tested_macos_build",
        "opencore_version", "nullmoth_version",
    }
    missing = release_keys - set(lock["release"])
    if missing:
        raise ValueError(f"Missing release lock fields: {sorted(missing)}")
    if lock["release"]["package_name"] != lock["release"]["package_prefix"] + ".zip":
        raise ValueError("Release package name/prefix mismatch")
    for name in SOURCE_NAMES:
        source = lock["sources"].get(name)
        if not isinstance(source, dict):
            raise ValueError(f"Missing locked source: {name}")
        for field in ("url", "filename", "size", "sha256"):
            if field not in source:
                raise ValueError(f"Missing {name}.{field}")
        if urllib.parse.urlsplit(source["url"]).scheme != "https":
            raise ValueError(f"Non-HTTPS source URL: {name}")
        if Path(source["filename"]).name != source["filename"]:
            raise ValueError(f"Unsafe source filename: {name}")
        if not isinstance(source["size"], int) or source["size"] <= 0:
            raise ValueError(f"Invalid source size: {name}")
        if not SHA256_RE.fullmatch(source["sha256"]):
            raise ValueError(f"Invalid source SHA-256: {name}")
        if name.startswith("nullmoth_"):
            for field in (
                "signature_url", "signature_filename", "signature_size",
                "signature_sha256",
            ):
                if field not in source:
                    raise ValueError(f"Missing {name}.{field}")
            if urllib.parse.urlsplit(source["signature_url"]).scheme != "https":
                raise ValueError(f"Non-HTTPS signature URL: {name}")
            if Path(source["signature_filename"]).name != source["signature_filename"]:
                raise ValueError(f"Unsafe signature filename: {name}")
            if not SHA256_RE.fullmatch(source["signature_sha256"]):
                raise ValueError(f"Invalid signature SHA-256: {name}")
    nullmoth_patch = lock["profile"].get("nullmoth_patch")
    required_patch_hashes = {
        "nmxaudio_info_before_sha256",
        "nmxaudio_info_after_sha256",
        "nmxaudio_executable_sha256",
        "nvrm_info_before_sha256",
        "nvrm_info_after_sha256",
        "nvrm_executable_sha256",
        "nvrm_installed_executable_sha256",
        "nvaccel_info_before_sha256",
        "nvaccel_info_after_sha256",
        "nvaccel_executable_sha256",
        "nvaccel26_executable_sha256",
        "nvaccel_prepared_executable_sha256",
        "nvaccel_installed_executable_sha256",
        "nvaccel15_installed_executable_sha256",
        "nvaccel26_installed_executable_sha256",
    }
    if not isinstance(nullmoth_patch, dict):
        raise ValueError("Missing profile.nullmoth_patch object")
    for field in sorted(required_patch_hashes):
        value = nullmoth_patch.get(field)
        if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
            raise ValueError(f"Invalid profile.nullmoth_patch hash: {field}")
    return lock


def _member_parts(name: str) -> tuple[str, ...]:
    if not isinstance(name, str) or not name or "\x00" in name or "\\" in name:
        raise ValueError(f"Unsafe archive member: {name!r}")
    path = PurePosixPath(name)
    if path.is_absolute():
        raise ValueError(f"Absolute archive member: {name}")
    parts = tuple(part for part in path.parts if part not in ("", "."))
    if not parts or any(part == ".." or ":" in part for part in parts):
        raise ValueError(f"Unsafe archive member: {name}")
    if any(any(ord(character) < 32 for character in part) for part in parts):
        raise ValueError(f"Control character in archive member: {name}")
    return parts


def _canonical_parts(parts: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(unicodedata.normalize("NFC", part).casefold() for part in parts)


def _empty_destination(destination: Path) -> Path:
    destination = Path(destination)
    if destination.is_symlink():
        raise ValueError(f"Extraction destination is a symlink: {destination}")
    if destination.exists():
        if not destination.is_dir() or any(destination.iterdir()):
            raise ValueError(f"Extraction destination is not empty: {destination}")
    else:
        destination.mkdir(parents=True)
    return destination.resolve()


def _reject_path_collisions(entries: list[tuple[tuple[str, ...], str]]) -> None:
    seen: dict[tuple[str, ...], str] = {}
    leaves: set[tuple[str, ...]] = set()
    for parts, kind in entries:
        canonical = _canonical_parts(parts)
        if canonical in seen:
            raise ValueError(f"Duplicate archive member: {'/'.join(parts)}")
        seen[canonical] = kind
        if kind != "directory":
            leaves.add(canonical)
    for canonical in seen:
        for end in range(1, len(canonical)):
            if canonical[:end] in leaves:
                raise ValueError("Archive member is nested below a non-directory")


def safe_extract_zip(
    archive: Path,
    destination: Path,
    *,
    max_total_size: int = MAX_ZIP_SIZE,
) -> list[Path]:
    """Extract a ZIP without allowing traversal, links, special files or bombs."""
    root = _empty_destination(destination)
    extracted: list[Path] = []
    with zipfile.ZipFile(Path(archive)) as bundle:
        records = []
        entries = []
        total = 0
        for info in bundle.infolist():
            parts = _member_parts(info.filename)
            mode = info.external_attr >> 16
            file_type = stat.S_IFMT(mode)
            is_directory = info.is_dir()
            if file_type == stat.S_IFLNK:
                raise ValueError(f"ZIP links are not permitted: {info.filename}")
            if file_type not in (0, stat.S_IFREG, stat.S_IFDIR):
                raise ValueError(f"ZIP special file is not permitted: {info.filename}")
            kind = "directory" if is_directory else "file"
            entries.append((parts, kind))
            total += 0 if is_directory else info.file_size
            if info.file_size > max_total_size or total > max_total_size:
                raise ValueError("ZIP expanded size exceeds the safety limit")
            if info.file_size and not info.compress_size and info.file_size > CHUNK:
                raise ValueError("ZIP member has an invalid compression ratio")
            records.append((info, parts, mode, kind))
        _reject_path_collisions(entries)
        for _, parts, mode, kind in sorted(records, key=lambda item: len(item[1])):
            if kind != "directory":
                continue
            target = root.joinpath(*parts)
            target.mkdir(parents=True, exist_ok=False)
            target.chmod((mode & 0o777) or 0o755)
            extracted.append(target)
        for info, parts, mode, kind in records:
            if kind != "file":
                continue
            target = root.joinpath(*parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(info, "r") as source, target.open("xb") as output:
                shutil.copyfileobj(source, output, CHUNK)
            if target.stat().st_size != info.file_size:
                raise ValueError(f"Truncated ZIP member: {info.filename}")
            target.chmod((mode & 0o777) or 0o644)
            extracted.append(target)
    return extracted


def safe_extract_tar(
    archive: Path,
    destination: Path,
    *,
    max_total_size: int = MAX_TAR_SIZE,
) -> list[Path]:
    """Extract a tar archive safely, preserving only internal relative links."""
    root = _empty_destination(destination)
    extracted: list[Path] = []
    with tarfile.open(Path(archive), "r:*") as bundle:
        records = []
        entries = []
        total = 0
        for member in bundle.getmembers():
            parts = _member_parts(member.name)
            link_parts = None
            if member.isdir():
                kind = "directory"
            elif member.isfile():
                kind = "file"
                total += member.size
                if member.size > max_total_size or total > max_total_size:
                    raise ValueError("tar expanded size exceeds the safety limit")
            elif member.issym():
                kind = "symlink"
                link_parts = _member_parts(member.linkname)
                if ".." in PurePosixPath(member.linkname).parts:
                    raise ValueError(f"Parent traversal in tar link: {member.name}")
            else:
                raise ValueError(f"tar special/hard-link member is not permitted: {member.name}")
            entries.append((parts, kind))
            records.append((member, parts, kind, link_parts))
        _reject_path_collisions(entries)
        for member, parts, kind, _ in sorted(records, key=lambda item: len(item[1])):
            if kind != "directory":
                continue
            target = root.joinpath(*parts)
            target.mkdir(parents=True, exist_ok=False)
            target.chmod(member.mode & 0o777)
            extracted.append(target)
        for member, parts, kind, _ in records:
            if kind != "file":
                continue
            target = root.joinpath(*parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            source = bundle.extractfile(member)
            if source is None:
                raise ValueError(f"Cannot read tar member: {member.name}")
            with source, target.open("xb") as output:
                shutil.copyfileobj(source, output, CHUNK)
            if target.stat().st_size != member.size:
                raise ValueError(f"Truncated tar member: {member.name}")
            target.chmod(member.mode & 0o777)
            extracted.append(target)
        for member, parts, kind, link_parts in records:
            if kind != "symlink":
                continue
            target = root.joinpath(*parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            assert link_parts is not None
            resolved = target.parent.joinpath(*link_parts).resolve(strict=False)
            if resolved != root and root not in resolved.parents:
                raise ValueError(f"tar link escapes extraction root: {member.name}")
            os.symlink(member.linkname, target)
            extracted.append(target)
    return extracted


def validate_public_config(source, lock: dict | None = None) -> dict:
    """Validate the exact public identity and all active NVIDIA profile policy."""
    lock = load_source_lock() if lock is None else lock
    data = bytes(source) if isinstance(source, (bytes, bytearray)) else Path(source).read_bytes()
    if sha256_data(data) != lock["profile"]["config_sha256"]:
        raise ValueError("Public config SHA-256 differs from the reviewed profile")
    config = plistlib.loads(data)
    generic = config["PlatformInfo"]["Generic"]
    expected_identity = {
        "MLB": "",
        "SystemSerialNumber": "",
        "SystemUUID": "00000000-0000-0000-0000-000000000000",
        "SystemProductName": lock["profile"]["system_product_name"],
    }
    for key, expected in expected_identity.items():
        if generic.get(key) != expected:
            raise ValueError(f"Unsafe or unexpected public SMBIOS field: {key}")
    if generic.get("ROM") != bytes(6):
        raise ValueError("Public ROM placeholder must be six zero bytes")
    nvram = config["NVRAM"]["Add"]["7C436110-AB2A-4BBB-A880-FE41995C9F82"]
    if nvram.get("boot-args") != lock["profile"]["boot_args"]:
        raise ValueError("NVIDIA boot arguments differ from the tested profile")
    csr = nvram.get("csr-active-config")
    if not isinstance(csr, bytes) or csr.hex() != lock["profile"]["csr_active_config"]:
        raise ValueError("csr-active-config differs from the reviewed profile")
    security = config["Misc"]["Security"]
    if security.get("ScanPolicy") != lock["profile"]["scan_policy"]:
        raise ValueError("ScanPolicy differs from the reviewed profile")
    if security.get("SecureBootModel") != lock["profile"]["secure_boot_model"]:
        raise ValueError("SecureBootModel differs from the reviewed profile")
    acpi = config["ACPI"]["Add"]
    kernel = config["Kernel"]["Add"]
    if any(item.get("Enabled") is not True for item in acpi + kernel):
        raise ValueError("Public profile contains an inactive ACPI or Kernel entry")
    if [item.get("Path") for item in acpi] != lock["profile"]["active_acpi_tables"]:
        raise ValueError("Active ACPI table order differs from the tested profile")
    if [item.get("BundlePath") for item in kernel] != lock["profile"]["active_kernel_bundles"]:
        raise ValueError("Active kernel bundle order differs from the tested profile")
    if config["Kernel"].get("Block") != []:
        raise ValueError("Public profile contains an inactive Kernel.Block entry")
    return config


def _download_locked(
    source: dict,
    cache_directory: Path,
    *,
    signature: bool = False,
) -> Path:
    cache_directory = Path(cache_directory)
    cache_directory.mkdir(parents=True, exist_ok=True)
    prefix = "signature_" if signature else ""
    url = source[prefix + "url"]
    filename = source[prefix + "filename"]
    expected_size = source[prefix + "size"]
    expected_sha = source[prefix + "sha256"]
    target = cache_directory / filename
    if target.exists():
        if not target.is_file() or target.stat().st_size != expected_size:
            raise ValueError(f"Cached input has the wrong size: {target}")
        if sha256_file(target) != expected_sha:
            raise ValueError(f"Cached input has the wrong SHA-256: {target}")
        return target
    temporary = target.with_name(target.name + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": "S540-release-kit/1"})
    try:
        with urllib.request.urlopen(request, timeout=120) as response, temporary.open("wb") as output:
            if urllib.parse.urlsplit(response.geturl()).scheme != "https":
                raise ValueError("A source redirect left HTTPS")
            written = 0
            while True:
                block = response.read(CHUNK)
                if not block:
                    break
                written += len(block)
                if written > expected_size:
                    raise ValueError(f"Downloaded source is larger than locked size: {filename}")
                output.write(block)
            output.flush()
            os.fsync(output.fileno())
        if temporary.stat().st_size != expected_size or sha256_file(temporary) != expected_sha:
            raise ValueError(f"Downloaded source failed size/SHA-256: {filename}")
        os.replace(temporary, target)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return target


def _download_source(lock: dict, name: str, cache_directory: Path) -> tuple[Path, Path | None]:
    source = lock["sources"][name]
    payload = _download_locked(source, cache_directory)
    signature = None
    if name.startswith("nullmoth_"):
        signature = _download_locked(source, cache_directory, signature=True)
        signature_text = signature.read_text(encoding="ascii").strip()
        if not verify_nullmoth_file(payload, signature_text):
            raise ValueError(f"NullMoth Ed25519 signature failed: {payload.name}")
    return payload, signature


def _regular_tree_manifest(root: Path) -> dict[str, str]:
    root = Path(root)
    files = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            continue
        if path.is_file():
            name = path.relative_to(root).as_posix()
            files[name] = sha256_file(path)
    return files


def _install_tar_filter(member: tarfile.TarInfo) -> tarfile.TarInfo:
    member.uid = 0
    member.gid = 0
    member.uname = "root"
    member.gname = "wheel"
    member.mtime = 0
    member.mode &= 0o777
    member.pax_headers = {}
    return member


def _build_install_payload(package_root: Path):
    """Freeze the verified tree in an anonymous FD before asking for consent."""
    root = Path(package_root).resolve()
    if not root.is_dir():
        raise ValueError("Prepared package root is not a directory")
    payload = tempfile.TemporaryFile(prefix="s540-nullmoth-install-", suffix=".tar")
    try:
        with tarfile.open(
            fileobj=payload,
            mode="w",
            format=tarfile.PAX_FORMAT,
            dereference=False,
        ) as archive:
            paths = sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix())
            for path in paths:
                relative = path.relative_to(root).as_posix()
                parts = _member_parts(relative)
                details = path.lstat()
                if stat.S_ISLNK(details.st_mode):
                    target = os.readlink(path)
                    link_parts = _member_parts(target)
                    if ".." in PurePosixPath(target).parts:
                        raise ValueError(f"Unsafe prepared-package link: {relative}")
                    resolved = path.parent.joinpath(*link_parts).resolve(strict=False)
                    if resolved != root and root not in resolved.parents:
                        raise ValueError(f"Prepared-package link escapes root: {relative}")
                elif stat.S_ISREG(details.st_mode):
                    if details.st_nlink != 1:
                        raise ValueError(f"Hard-linked prepared-package file: {relative}")
                elif not stat.S_ISDIR(details.st_mode):
                    raise ValueError(f"Special prepared-package node: {relative}")
                archive.add(
                    path,
                    arcname=PurePosixPath(*parts).as_posix(),
                    recursive=False,
                    filter=_install_tar_filter,
                )
        payload.flush()
        os.fsync(payload.fileno())
        payload.seek(0)
        digest = hashlib.sha256()
        for block in iter(lambda: payload.read(CHUNK), b""):
            digest.update(block)
        payload.seek(0)
        return payload, digest.hexdigest()
    except Exception:
        payload.close()
        raise


def _run_privileged_install(payload, digest: str) -> None:
    """Pass the exact anonymous payload to a root-private staging directory."""
    if not SHA256_RE.fullmatch(digest):
        raise ValueError("Invalid prepared-package digest")
    payload.seek(0)
    subprocess.run(
        [
            "/usr/bin/sudo", "/bin/bash", "-c", ROOT_INSTALL_SCRIPT,
            "s540-nullmoth-install", digest,
        ],
        stdin=payload,
        check=True,
    )


def _deterministic_zip(
    destination: Path,
    files: dict[str, bytes],
    *,
    prefix: str = "",
) -> Path:
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".part")
    with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for name, data in sorted(files.items()):
            archive_name = f"{prefix}/{name}" if prefix else name
            info = zipfile.ZipInfo(archive_name, (2026, 11, 8, 0, 0, 0))
            executable = (
                name.endswith((".command", ".py", ".efi")) or
                "/MacOS/" in name
            )
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | (0o755 if executable else 0o644)) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            bundle.writestr(info, data, compresslevel=9)
    os.replace(temporary, destination)
    sidecar = destination.with_name(destination.name + ".sha256")
    sidecar.write_text(f"{sha256_file(destination)}  {destination.name}\n", encoding="ascii")
    return destination


def _read_release_files(release_root: Path, lock: dict) -> dict[str, bytes]:
    release_root = Path(release_root)
    mappings = {
        "README.md": release_root / "README.md",
        "sources.lock.json": release_root / "sources.lock.json",
        "bin/s540_release.py": release_root / "s540_release.py",
        "bin/nullmoth_release_sig.py": release_root / "nullmoth_release_sig.py",
        "ASSEMBLA-EFI-NVIDIA.command": release_root / "ASSEMBLA-EFI-NVIDIA.command",
        "INSTALLA-NULLMOTH-S540.command": release_root / "INSTALLA-NULLMOTH-S540.command",
        "VERIFICA-INSTALLAZIONE.command": release_root / "VERIFICA-INSTALLAZIONE.command",
        "LICENSES/S540Sensors-MIT.txt": release_root / "LICENSES/S540Sensors-MIT.txt",
        "LICENSES/S540Sensors-THIRD-PARTY-NOTICES.txt": (
            release_root / "LICENSES/S540Sensors-THIRD-PARTY-NOTICES.txt"
        ),
        "LICENSES/MacKernelSDK-APSL-2.0.txt": (
            release_root / "LICENSES/MacKernelSDK-APSL-2.0.txt"
        ),
        "LICENSES/Lilu-BSD-3-Clause.txt": (
            release_root / "LICENSES/Lilu-BSD-3-Clause.txt"
        ),
        "LICENSES/VirtualSMC-BSD-3-Clause.txt": (
            release_root / "LICENSES/VirtualSMC-BSD-3-Clause.txt"
        ),
        "LICENSES/NullMoth-PolyForm-Noncommercial-1.0.0.txt": (
            release_root / "LICENSES/NullMoth-PolyForm-Noncommercial-1.0.0.txt"
        ),
        "profile/config.plist": release_root / lock["profile"]["config_path"],
        "profile/efi-manifest.json": release_root / lock["profile"]["efi_manifest_path"],
    }
    sensors = release_root / lock["profile"]["sensors_path"]
    for path in sensors.rglob("*"):
        if path.is_symlink():
            raise ValueError("S540Sensors profile contains a symlink")
        if path.is_file():
            mappings[(Path("profile/S540Sensors.kext") / path.relative_to(sensors)).as_posix()] = path
    result = {}
    for name, path in mappings.items():
        if not path.is_file():
            raise ValueError(f"Missing release-kit source: {path}")
        result[name] = path.read_bytes()
    return result


def _validate_sensors(release_root: Path, lock: dict) -> None:
    root = release_root / lock["profile"]["sensors_path"] / "Contents"
    expected = lock["profile"]["sensors"]
    paths = {
        "info_sha256": root / "Info.plist",
        "executable_sha256": root / "MacOS/S540Sensors",
        "code_resources_sha256": root / "_CodeSignature/CodeResources",
    }
    for field, path in paths.items():
        if sha256_file(path) != expected[field]:
            raise ValueError(f"S540Sensors binding failed: {field}")


def build_release(
    output_dir: Path,
    *,
    cache_dir: Path | None = None,
) -> Path:
    """Build the deterministic, source-only release kit and SHA sidecar."""
    del cache_dir  # Kept for a stable API; kit construction never downloads.
    release_root = DEFAULT_LOCK.parent
    lock = load_source_lock(DEFAULT_LOCK)
    validate_public_config(release_root / lock["profile"]["config_path"], lock)
    _validate_sensors(release_root, lock)
    efi_manifest_path = release_root / lock["profile"]["efi_manifest_path"]
    if sha256_file(efi_manifest_path) != lock["profile"]["efi_manifest_sha256"]:
        raise ValueError("EFI manifest SHA-256 differs from the reviewed profile")
    efi_manifest = json.loads(efi_manifest_path.read_text())
    if efi_manifest.get("schema") != 1 or efi_manifest.get("version") != lock["release"]["tag"]:
        raise ValueError("EFI manifest release binding failed")
    files = _read_release_files(release_root, lock)
    manifest = {
        "schema": 1,
        "version": lock["release"]["tag"],
        "files": {name: sha256_data(data) for name, data in sorted(files.items())},
    }
    files["MANIFEST.json"] = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    destination = Path(output_dir) / lock["release"]["package_name"]
    return _deterministic_zip(
        destination,
        files,
        prefix=lock["release"]["package_prefix"],
    )


def _copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def assemble_efi(kit_root: Path, output_directory: Path, cache_directory: Path) -> Path:
    kit_root = Path(kit_root)
    lock = load_source_lock(kit_root / "sources.lock.json")
    validate_public_config(kit_root / lock["profile"]["config_path"], lock)
    inputs = {}
    for name in ("stable_efi", "opencore", "amfipass", "nullmoth_1401"):
        inputs[name] = _download_source(lock, name, cache_directory)[0]
    with tempfile.TemporaryDirectory(prefix="s540-efi-assemble-") as temporary_name:
        temporary = Path(temporary_name)
        extracted = {}
        for name, archive in inputs.items():
            destination = temporary / name
            safe_extract_zip(archive, destination)
            extracted[name] = destination
        stage = temporary / "result"
        stable_root = extracted["stable_efi"] / lock["sources"]["stable_efi"]["efi_root"]
        shutil.copytree(stable_root, stage / "EFI")
        profile_config = kit_root / lock["profile"]["config_path"]
        _copy_file(profile_config, stage / "EFI/OC/config.plist")
        opencore = lock["sources"]["opencore"]
        for field, relative in (
            ("bootx64", "EFI/BOOT/BOOTx64.efi"),
            ("opencore_efi", "EFI/OC/OpenCore.efi"),
            ("openruntime_efi", "EFI/OC/Drivers/OpenRuntime.efi"),
        ):
            _copy_file(extracted["opencore"] / opencore[field], stage / relative)
        amfi_source = extracted["amfipass"] / lock["sources"]["amfipass"]["bundle_root"]
        amfi_target = stage / "EFI/OC/Kexts/AMFIPass.kext"
        shutil.copytree(amfi_source, amfi_target)
        sensors_source = kit_root / lock["profile"]["sensors_path"]
        sensors_target = stage / "EFI/OC/Kexts/S540Sensors.kext"
        shutil.copytree(sensors_source, sensors_target)
        safe_tool = extracted["nullmoth_1401"] / lock["sources"]["nullmoth_1401"]["safe_tool"]
        _copy_file(safe_tool, stage / "EFI/OC/Tools/NullMothSafe.efi")
        efi_manifest_path = kit_root / lock["profile"]["efi_manifest_path"]
        if sha256_file(efi_manifest_path) != lock["profile"]["efi_manifest_sha256"]:
            raise ValueError("EFI manifest SHA-256 differs from the reviewed profile")
        expected_manifest = json.loads(efi_manifest_path.read_text(encoding="utf-8"))
        actual_files = _regular_tree_manifest(stage)
        if actual_files != expected_manifest.get("files"):
            missing = sorted(set(expected_manifest.get("files", {})) - set(actual_files))
            extra = sorted(set(actual_files) - set(expected_manifest.get("files", {})))
            changed = sorted(
                name for name in set(actual_files) & set(expected_manifest.get("files", {}))
                if actual_files[name] != expected_manifest["files"][name]
            )
            raise ValueError(
                f"Assembled EFI differs from reviewed manifest; missing={missing}, "
                f"extra={extra}, changed={changed}"
            )
        validator = extracted["opencore"] / opencore["ocvalidate"]
        validator.chmod(validator.stat().st_mode | stat.S_IXUSR)
        validation = subprocess.run(
            [str(validator), str(stage / "EFI/OC/config.plist")],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        if validation.returncode:
            raise RuntimeError(f"OpenCore validation failed:\n{validation.stdout}")
        provenance = {
            "schema": 1,
            "release": lock["release"],
            "sources": {
                name: {
                    "filename": lock["sources"][name]["filename"],
                    "size": lock["sources"][name]["size"],
                    "sha256": lock["sources"][name]["sha256"],
                }
                for name in ("stable_efi", "opencore", "amfipass", "nullmoth_1401")
            },
            "efi_files": actual_files,
            "ocvalidate": {
                "version": lock["release"]["opencore_version"],
                "status": "passed",
            },
        }
        files = {name: path.read_bytes() for name, path in (
            (path.relative_to(stage).as_posix(), path)
            for path in stage.rglob("*") if path.is_file()
        )}
        files["ASSEMBLY-MANIFEST.json"] = (
            json.dumps(provenance, indent=2, sort_keys=True) + "\n"
        ).encode()
        name = f"S540-Tahoe-NVIDIA-EFI-{lock['release']['tag']}.zip"
        destination = _deterministic_zip(Path(output_directory) / name, files)
    print(f"EFI locale verificata: {destination}")
    print(f"SHA-256: {sha256_file(destination)}")
    print("La ESP non è stata modificata. Personalizza gli SMBIOS prima del boot.")
    return destination


def _verify_package_sums(package_root: Path) -> None:
    sums = package_root / "SHA256SUMS"
    expected = {}
    for line in sums.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if not match:
            raise ValueError("Malformed upstream SHA256SUMS")
        parts = _member_parts(match.group(2))
        name = PurePosixPath(*parts).as_posix()
        if name in expected:
            raise ValueError(f"Duplicate upstream SHA256SUMS entry: {name}")
        expected[name] = match.group(1)
    actual_paths = {
        path.relative_to(package_root).as_posix(): path
        for path in package_root.rglob("*")
        if path.is_file() and not path.is_symlink() and path != sums
    }
    if set(actual_paths) != set(expected):
        raise ValueError("Upstream SHA256SUMS does not cover the complete regular-file package")
    for name, path in actual_paths.items():
        if sha256_file(path) != expected[name]:
            raise ValueError(f"Upstream package SHA mismatch: {name}")


def _plist(path: Path) -> dict:
    with path.open("rb") as stream:
        return plistlib.load(stream)


def _run_plistbuddy(command: str, path: Path) -> None:
    tool = Path("/usr/libexec/PlistBuddy")
    if not tool.is_file():
        raise RuntimeError("PlistBuddy is required on macOS")
    subprocess.run([str(tool), "-c", command, str(path)], check=True)


def _codesign_bundle(path: Path) -> None:
    subprocess.run(["/usr/bin/codesign", "--force", "--sign", "-", str(path)], check=True)
    subprocess.run(["/usr/bin/codesign", "--verify", "--strict", str(path)], check=True)


def _patch_nullmoth(package_root: Path, lock: dict) -> None:
    patch = lock["profile"]["nullmoth_patch"]
    device = lock["device"]
    nmx = package_root / "Library/Extensions/NMXAudio.kext"
    nmx_info = nmx / "Contents/Info.plist"
    nmx_binary = nmx / "Contents/MacOS/NMXAudio"
    if sha256_file(nmx_info) != patch["nmxaudio_info_before_sha256"]:
        raise ValueError("Unexpected upstream NMXAudio Info.plist")
    if sha256_file(nmx_binary) != patch["nmxaudio_executable_sha256"]:
        raise ValueError("Unexpected upstream NMXAudio executable")
    personality = _plist(nmx_info)["IOKitPersonalities"]["HDAudio"]
    if "IOPCIPrimaryMatch" in personality:
        raise ValueError("Upstream NMXAudio already has an unexpected primary match")
    _run_plistbuddy(
        "Add :IOKitPersonalities:HDAudio:IOPCIPrimaryMatch string " +
        device["nmx_audio_primary_match"],
        nmx_info,
    )
    _run_plistbuddy(
        "Set :IOKitPersonalities:HDAudio:IOPCIClassMatch " +
        device["nmx_audio_class_match"],
        nmx_info,
    )
    if sha256_file(nmx_info) != patch["nmxaudio_info_after_sha256"]:
        raise ValueError("Patched NMXAudio does not match the reviewed exact profile")
    targets = (
        (
            "Library/Extensions/NVRM.kext", "NVRM", "nvrm",
            "nvrm_installed_executable_sha256",
        ),
        (
            "Library/Extensions/NVAccel.kext", "NVAccel", "nvaccel",
            "nvaccel_prepared_executable_sha256",
        ),
        (
            "Library/NullMoth/kexts/15/NVAccel.kext", "NVAccel", "nvaccel",
            "nvaccel15_installed_executable_sha256",
        ),
        (
            "Library/NullMoth/kexts/26/NVAccel.kext", "NVAccel", "nvaccel",
            "nvaccel26_installed_executable_sha256",
        ),
    )
    for relative, personality_name, family, installed_executable_field in targets:
        bundle = package_root / relative
        info = bundle / "Contents/Info.plist"
        executable = bundle / "Contents/MacOS" / personality_name
        if sha256_file(info) != patch[f"{family}_info_before_sha256"]:
            raise ValueError(f"Unexpected upstream {relative} Info.plist")
        executable_field = f"{family}_executable_sha256"
        if relative.startswith("Library/NullMoth/kexts/26/"):
            executable_field = "nvaccel26_executable_sha256"
        if sha256_file(executable) != patch[executable_field]:
            raise ValueError(f"Unexpected upstream {relative} executable")
        _run_plistbuddy(
            f"Set :IOKitPersonalities:{personality_name}:IOPCIPrimaryMatch " +
            device["nvidia_primary_match"],
            info,
        )
        if sha256_file(info) != patch[f"{family}_info_after_sha256"]:
            raise ValueError(f"Patched {relative} does not match the reviewed profile")
        _codesign_bundle(bundle)
        if sha256_file(executable) != patch[installed_executable_field]:
            raise ValueError(f"Signed {relative} executable differs from reviewed output")


def _write_package_sums(package_root: Path) -> None:
    paths = sorted(
        path for path in package_root.rglob("*")
        if path.is_file() and not path.is_symlink() and path.name != "SHA256SUMS"
    )
    content = "".join(
        f"{sha256_file(path)}  {path.relative_to(package_root).as_posix()}\n"
        for path in paths
    )
    (package_root / "SHA256SUMS").write_text(content, encoding="utf-8")


def validate_target_host(lock: dict) -> dict:
    """Refuse preparation/install away from the one qualified OS and GPU."""
    if sys.platform != "darwin":
        raise RuntimeError("NullMoth preparation is allowed only on the target macOS host")

    def capture(arguments: list[str]) -> str:
        result = subprocess.run(
            arguments,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        if result.returncode:
            raise RuntimeError(f"Host preflight command failed: {' '.join(arguments)}")
        return result.stdout.strip()

    architecture = capture(["/usr/bin/uname", "-m"])
    product_version = capture(["/usr/bin/sw_vers", "-productVersion"])
    build_version = capture(["/usr/bin/sw_vers", "-buildVersion"])
    if architecture != "x86_64":
        raise RuntimeError(f"Untested architecture: {architecture}; required x86_64")
    if product_version != lock["release"]["tested_macos_version"]:
        raise RuntimeError(
            f"Untested macOS version: {product_version}; required "
            f"{lock['release']['tested_macos_version']}"
        )
    if build_version != lock["release"]["tested_macos_build"]:
        raise RuntimeError(
            f"Untested macOS build: {build_version}; required "
            f"{lock['release']['tested_macos_build']}"
        )
    registry = capture(["/usr/sbin/ioreg", "-l", "-p", "IOService", "-w0"])
    compatible_line = re.compile(
        r'"compatible"\s*=\s*<[^>]*"' +
        re.escape(lock["device"]["nvidia_subsystem_compatible"]) +
        r'"[^>]*"' + re.escape(lock["device"]["nvidia_compatible"]) + r'"[^>]*>'
    )
    if compatible_line.search(registry) is None:
        raise RuntimeError(
            "Target GPU mismatch: required NVIDIA 10DE:1F91 with Lenovo "
            "subsystem 17AA:3806 on the same PCI function"
        )
    return {
        "architecture": architecture,
        "product_version": product_version,
        "build_version": build_version,
        "nvidia_compatible": lock["device"]["nvidia_compatible"],
        "nvidia_subsystem_compatible": lock["device"]["nvidia_subsystem_compatible"],
    }


def prepare_nullmoth(
    kit_root: Path,
    output_directory: Path,
    cache_directory: Path,
    *,
    install: bool = False,
) -> Path:
    kit_root = Path(kit_root)
    lock = load_source_lock(kit_root / "sources.lock.json")
    host = validate_target_host(lock)
    print(
        "Host qualificato: "
        f"{host['architecture']}, macOS {host['product_version']} "
        f"({host['build_version']}), {host['nvidia_compatible']} / "
        f"{host['nvidia_subsystem_compatible']}"
    )
    archive, _ = _download_source(lock, "nullmoth_driver", cache_directory)
    output_directory = Path(output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)
    final = output_directory / f"S540-NullMoth-{lock['release']['nullmoth_version']}-prepared"
    if final.exists():
        raise ValueError(f"Prepared package already exists; preserve or move it first: {final}")
    install_payload = None
    try:
        with tempfile.TemporaryDirectory(
            prefix="s540-nullmoth-", dir=output_directory
        ) as temporary_name:
            extracted = Path(temporary_name) / "extracted"
            safe_extract_tar(archive, extracted)
            package_root = extracted / lock["sources"]["nullmoth_driver"]["package_root"]
            if not package_root.is_dir():
                raise ValueError("Signed NullMoth archive has no locked package root")
            _verify_package_sums(package_root)
            _patch_nullmoth(package_root, lock)
            patch_record = {
                "schema": 1,
                "release": lock["release"]["tag"],
                "source_sha256": lock["sources"]["nullmoth_driver"]["sha256"],
                "nvidia_primary_match": lock["device"]["nvidia_primary_match"],
                "nmx_audio_primary_match": lock["device"]["nmx_audio_primary_match"],
                "nmx_audio_class_match": lock["device"]["nmx_audio_class_match"],
            }
            (package_root / "S540-PATCH.json").write_text(
                json.dumps(patch_record, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            _write_package_sums(package_root)
            install_digest = None
            if install:
                install_payload, install_digest = _build_install_payload(package_root)
            shutil.move(str(package_root), final)
        print(f"Pacchetto NullMoth verificato e preparato: {final}")
        if install:
            print("L'installer ufficiale modificherà /Library e ricostruirà la Auxiliary KC.")
            answer = input("Scrivi INSTALLA per continuare: ").strip()
            if answer != "INSTALLA":
                print("Installazione annullata; il pacchetto preparato è stato conservato.")
                return final
            assert install_payload is not None and install_digest is not None
            _run_privileged_install(install_payload, install_digest)
            print("Installer completato. Riavvia, poi esegui VERIFICA-INSTALLAZIONE.command.")
        return final
    finally:
        if install_payload is not None:
            install_payload.close()


def verify_installation(kit_root: Path) -> dict:
    lock = load_source_lock(Path(kit_root) / "sources.lock.json")
    patch = lock["profile"]["nullmoth_patch"]
    checks: list[dict] = []

    def record(name: str, passed: bool, detail: str) -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    try:
        host = validate_target_host(lock)
        record(
            "Qualified target host",
            True,
            f"{host['architecture']}, macOS {host['product_version']} "
            f"({host['build_version']}), {host['nvidia_compatible']} / "
            f"{host['nvidia_subsystem_compatible']}",
        )
    except (OSError, RuntimeError, ValueError) as error:
        record("Qualified target host", False, str(error))

    paths = {
        "NMXAudio": Path("/Library/Extensions/NMXAudio.kext"),
        "NVRM": Path("/Library/Extensions/NVRM.kext"),
        "NVAccel": Path("/Library/Extensions/NVAccel.kext"),
        "NVAccel15": Path("/Library/NullMoth/kexts/15/NVAccel.kext"),
        "NVAccel26": Path("/Library/NullMoth/kexts/26/NVAccel.kext"),
    }
    for name, path in paths.items():
        record(name + " present", path.is_dir(), str(path))
    if paths["NMXAudio"].is_dir():
        info = _plist(paths["NMXAudio"] / "Contents/Info.plist")
        personality = info["IOKitPersonalities"]["HDAudio"]
        record(
            "NMXAudio exact PCI match",
            personality.get("IOPCIPrimaryMatch") == lock["device"]["nmx_audio_primary_match"] and
            personality.get("IOPCIClassMatch") == lock["device"]["nmx_audio_class_match"],
            repr(personality),
        )
        info_path = paths["NMXAudio"] / "Contents/Info.plist"
        record(
            "NMXAudio exact Info.plist",
            sha256_file(info_path) == patch["nmxaudio_info_after_sha256"],
            str(info_path),
        )
        binary = paths["NMXAudio"] / "Contents/MacOS/NMXAudio"
        record(
            "NMXAudio executable",
            binary.is_file() and sha256_file(binary) == patch["nmxaudio_executable_sha256"],
            str(binary),
        )
    driver_expectations = {
        "NVRM": ("NVRM", "nvrm_info_after_sha256", "nvrm_installed_executable_sha256"),
        "NVAccel": ("NVAccel", "nvaccel_info_after_sha256", "nvaccel_installed_executable_sha256"),
        "NVAccel15": ("NVAccel", "nvaccel_info_after_sha256", "nvaccel15_installed_executable_sha256"),
        "NVAccel26": ("NVAccel", "nvaccel_info_after_sha256", "nvaccel26_installed_executable_sha256"),
    }
    for name, (personality_name, info_field, executable_field) in driver_expectations.items():
        path = paths[name]
        if not path.is_dir():
            continue
        info_path = path / "Contents/Info.plist"
        info = _plist(info_path)
        match = info["IOKitPersonalities"][personality_name].get("IOPCIPrimaryMatch")
        record(name + " exact GPU match", match == lock["device"]["nvidia_primary_match"], str(match))
        record(
            name + " exact Info.plist",
            sha256_file(info_path) == patch[info_field],
            str(info_path),
        )
        executable = path / "Contents/MacOS" / personality_name
        record(
            name + " exact installed executable",
            executable.is_file() and sha256_file(executable) == patch[executable_field],
            str(executable),
        )
    auxkc = Path("/Library/KernelCollections/AuxiliaryKernelExtensions.kc")
    if auxkc.is_file():
        inspect = subprocess.run(
            ["/usr/bin/kmutil", "inspect", "-a", "x86_64", "-A", str(auxkc)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        for identifier in (
            "com.nullmoth.NMXAudio", "com.nullmoth.NVRM", "com.nullmoth.NVAccel",
            "com.nullmoth.NVRMFB", "com.nullmoth.NVRMAGDC",
        ):
            record("AuxKC " + identifier, inspect.returncode == 0 and identifier in inspect.stdout, "kmutil inspect")
    else:
        record("AuxKC present", False, str(auxkc))
    ioreg = subprocess.run(
        ["/usr/sbin/ioreg", "-r", "-c", "NVAccel", "-l"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    record("NVAccel active in IORegistry", ioreg.returncode == 0 and "NVAccel" in ioreg.stdout, "ioreg -c NVAccel")
    result = {
        "schema": 1,
        "release": lock["release"]["tag"],
        "passed": all(item["passed"] for item in checks),
        "checks": checks,
    }
    for item in checks:
        print(("PASS" if item["passed"] else "FAIL") + f" — {item['name']}: {item['detail']}")
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kit-root", type=Path, default=KIT_ROOT)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build-kit", help="Build the deterministic public kit")
    build.add_argument("--output-directory", type=Path, required=True)
    assemble = subparsers.add_parser("assemble-efi", help="Download and assemble the local EFI")
    assemble.add_argument("--cache-directory", type=Path, required=True)
    assemble.add_argument("--output-directory", type=Path, required=True)
    prepare = subparsers.add_parser("prepare-nullmoth", help="Prepare exact S540 NullMoth payload")
    prepare.add_argument("--cache-directory", type=Path, required=True)
    prepare.add_argument("--output-directory", type=Path, required=True)
    prepare.add_argument("--install", action="store_true")
    verify = subparsers.add_parser("verify-install", help="Read-only post-restart verification")
    verify.add_argument("--json-output", type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.command == "build-kit":
        if args.kit_root.resolve() != DEFAULT_LOCK.parent.resolve():
            raise ValueError("build-kit must run from the repository release source")
        destination = build_release(args.output_directory)
        print(f"Kit: {destination}")
        print(f"SHA-256: {sha256_file(destination)}")
        return 0
    if args.command == "assemble-efi":
        assemble_efi(args.kit_root, args.output_directory, args.cache_directory)
        return 0
    if args.command == "prepare-nullmoth":
        prepare_nullmoth(
            args.kit_root,
            args.output_directory,
            args.cache_directory,
            install=args.install,
        )
        return 0
    if args.command == "verify-install":
        result = verify_installation(args.kit_root)
        if args.json_output:
            args.json_output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        return 0 if result["passed"] else 1
    return 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"ERRORE: {error}", file=sys.stderr)
        raise SystemExit(1)
