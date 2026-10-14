#!/usr/bin/env python3
"""Reconstruct the current public EFI from pinned assets and checked inputs."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import plistlib
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "S540-Tahoe-EFI-v0.1.0"
CONFIG = ROOT / "config/efi/current/config.plist"
PLAN = ROOT / "config/efi/current/manifest.json"
LOCK = ROOT / "config/profiles/assets.lock.json"


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def error(message: str) -> None:
    raise ValueError(message)


def safe_relative(value: str) -> str:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts or "\\" in value:
        error("Invalid relative path.")
    if any(char in value for char in ("\n", "\r", "\0")) or str(path) != value:
        error("Non-canonical relative path.")
    return value


def ordinary_file(path: Path) -> None:
    if not path.is_file() or path.is_symlink():
        error(f"Missing regular file: {path.name}")


def ordinary_path(path: Path) -> Path:
    # resolve only after rejecting symlinks, rather than concealing them.
    absolute = Path(os.path.abspath(path))
    for part in (absolute, *absolute.parents):
        if part.is_symlink():
            error("The path contains a symbolic link.")
    return absolute


def checked_zip_members(archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    result = []
    names = set()
    for member in archive.infolist():
        # Directory trailing slashes are valid ZIP entries.
        name = member.filename[:-1] if member.is_dir() else member.filename
        safe_relative(name)
        if member.filename in names:
            error("The archive contains duplicate paths.")
        names.add(member.filename)
        mode = member.external_attr >> 16
        kind = stat.S_IFMT(mode)
        if stat.S_ISLNK(mode) or (kind not in (0, stat.S_IFREG, stat.S_IFDIR)):
            error("The archive contains links or special files.")
        if member.is_dir():
            continue
        if kind == stat.S_IFDIR or member.file_size > 64 * 1024 * 1024:
            error("An archive member is not a valid regular file.")
        if "__MACOSX" in PurePosixPath(name).parts or PurePosixPath(name).name == ".DS_Store":
            continue
        result.append(member)
    return result


def download(asset: dict, cache: Path) -> Path:
    filename = safe_relative(asset["filename"])
    if "/" in filename:
        error("The asset filename must identify a single file.")
    wanted = asset["sha256"]
    if len(wanted) != 64 or any(char not in "0123456789abcdef" for char in wanted):
        error("The asset has no pinned SHA256.")
    size = asset["size"]
    if not isinstance(size, int) or not 0 < size <= 128 * 1024 * 1024:
        error("Invalid asset size.")
    url = asset["url"]
    if not (url.startswith("https://github.com/") or url.startswith("https://raw.githubusercontent.com/")):
        error("The asset does not use a GitHub HTTPS URL.")
    destination = cache / filename
    if destination.exists() or destination.is_symlink():
        ordinary_file(destination)
    else:
        with tempfile.TemporaryDirectory(prefix="download-", dir=cache) as temporary:
            partial = Path(temporary) / filename
            subprocess.run(
                ["curl", "--fail", "--location", "--silent", "--show-error",
                 "--proto", "=https", "--proto-redir", "=https", "--max-redirs", "5",
                 "--connect-timeout", "15", "--max-time", "90", "--max-filesize",
                 str(size), "--output", str(partial), url],
                check=True, capture_output=True, text=True, timeout=95,
            )
            if partial.stat().st_size != size or sha256(partial.read_bytes()) != wanted:
                error(f"The downloaded asset does not match its lock: {asset['id']}")
            shutil.move(partial, destination)
    if destination.stat().st_size != size or sha256(destination.read_bytes()) != wanted:
        error(f"The cached asset does not match its lock: {asset['id']}")
    return destination


def check_public_config(raw: bytes) -> dict:
    config = plistlib.loads(raw)
    if not isinstance(config, dict):
        error("The public configuration is not a dictionary.")
    placeholders = {"", "CHANGEME", "CHANGE_ME", "YOUR_SERIAL_NUMBER", "YOUR_MLB",
                    "YOUR_SYSTEM_UUID", "REPLACE_ME", "00000000-0000-0000-0000-000000000000"}
    identity_keys = {"SystemSerialNumber", "MLB", "SystemUUID", "ROM", "BoardSerialNumber",
                     "ChassisSerialNumber", "System-id"}
    def visit(value: object) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key in identity_keys:
                    if isinstance(child, bytes):
                        valid = not any(child)
                    elif isinstance(child, str):
                        valid = child in placeholders or (child != "" and set(child) <= {"0", "-"})
                    else:
                        valid = child in (None, 0)
                    if not valid:
                        error("The configuration contains a personal identity instead of placeholders.")
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
    visit(config.get("PlatformInfo", {}))
    if any(not entry.get("Enabled") for entry in config["ACPI"]["Add"] + config["Kernel"]["Add"]):
        error("The minimal release configuration still contains disabled entries.")
    return config


def normalize_wifi(raw: bytes) -> bytes:
    info = plistlib.loads(raw)
    info["IOKitPersonalities"]["itlwm"]["WiFiConfig"] = {}
    return plistlib.dumps(info, fmt=plistlib.FMT_XML, sort_keys=False)


def suffix_for(desired: str) -> str:
    if desired.startswith("EFI/OC/Kexts/"):
        return desired.removeprefix("EFI/OC/Kexts/")
    return desired


def find_asset_bytes(assets: dict[str, Path], desired: str, wanted: str) -> tuple[bytes, str]:
    suffix = suffix_for(desired)
    for asset_id, path in assets.items():
        if path.suffix.lower() != ".zip":
            if path.name == PurePosixPath(desired).name:
                raw = path.read_bytes()
                if sha256(raw) == wanted:
                    return raw, asset_id
            continue
        with zipfile.ZipFile(path) as archive:
            for member in checked_zip_members(archive):
                if not (member.filename == suffix or member.filename.endswith("/" + suffix)):
                    continue
                raw = archive.read(member)
                if desired.endswith("itlwm.kext/Contents/Info.plist"):
                    raw = normalize_wifi(raw)
                if sha256(raw) == wanted:
                    return raw, asset_id
    error(f"No pinned asset reconstructs the expected file: {desired}")
    raise AssertionError("unreachable")


def reference_bytes(reference: Path, desired: str) -> bytes:
    if reference.is_dir():
        candidates = [reference / desired]
        if reference.name == "EFI":
            candidates.append(reference / desired.removeprefix("EFI/"))
        for path in candidates:
            if path.is_file() and not path.is_symlink():
                ordinary_path(path)
                return path.read_bytes()
        error(f"The local reference lacks an expected file: {desired}")
    ordinary_file(reference)
    with zipfile.ZipFile(reference) as archive:
        members = checked_zip_members(archive)
        direct = [member for member in members if member.filename == desired or member.filename.endswith("/" + desired)]
        if len(direct) == 1:
            return archive.read(direct[0])
        nested = [member for member in members if member.filename.endswith(".zip")]
        if not direct and len(nested) == 1:
            with zipfile.ZipFile(io.BytesIO(archive.read(nested[0]))) as inner:
                hits = [member for member in checked_zip_members(inner) if member.filename == desired]
                if len(hits) == 1:
                    return inner.read(hits[0])
    error(f"The local reference does not identify exactly one file: {desired}")
    raise AssertionError("unreachable")


def validator_from(assets: dict[str, Path], temporary: Path) -> Path:
    if sys.platform == "linux":
        name = "ocvalidate.linux"
    elif sys.platform == "darwin":
        name = "ocvalidate"
    else:
        error("Native release validation requires Linux or macOS.")
    archive_path = assets.get("OpenCore")
    if archive_path is None:
        error("The pinned OpenCore asset is required for ocvalidate.")
    with zipfile.ZipFile(archive_path) as archive:
        hits = [member for member in checked_zip_members(archive)
                if PurePosixPath(member.filename).name == name]
        if len(hits) != 1:
            error("The OpenCore release does not contain exactly one native ocvalidate.")
        validator = temporary / name
        validator.write_bytes(archive.read(hits[0]))
        validator.chmod(0o755)
        return validator


def build(arguments: argparse.Namespace) -> Path:
    in_ci = os.environ.get("CI", "").lower() in ("true", "1")
    if in_ci and (arguments.skip_ocvalidate or arguments.reference_efi or arguments.ocvalidate):
        error("CI requires pinned upstream assets and ocvalidate extracted from the OpenCore release.")
    output = ordinary_path(arguments.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    ordinary_file(PLAN)
    ordinary_file(CONFIG)
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    wanted_files = plan["files"]
    if not isinstance(wanted_files, dict) or not wanted_files:
        error("The manifest does not contain a file list.")
    if len({path.casefold() for path in wanted_files}) != len(wanted_files):
        error("The manifest contains paths that collide on a FAT filesystem.")
    for path, wanted in wanted_files.items():
        safe_relative(path)
        if not path.startswith("EFI/") or "/backup-" in path or "/config.before" in path:
            error("The manifest includes files outside the minimal EFI.")
        if not isinstance(wanted, str) or len(wanted) != 64 or any(c not in "0123456789abcdef" for c in wanted):
            error("The manifest contains an invalid hash.")
    config_raw = CONFIG.read_bytes()
    config = check_public_config(config_raw)
    if wanted_files.get("EFI/OC/config.plist") != sha256(config_raw):
        error("The public configuration does not match the manifest.")
    for entry in config["ACPI"]["Add"]:
        if "EFI/OC/ACPI/" + entry["Path"] not in wanted_files:
            error("An enabled ACPI table is missing from the manifest.")
    for entry in config["Kernel"]["Add"]:
        prefix = "EFI/OC/Kexts/" + entry["BundlePath"] + "/"
        for relative in (entry["PlistPath"], entry["ExecutablePath"]):
            if relative and prefix + relative not in wanted_files:
                error("A file required by an enabled kext is missing from the manifest.")
    for entry in config["UEFI"]["Drivers"]:
        if entry["Enabled"] and "EFI/OC/Drivers/" + entry["Path"] not in wanted_files:
            error("An enabled UEFI driver is missing from the manifest.")
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    ids = plan.get("assetlock_ids", [asset["id"] for asset in lock["assets"]])
    known = {asset["id"]: asset for asset in lock["assets"]}
    if len(known) != len(lock["assets"]) or len(ids) != len(set(ids)) or any(asset_id not in known for asset_id in ids):
        error("Invalid asset list.")
    tracked = plan.get("trackedpathsmap", {})
    assets: dict[str, Path] = {}
    reference = ordinary_path(arguments.reference_efi) if arguments.reference_efi else None
    if reference is None or not arguments.skip_ocvalidate and not arguments.ocvalidate:
        cache = ordinary_path(arguments.asset_cache or output / "asset-cache")
        cache.mkdir(parents=True, exist_ok=True)
        for asset_id in ids:
            assets[asset_id] = download(known[asset_id], cache)
    package = output / PACKAGE
    zipped = output / f"{PACKAGE}.zip"
    sidecar = output / f"{PACKAGE}.zip.sha256"
    if any(path.exists() or path.is_symlink() for path in (package, zipped, sidecar)):
        error("The release destination already exists.")
    with tempfile.TemporaryDirectory(prefix="efi-release-", dir=output) as temporary_name:
        temporary = Path(temporary_name)
        stage = temporary / PACKAGE
        stage.mkdir()
        origins = {}
        for desired, wanted in sorted(wanted_files.items()):
            if desired == "EFI/OC/config.plist":
                raw, origin = config_raw, "tracked public configuration"
            elif desired in tracked:
                source = ROOT / safe_relative(tracked[desired])
                ordinary_path(source)
                ordinary_file(source)
                raw, origin = source.read_bytes(), tracked[desired]
            elif desired.startswith("EFI/OC/ACPI/"):
                source = ROOT / "config/acpi/compiled" / PurePosixPath(desired).name
                ordinary_path(source)
                ordinary_file(source)
                raw, origin = source.read_bytes(), "tracked ACPI table"
            elif desired.startswith("EFI/OC/Kexts/UTBMap.kext/"):
                source = ROOT / "config/usb" / desired.removeprefix("EFI/OC/Kexts/")
                ordinary_path(source)
                ordinary_file(source)
                raw, origin = source.read_bytes(), "tracked USB map"
            elif reference is not None:
                raw, origin = reference_bytes(reference, desired), "offline component reference"
                if desired.endswith("itlwm.kext/Contents/Info.plist"):
                    raw = normalize_wifi(raw)
            else:
                raw, origin = find_asset_bytes(assets, desired, wanted)
            if sha256(raw) != wanted:
                error(f"The reconstructed file does not match the manifest: {desired}")
            target = stage / desired
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
            executable = desired.endswith(".efi") or "/Contents/MacOS/" in desired
            target.chmod(0o755 if executable else 0o644)
            origins[desired] = origin
        actual = {path.relative_to(stage).as_posix(): sha256(path.read_bytes())
                  for path in (stage / "EFI").rglob("*") if path.is_file()}
        if actual != wanted_files:
            error("The generated EFI does not match the manifest exactly.")
        validation = "offline hash comparison; ocvalidate intentionally skipped"
        if not arguments.skip_ocvalidate:
            validator = ordinary_path(arguments.ocvalidate) if arguments.ocvalidate else validator_from(assets, temporary)
            ordinary_file(validator)
            result = subprocess.run([str(validator), str(stage / "EFI/OC/config.plist")],
                                    check=True, capture_output=True, text=True, timeout=60)
            validation = result.stdout.strip() or "ocvalidate passed"
            (stage / "ocvalidate.txt").write_text(validation + "\n", encoding="utf-8")
        for source, name in ((ROOT / "packages/efi/README.md", "README.md"),
                             (ROOT / "packages/efi/COMPATIBILITY.md", "COMPATIBILITY.md")):
            ordinary_path(source)
            ordinary_file(source)
            shutil.copyfile(source, stage / name)
        license_root = ordinary_path(ROOT / "licenses/efi")
        if not license_root.is_dir():
            error("The EFI component license directory is missing.")
        license_files = []
        for source in sorted(license_root.rglob("*")):
            ordinary_path(source)
            if source.is_dir():
                continue
            ordinary_file(source)
            relative = safe_relative(source.relative_to(license_root).as_posix())
            if source.name == ".DS_Store" or source.name.startswith("."):
                error("The component license directory contains unexpected metadata.")
            target = stage / "LICENSES" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            target.chmod(0o644)
            license_files.append(relative)
        if not license_files:
            error("No EFI component license files were supplied.")
        release_manifest = {"schema": 1, "package": PACKAGE,
                            "commit": os.environ.get("GITHUB_SHA"),
                            "component_hashes": actual, "component_sources": origins,
                            "config_manifest_sha256": sha256(PLAN.read_bytes()),
                            "asset_lock_sha256": sha256(LOCK.read_bytes()),
                            "assets": [known[asset_id] for asset_id in ids],
                            "license_files": license_files,
                            "validation": validation,
                            "privacy": "No Wi-Fi configuration or personal SMBIOS identity; local personalization required."}
        (stage / "manifest.json").write_text(json.dumps(release_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (stage / "SHA256SUMS").write_text("".join(f"{wanted}  {desired}\n" for desired, wanted in sorted(actual.items())), encoding="ascii")
        staged_zip = temporary / zipped.name
        with zipfile.ZipFile(staged_zip, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for path in sorted(stage.rglob("*")):
                if not path.is_file():
                    continue
                if path.is_symlink():
                    error("The package contains a symbolic link.")
                name = path.relative_to(stage).as_posix()
                member = zipfile.ZipInfo(name, date_time=(2026, 10, 14, 0, 0, 0))
                member.create_system = 3
                member.external_attr = (stat.S_IFREG | stat.S_IMODE(path.stat().st_mode)) << 16
                member.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(member, path.read_bytes())
        digest = sha256(staged_zip.read_bytes())
        shutil.move(stage, package)
        shutil.move(staged_zip, zipped)
        sidecar.write_text(f"{digest}  {zipped.name}\n", encoding="ascii")
    return zipped


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--asset-cache", type=Path)
    parser.add_argument("--reference-efi", type=Path, help="Local offline reference directory or ZIP; identities are never copied")
    parser.add_argument("--ocvalidate", type=Path, help="Existing native ocvalidate 1.0.8 executable")
    parser.add_argument("--skip-ocvalidate", action="store_true", help="Offline hash comparison only; forbidden in CI")
    arguments = parser.parse_args()
    try:
        archive = build(arguments)
        print(f"Reconstructed release: {archive.name}")
        print(f"SHA256: {sha256(archive.read_bytes())}")
        return 0
    except (ValueError, OSError, KeyError, TypeError, plistlib.InvalidFileException,
            json.JSONDecodeError, zipfile.BadZipFile, subprocess.SubprocessError) as exception:
        print(f"Release not created: {exception}", file=sys.stderr)
        if isinstance(exception, subprocess.CalledProcessError) and exception.stderr:
            print(exception.stderr[-4000:], file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
