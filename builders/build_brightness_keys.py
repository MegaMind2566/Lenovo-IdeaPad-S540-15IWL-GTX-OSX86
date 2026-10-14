#!/usr/bin/env python3
"""Audit official BrightnessKeys assets and build a pinned reversible test package."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import plistlib
import re
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
from urllib.parse import quote, urlsplit
import zipfile


ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "config/profiles/brightness-keys-assets.lock.json"
CONFIG = ROOT / "config/efi/current/config.plist"
PLAN = ROOT / "config/efi/current/manifest.json"
PACKAGE = "S540-brightness-keys-v2"
IDENTIFIER = "as.acidanthera.BrightnessKeys"
VERSION = "1.0.3"
SOURCE_REPOSITORY = "MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86"
EXPECTED = {
    "BrightnessKeys": {
        "id": "BrightnessKeys", "repository": "acidanthera/BrightnessKeys",
        "version": VERSION, "filename": "BrightnessKeys-1.0.3-RELEASE.zip",
        "url": "https://github.com/acidanthera/BrightnessKeys/releases/download/1.0.3/BrightnessKeys-1.0.3-RELEASE.zip",
        "size": 66112,
    },
    "OpenCore": {
        "id": "OpenCore", "repository": "acidanthera/OpenCorePkg",
        "version": "1.0.8", "filename": "OpenCore-1.0.8-DEBUG.zip",
        "url": "https://github.com/acidanthera/OpenCorePkg/releases/download/1.0.8/OpenCore-1.0.8-DEBUG.zip",
        "size": 11931199,
    },
}
OPENCORE_SHA = "3f5f42b85703cf2c08e8dcd9245a52fb4326c9f4ef335c75b49f516cbbe131c6"


def fail(message: str) -> None:
    raise ValueError(message)


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def valid_sha(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def plain_path(path: Path) -> Path:
    absolute = Path(os.path.abspath(path))
    for part in (absolute, *absolute.parents):
        if part.is_symlink():
            fail("The path contains a symbolic link.")
    return absolute


def regular_file(path: Path) -> None:
    plain_path(path)
    if not path.is_file():
        fail(f"A required regular file is missing: {path.name}")


def safe_relative(value: str) -> str:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts or "\\" in value or ":" in value or not path.parts:
        fail("The archive contains an unsafe path.")
    if str(path) != value or any(char in value for char in ("\0", "\n", "\r")):
        fail("The archive contains a non-canonical path.")
    return value


def checked_members(archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    files = []
    seen = set()
    expanded_size = 0
    for member in archive.infolist():
        name = member.filename[:-1] if member.is_dir() else member.filename
        safe_relative(name)
        if name in seen:
            fail("The archive contains duplicate paths.")
        seen.add(name)
        kind = stat.S_IFMT(member.external_attr >> 16)
        if kind not in (0, stat.S_IFREG, stat.S_IFDIR) or member.flag_bits & 1:
            fail("The archive contains links, special files or encrypted entries.")
        if member.is_dir():
            if kind not in (0, stat.S_IFDIR):
                fail("An archive directory has an inconsistent file type.")
            continue
        if kind == stat.S_IFDIR or member.file_size > 64 * 1024 * 1024:
            fail("An archive file has an invalid type or size.")
        expanded_size += member.file_size
        if expanded_size > 256 * 1024 * 1024:
            fail("The archive exceeds the allowed expanded size.")
        files.append(member)
    if archive.testzip() is not None:
        fail("The archive failed CRC verification.")
    return files


def load_lock(audit_only: bool) -> dict[str, dict]:
    regular_file(LOCK)
    data = json.loads(LOCK.read_text(encoding="utf-8"))
    if set(data) != {"schema", "assets"} or data["schema"] != 1 or not isinstance(data["assets"], list):
        fail("The brightness asset lock has an invalid schema.")
    assets = {}
    for asset in data["assets"]:
        if not isinstance(asset, dict) or asset.get("id") not in EXPECTED or asset["id"] in assets:
            fail("The brightness asset lock contains unknown or duplicate assets.")
        expected = EXPECTED[asset["id"]]
        if set(asset) != set(expected) | {"sha256"} or any(asset[key] != value for key, value in expected.items()):
            fail("The asset lock does not identify the expected official release.")
        missing_brightness_hash = audit_only and asset["id"] == "BrightnessKeys" and asset["sha256"] is None
        if not missing_brightness_hash and not valid_sha(asset["sha256"]):
            fail("Full packaging requires a pinned SHA256 for every asset.")
        if asset["id"] == "OpenCore" and asset["sha256"] != OPENCORE_SHA:
            fail("OpenCore does not match the verified 1.0.8 archive.")
        assets[asset["id"]] = asset
    if set(assets) != set(EXPECTED):
        fail("The lock must contain both BrightnessKeys and OpenCore.")
    return assets


def download(asset: dict, directory: Path, audit_only: bool) -> Path:
    destination = directory / asset["filename"]
    if destination.exists() or destination.is_symlink():
        regular_file(destination)
    else:
        with tempfile.TemporaryDirectory(prefix="download-", dir=directory) as temporary:
            partial = Path(temporary) / asset["filename"]
            # Both attempts share the retry deadline; the process timeout also
            # bounds all redirects, retries and connection setup together.
            subprocess.run(
                ["/usr/bin/curl", "--fail", "--location", "--silent", "--show-error",
                 "--proto", "=https", "--proto-redir", "=https", "--max-redirs", "5",
                 "--connect-timeout", "15", "--max-time", "60", "--retry", "1",
                 "--retry-delay", "1", "--retry-max-time", "65", "--max-filesize",
                 str(asset["size"]), "--output", str(partial), asset["url"]],
                check=True, capture_output=True, text=True, timeout=130,
            )
            verify_download(partial, asset, audit_only)
            shutil.move(partial, destination)
    verify_download(destination, asset, audit_only)
    return destination


def verify_download(path: Path, asset: dict, audit_only: bool) -> None:
    regular_file(path)
    if path.stat().st_size != asset["size"]:
        fail(f"The official archive size does not match its lock: {asset['id']}")
    actual = sha256(path.read_bytes())
    if asset["sha256"] is None:
        if not audit_only or asset["id"] != "BrightnessKeys":
            fail("An unpinned asset cannot be packaged.")
    elif actual != asset["sha256"]:
        fail(f"The archive SHA256 does not match its lock: {asset['id']}")
    with zipfile.ZipFile(path) as archive:
        checked_members(archive)


def thin_header(raw: bytes, offset: int, size: int) -> dict:
    magic = raw[offset:offset + 4]
    formats = {b"\xcf\xfa\xed\xfe": ("<", 32), b"\xce\xfa\xed\xfe": ("<", 28),
               b"\xfe\xed\xfa\xcf": (">", 32), b"\xfe\xed\xfa\xce": (">", 28)}
    if magic not in formats:
        fail("An executable slice has no recognized Mach-O header.")
    endian, header_size = formats[magic]
    if size < header_size or offset < 0 or offset + size > len(raw):
        fail("A Mach-O slice is truncated or out of bounds.")
    _, cpu, subtype, file_type = struct.unpack_from(endian + "4I", raw, offset)
    return {"cpu_type": cpu, "cpu_subtype": subtype, "file_type": file_type,
            "offset": offset, "size": size, "header_size": header_size}


def macho_metadata(raw: bytes, file_type: int) -> dict:
    if len(raw) < 8:
        fail("The executable has a truncated Mach-O header.")
    fat_formats = {b"\xca\xfe\xba\xbe": (">", False), b"\xbe\xba\xfe\xca": ("<", False),
                   b"\xca\xfe\xba\xbf": (">", True), b"\xbf\xba\xfe\xca": ("<", True)}
    if raw[:4] in fat_formats:
        endian, wide = fat_formats[raw[:4]]
        count = struct.unpack_from(endian + "I", raw, 4)[0]
        width = 32 if wide else 20
        if not 1 <= count <= 16 or len(raw) < 8 + count * width:
            fail("The universal Mach-O architecture table is invalid.")
        slices = []
        ranges = []
        for index in range(count):
            entry = struct.unpack_from(endian + ("IIQQII" if wide else "5I"), raw, 8 + index * width)
            cpu, subtype, offset, size = entry[:4]
            if offset < 8 + count * width or size == 0:
                fail("A universal Mach-O slice overlaps its architecture table.")
            header = thin_header(raw, offset, size)
            if (header["cpu_type"], header["cpu_subtype"]) != (cpu, subtype):
                fail("A Mach-O slice disagrees with its architecture descriptor.")
            if any(offset < end and start < offset + size for start, end in ranges):
                fail("Universal Mach-O slices overlap.")
            ranges.append((offset, offset + size))
            slices.append(header)
        kind = "universal"
    else:
        slices, kind = [thin_header(raw, 0, len(raw))], "thin"
    if any(item["file_type"] != file_type for item in slices):
        fail("The executable has an unexpected Mach-O file type.")
    if not any(item["cpu_type"] == 0x01000007 for item in slices):
        fail("The executable does not support Intel x86_64.")
    return {"format": kind, "slices": slices, "supports_x86_64": True}


def brightness_bundle(path: Path) -> tuple[dict[str, bytes], dict]:
    with zipfile.ZipFile(path) as archive:
        candidates = [item for item in checked_members(archive)
                      if "BrightnessKeys.kext" in PurePosixPath(item.filename).parts]
        if not candidates:
            fail("The official archive has no BrightnessKeys bundle.")
        files = {}
        prefixes = set()
        for item in candidates:
            parts = PurePosixPath(item.filename).parts
            start = parts.index("BrightnessKeys.kext")
            prefixes.add(parts[:start])
            relative = "/".join(parts[start:])
            if relative in files or not relative.startswith("BrightnessKeys.kext/Contents/"):
                fail("The brightness bundle contains duplicate or unexpected paths.")
            files[relative] = archive.read(item)
        if len(prefixes) != 1:
            fail("The release contains multiple BrightnessKeys bundles.")
    info_path = "BrightnessKeys.kext/Contents/Info.plist"
    binary_path = "BrightnessKeys.kext/Contents/MacOS/BrightnessKeys"
    if info_path not in files or binary_path not in files:
        fail("The brightness bundle lacks its plist or executable.")
    info = plistlib.loads(files[info_path])
    if info.get("CFBundleIdentifier") != IDENTIFIER or info.get("CFBundleVersion") != VERSION:
        fail("The bundle identity or version does not match BrightnessKeys 1.0.3.")
    if info.get("CFBundleExecutable") != "BrightnessKeys":
        fail("The brightness bundle names an unexpected executable.")
    if info.get("CFBundlePackageType") != "KEXT":
        fail("The brightness bundle is not a kernel extension.")
    metadata = {"identifier": IDENTIFIER, "version": VERSION,
                "macho": macho_metadata(files[binary_path], 11),
                "libraries": info.get("OSBundleLibraries", {}),
                "files": [{"path": name, "sha256": sha256(raw), "size": len(raw)}
                          for name, raw in sorted(files.items())]}
    return files, metadata


def opencore_components(path: Path) -> tuple[bytes, bytes]:
    with zipfile.ZipFile(path) as archive:
        members = checked_members(archive)
        validators = [item for item in members if PurePosixPath(item.filename).name == "ocvalidate"]
        bootloaders = [item for item in members if item.filename == "X64/EFI/OC/OpenCore.efi"
                       or item.filename.endswith("/X64/EFI/OC/OpenCore.efi")]
        if len(validators) != 1 or len(bootloaders) != 1:
            fail("OpenCore must contain exactly one native macOS validator and x64 bootloader.")
        validator = archive.read(validators[0])
        macho_metadata(validator, 2)
        return validator, archive.read(bootloaders[0])


def configs(opencore: bytes) -> tuple[bytes, bytes, str]:
    regular_file(CONFIG)
    regular_file(PLAN)
    raw = CONFIG.read_bytes()
    wanted = json.loads(PLAN.read_text(encoding="utf-8"))["files"]
    if wanted.get("EFI/OC/config.plist") != sha256(raw):
        fail("The public configuration does not match its current EFI manifest.")
    oc_hash = wanted.get("EFI/OC/OpenCore.efi")
    if not valid_sha(oc_hash) or sha256(opencore) != oc_hash:
        fail("The pinned OpenCore bootloader does not match the current EFI.")
    original = plistlib.loads(raw)
    generic = original.get("PlatformInfo", {}).get("Generic", {})
    placeholders = {"", "CHANGEME", "CHANGE_ME", "REPLACE_ME", "YOUR_SERIAL_NUMBER",
                    "YOUR_MLB", "YOUR_SYSTEM_UUID", "00000000-0000-0000-0000-000000000000"}
    for key in ("MLB", "SystemSerialNumber", "SystemUUID"):
        if generic.get(key, "") not in placeholders:
            fail("Only the tracked public configuration with identity placeholders may be audited.")
    if not isinstance(generic.get("ROM", b""), bytes) or any(generic.get("ROM", b"")):
        fail("The public configuration contains a personal ROM identity.")
    entries = original["Kernel"]["Add"]
    if any(entry.get("BundlePath") == "BrightnessKeys.kext" for entry in entries):
        fail("The reference configuration already contains BrightnessKeys.")
    if not any(entry.get("Enabled") and entry.get("BundlePath") == "Lilu.kext" for entry in entries):
        fail("The reference configuration must enable Lilu before the brightness test.")
    candidate = copy.deepcopy(original)
    candidate["Kernel"]["Add"].append({
        "Arch": "Any", "BundlePath": "BrightnessKeys.kext", "Comment": "S540 brightness-key test",
        "Enabled": True, "ExecutablePath": "Contents/MacOS/BrightnessKeys",
        "MaxKernel": "25.99.99", "MinKernel": "25.0.0", "PlistPath": "Contents/Info.plist",
    })
    reverted = copy.deepcopy(candidate)
    reverted["Kernel"]["Add"].pop()
    if reverted != original:
        fail("The candidate changes configuration outside the appended Kernel.Add entry.")
    return raw, plistlib.dumps(candidate, fmt=plistlib.FMT_XML, sort_keys=False), oc_hash


def validate_configs(validator: bytes, original: bytes, candidate: bytes, temporary: Path) -> dict:
    executable = temporary / "ocvalidate"
    executable.write_bytes(validator)
    executable.chmod(0o755)
    reports = {}
    for name, raw in (("original", original), ("candidate", candidate)):
        configuration = temporary / f"{name}.plist"
        configuration.write_bytes(raw)
        result = subprocess.run([str(executable), str(configuration)], capture_output=True,
                                text=True, timeout=30)
        reports[name] = {"exit_code": result.returncode, "stdout": result.stdout,
                         "stderr": result.stderr, "config_sha256": sha256(raw)}
        if result.returncode:
            fail(f"ocvalidate rejected the {name} configuration: {result.stdout.strip()} {result.stderr.strip()}")
    return reports


def acquire(arguments: argparse.Namespace) -> tuple[dict, dict[str, bytes], bytes, bytes, str, dict]:
    if sys.platform != "darwin" or os.uname().machine != "x86_64":
        fail("Asset auditing and packaging require native Intel macOS.")
    assets = load_lock(arguments.audit_only)
    output = plain_path(arguments.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    cache = output / ("audit" if arguments.audit_only else "asset-cache")
    plain_path(cache).mkdir(parents=True, exist_ok=True)
    paths = {name: download(asset, cache, arguments.audit_only) for name, asset in assets.items()}
    bundle, metadata = brightness_bundle(paths["BrightnessKeys"])
    validator, opencore = opencore_components(paths["OpenCore"])
    original, candidate, oc_hash = configs(opencore)
    with tempfile.TemporaryDirectory(prefix="brightness-validate-", dir=output) as temporary:
        validation = validate_configs(validator, original, candidate, Path(temporary))
    audit = {"schema": 1, "audit_only": arguments.audit_only,
             "source_commit": os.environ.get("GITHUB_SHA"),
             "assets": [{**asset, "sha256": sha256(paths[name].read_bytes()),
                         "lock_hash_pinned": valid_sha(asset["sha256"])}
                        for name, asset in assets.items()],
             "brightness_keys": metadata, "validator_sha256": sha256(validator),
             "validator_macho": macho_metadata(validator, 2), "opencore_sha256": oc_hash,
             "configuration_delta": "One appended BrightnessKeys Kernel.Add entry; no other changes.",
             "validation": validation}
    if arguments.audit_only:
        destination = cache / "audit.json"
        destination.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        destination.chmod(0o644)
    return audit, bundle, validator, candidate, oc_hash, assets


def absolute_readme_links(source: Path) -> str:
    regular_file(source)
    reference = os.environ.get("GITHUB_SHA", "main")
    if reference != "main" and re.fullmatch(r"[0-9a-f]{40}", reference) is None:
        fail("GITHUB_SHA must identify the source commit with 40 lowercase hexadecimal characters.")
    text = source.read_text(encoding="utf-8")

    def replace(match: re.Match) -> str:
        label, target = match.group(1), match.group(2)
        parsed = urlsplit(target)
        if parsed.scheme or parsed.netloc or not parsed.path:
            return match.group(0)
        destination = (source.parent / parsed.path).resolve()
        if not destination.is_relative_to(ROOT) or not destination.exists():
            fail("A package README link points outside the repository or to a missing file.")
        kind = "tree" if destination.is_dir() else "blob"
        relative = quote(destination.relative_to(ROOT).as_posix(), safe="/")
        fragment = "#" + parsed.fragment if parsed.fragment else ""
        url = f"https://github.com/{SOURCE_REPOSITORY}/{kind}/{reference}/{relative}{fragment}"
        return f"[{label}]({url})"

    return re.sub(r"\[([^\]\n]+)\]\(([^\s)]+)\)", replace, text)


def copy_source(source: Path, destination: Path, executable: bool = False) -> None:
    regular_file(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    destination.chmod(0o755 if executable else 0o644)


def write_bytes(destination: Path, raw: bytes, executable: bool = False) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(raw)
    destination.chmod(0o755 if executable else 0o644)


def package(arguments: argparse.Namespace, acquired: tuple) -> tuple[Path, str]:
    audit, bundle, validator, _, oc_hash, assets = acquired
    if arguments.audit_only or any(not valid_sha(asset["sha256"]) for asset in assets.values()):
        fail("An audit-only or unpinned acquisition cannot produce an installer.")
    output = plain_path(arguments.output_dir)
    destination = output / PACKAGE
    archive_path = output / f"{PACKAGE}.zip"
    sidecar = output / f"{PACKAGE}.zip.sha256"
    for path in (destination, archive_path, sidecar):
        if path.exists() or path.is_symlink():
            fail("The package destination already exists and will not be overwritten.")
    manifest = {
        "schema": 1, "identifier": IDENTIFIER, "version": VERSION,
        "files": [{"path": name, "sha256": sha256(raw)} for name, raw in sorted(bundle.items())],
        "validator_sha256": sha256(validator), "opencore_sha256": oc_hash,
    }
    # The runtime uses native plutil on macOS without developer tools. An XML
    # plist keeps the manifest readable by that interface on the target system.
    manifest_raw = plistlib.dumps(manifest, fmt=plistlib.FMT_XML, sort_keys=True)
    manifest_sha = sha256(manifest_raw)
    runtime = ROOT / "packages/function-keys"
    helper_source = runtime / "tools/brightness_keys_test.sh"
    regular_file(helper_source)
    helper_text = helper_source.read_text(encoding="utf-8")
    marker = "BRIGHTNESS_KEYS_MANIFEST_SHA_PENDING"
    if helper_text.count(marker) != 1:
        fail("The brightness helper must contain exactly one manifest placeholder.")
    with tempfile.TemporaryDirectory(prefix="brightness-package-", dir=output) as temporary_name:
        temporary = Path(temporary_name)
        stage = temporary / PACKAGE
        stage.mkdir()
        # Official kext bytes are copied unchanged; no plist patch or re-signing
        # occurs. The cache/audit directories are never copied into the package.
        for name, raw in bundle.items():
            write_bytes(stage / "payload" / name, raw, "/Contents/MacOS/" in name)
        write_bytes(stage / "payload/manifest.plist", manifest_raw)
        write_bytes(stage / "bin/ocvalidate", validator, True)
        for name in ("TEST-BRIGHTNESS-KEYS.command", "RESTORE-BRIGHTNESS-KEYS.command",
                     "COLLECT-FUNCTION-KEYS.command"):
            copy_source(runtime / name, stage / name, True)
        write_bytes(stage / "tools/brightness_keys_test.sh",
                    helper_text.replace(marker, manifest_sha).encode("utf-8"), True)
        copy_source(runtime / "tools/collect_function_keys.sh", stage / "tools/collect_function_keys.sh", True)
        write_bytes(stage / "README.md", absolute_readme_links(runtime / "README.md").replace("S540-brightness-keys", PACKAGE).encode("utf-8"))
        copy_source(ROOT / "licenses/brightness-keys/LICENSE", stage / "LICENSES/BrightnessKeys-LICENSE.txt")
        copy_source(ROOT / "licenses/efi/OpenCore-LICENSE.txt", stage / "LICENSES/OpenCore-LICENSE.txt")
        build = {"schema": 1, "package": PACKAGE, "source_commit": os.environ.get("GITHUB_SHA"),
                 "payload_manifest_sha256": manifest_sha,
                 "asset_lock_sha256": sha256(LOCK.read_bytes()),
                 "assets": audit["assets"], "validation": audit["validation"],
                 "hardware_status": "Native configuration validation only; no driver loading or keyboard event test."}
        write_bytes(stage / "BUILD.json", (json.dumps(build, indent=2, sort_keys=True) + "\n").encode("utf-8"))
        source_names = ["tools/brightness_keys_test.sh", "tools/collect_function_keys.sh",
                        "TEST-BRIGHTNESS-KEYS.command", "RESTORE-BRIGHTNESS-KEYS.command",
                        "COLLECT-FUNCTION-KEYS.command"]
        for name in source_names:
            subprocess.run(["/bin/bash", "-n", str(stage / name)],
                           check=True, capture_output=True, text=True, timeout=15)
        for name, raw in bundle.items():
            if (stage / "payload" / name).read_bytes() != raw:
                fail("The staged brightness driver differs from its official release.")
        staged_files = sorted(path for path in stage.rglob("*") if path.is_file())
        checksums = "".join(f"{sha256(path.read_bytes())}  {path.relative_to(stage).as_posix()}\n"
                            for path in staged_files)
        write_bytes(stage / "SHA256SUMS", checksums.encode("ascii"))
        staged_archive = temporary / archive_path.name
        with zipfile.ZipFile(staged_archive, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for path in sorted(stage.rglob("*")):
                if path.is_dir():
                    continue
                regular_file(path)
                relative = safe_relative(path.relative_to(stage).as_posix())
                entry = zipfile.ZipInfo(f"{PACKAGE}/{relative}", (2026, 10, 14, 0, 0, 0))
                entry.create_system = 3
                entry.external_attr = (stat.S_IFREG | stat.S_IMODE(path.stat().st_mode)) << 16
                entry.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(entry, path.read_bytes())
        with zipfile.ZipFile(staged_archive) as archive:
            checked_members(archive)
            expected_names = {f"{PACKAGE}/{path.relative_to(stage).as_posix()}"
                              for path in stage.rglob("*") if path.is_file()}
            if set(archive.namelist()) != expected_names:
                fail("The package ZIP contains unexpected paths.")
            for path in stage.rglob("*"):
                if path.is_file() and archive.read(f"{PACKAGE}/{path.relative_to(stage).as_posix()}") != path.read_bytes():
                    fail("The final ZIP differs from the verified staging files.")
        archive_sha = sha256(staged_archive.read_bytes())
        shutil.move(stage, destination)
        shutil.move(staged_archive, archive_path)
        sidecar.write_text(f"{archive_sha}  {archive_path.name}\n", encoding="ascii")
        sidecar.chmod(0o644)
    return archive_path, manifest_sha


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--audit-only", action="store_true",
                        help="Inspect official assets and native validation; never create an installer")
    arguments = parser.parse_args()
    try:
        result = acquire(arguments)
        if arguments.audit_only:
            print(f"Official asset audit completed: {arguments.output_dir / 'audit/audit.json'}")
            print("No installer package was created.")
        else:
            archive, manifest_sha = package(arguments, result)
            print(f"Verified brightness-key package: {archive}")
            print(f"Payload manifest SHA256: {manifest_sha}")
            print(f"Package SHA256: {sha256(archive.read_bytes())}")
        return 0
    except (ValueError, OSError, KeyError, TypeError, plistlib.InvalidFileException,
            json.JSONDecodeError, zipfile.BadZipFile, subprocess.SubprocessError) as exception:
        print(f"Brightness package not created: {exception}", file=sys.stderr)
        if isinstance(exception, subprocess.CalledProcessError) and exception.stderr:
            print(exception.stderr[-4000:], file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
