#!/usr/bin/env python3
"""Package the CI-built input-gain driver; never install or load a driver."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import plistlib
import re
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import zipfile


REPO = Path(__file__).resolve().parents[1]
PACKAGE = "S540-microfono-fix-v2"
VERSION = "3.6.9"
SOURCE_COMMIT = "8c7e8e2ce6de0a917be663a3192857955288c937"
SDK_COMMIT = "bfbfbe4cf35979f33ded6c7a8761eb1df091fb39"
ARCHIVE_URL = (
    "https://github.com/CloverHackyColor/VoodooHDA/releases/download/"
    "Release368/VoodooHDA.kext-368.zip"
)
ARCHIVE_SHA = "9aaa01b245f4827b2de5edfdc028700b9bc8823f03bfb1daf280b8571f88adb0"
ARCHIVE_SIZE = 135026
ORIGINAL_FILES = {
    "VoodooHDA.kext/Contents/Info.plist":
        "21b886b5449b9a0739422b6720ea2bc04fdcc477f79e1e3cece021033a51bf1a",
    "VoodooHDA.kext/Contents/MacOS/VoodooHDA":
        "932a7c9e46a65fdab7c8729f599c1094b568ae4fc7f17dad9818c83e833a0973",
    "VoodooHDA.kext/Contents/_CodeSignature/CodeResources":
        "6686de10a28a2fe11b36cbb86dcbacc827cfc4ea116b4dabf1845e5aee629e9b",
}
BUNDLE_FILES = (
    "Contents/Info.plist",
    "Contents/MacOS/VoodooHDA",
    "Contents/_CodeSignature/CodeResources",
)
LICENSES = (
    "AppleALC-LICENSE.txt",
    "VoodooHDA-LICENSE.txt",
    "VoodooHDA-third-party-LICENSE.txt",
)


def fail(message: str) -> None:
    raise ValueError(message)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def absolute_plain_path(value: str, *, directory: bool = False) -> Path:
    path = Path(value)
    if not path.is_absolute() or any(part in (".", "..") for part in value.split("/")):
        fail("I percorsi devono essere assoluti e senza componenti relative.")
    if "\n" in value or "\r" in value:
        fail("Il percorso contiene caratteri non ammessi.")
    for component in (path, *path.parents):
        if component.is_symlink():
            fail(f"Il percorso contiene un collegamento simbolico: {component}")
    if directory and not path.is_dir():
        fail(f"Cartella assente: {path}")
    return path


def regular_file(path: Path) -> None:
    if not path.is_file() or path.is_symlink():
        fail(f"File ordinario assente: {path}")


def run(*arguments: str) -> str:
    result = subprocess.run(
        arguments, check=True, text=True, capture_output=True, timeout=90
    )
    return result.stdout.strip()


def verify_macho(path: Path) -> None:
    regular_file(path)
    with path.open("rb") as stream:
        header = stream.read(32)
    if len(header) != 32:
        fail("Header Mach-O incompleto.")
    magic, cpu_type, _, file_type, _, _, _, _ = struct.unpack("<8I", header)
    if (magic, cpu_type, file_type) != (0xFEEDFACF, 0x01000007, 11):
        fail("Il driver deve essere un MH_KEXT_BUNDLE sottile x86_64.")
    if run("/usr/bin/lipo", "-archs", str(path)) != "x86_64":
        fail("Il driver non contiene soltanto l'architettura x86_64.")
    if b"S540InputGainFixActive" not in path.read_bytes():
        fail("Il driver compilato non contiene il marcatore della correzione ingresso.")


def load_original_info() -> dict:
    lock_path = REPO / "config/profiles/audio-tahoe-assets.lock.json"
    regular_file(lock_path)
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    expected = {
        "repository": "CloverHackyColor/VoodooHDA",
        "source_commit": SOURCE_COMMIT,
        "release": "Release368",
        "version": "3.6.8",
        "url": ARCHIVE_URL,
        "archive_sha256": ARCHIVE_SHA,
        "archive_size": ARCHIVE_SIZE,
        "files": ORIGINAL_FILES,
    }
    if lock != expected:
        fail("Il lock del rilascio audio non coincide con quello verificato.")
    # curl enforces one total 60-second network deadline, including redirects.
    with tempfile.TemporaryDirectory(prefix="s540-upstream-audio-") as temporary:
        download = Path(temporary) / "release.zip"
        subprocess.run(
            ["/usr/bin/curl", "--fail", "--location", "--silent", "--show-error",
             "--proto", "=https", "--proto-redir", "=https", "--max-redirs", "5",
             "--connect-timeout", "15", "--max-time", "60", "--max-filesize",
             str(ARCHIVE_SIZE), "--output", str(download), ARCHIVE_URL],
            check=True, text=True, capture_output=True, timeout=65,
        )
        if download.stat().st_size != ARCHIVE_SIZE:
            fail("Dimensione del rilascio ufficiale non valida.")
        data = download.read_bytes()
        if digest(data) != ARCHIVE_SHA:
            fail("SHA256 del rilascio ufficiale non valido.")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        # The entire pinned archive is already authenticated above. Read only
        # the three canonical bundle files; never extract archive metadata.
        files = [item for item in archive.infolist() if item.filename in ORIGINAL_FILES]
        if any(sum(item.filename == name for item in files) != 1 for name in ORIGINAL_FILES):
            fail("Ogni file canonico deve comparire esattamente una volta nel rilascio.")
        contents = {}
        for item in files:
            mode = item.external_attr >> 16
            if item.is_dir() or stat.S_ISLNK(mode) or item.file_size > 4 * 1024 * 1024:
                fail("Il rilascio contiene un link o un file troppo grande.")
            value = archive.read(item)
            if digest(value) != ORIGINAL_FILES[item.filename]:
                fail(f"Impronta upstream errata: {item.filename}")
            contents[item.filename] = value
    info = plistlib.loads(contents["VoodooHDA.kext/Contents/Info.plist"])
    if not isinstance(info, dict):
        fail("Il plist originale non è un dizionario.")
    return info


def canonical_manifest(bundle: Path) -> tuple[bytes, dict[str, str]]:
    actual = {item.relative_to(bundle).as_posix() for item in bundle.rglob("*") if item.is_file()}
    if actual != set(BUNDLE_FILES) or any(item.is_symlink() for item in bundle.rglob("*")):
        fail("Il bundle firmato non contiene soltanto i tre file canonici.")
    hashes = {relative: file_digest(bundle / relative) for relative in BUNDLE_FILES}
    manifest = "".join(f"{hashes[relative]}  {relative}\n" for relative in BUNDLE_FILES)
    return manifest.encode("ascii"), hashes


def copy_plain(source: Path, destination: Path, *, executable: bool = False) -> None:
    regular_file(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    destination.chmod(0o755 if executable else 0o644)


def write_json(path: Path, content: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(content, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    path.chmod(0o644)


def make_package(built_bundle: Path, output: Path) -> Path:
    commit = os.environ.get("GITHUB_SHA", "")
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        fail("GITHUB_SHA deve identificare il commit CI con 40 caratteri esadecimali.")
    patch = REPO / "patches/audio-microphone/input-gain.patch"
    regular_file(patch)
    source_binary = built_bundle / "Contents/MacOS/VoodooHDA"
    absolute_plain_path(str(source_binary))
    verify_macho(source_binary)
    info = load_original_info()
    info["CFBundleVersion"] = VERSION
    info["CFBundleShortVersionString"] = VERSION
    personality = info["IOKitPersonalities"]["VoodooHDA"]
    personality["VoodooHDAEnableVolumeChangeFix"] = True
    personality["S540InputGainFix"] = True
    personality["MixerValues"]["Rec"] = 50
    personality["MixerValues"]["iMix"] = 100
    package = output / PACKAGE
    archive_path = output / f"{PACKAGE}.zip"
    if any(path.exists() or path.is_symlink() for path in
           (package, archive_path, output / f"{PACKAGE}.zip.sha256")):
        fail("La destinazione del pacchetto esiste già; non verrà sovrascritta.")
    with tempfile.TemporaryDirectory(prefix="s540-microphone-package-", dir=output) as temporary:
        stage = Path(temporary) / PACKAGE
        stage.mkdir()
        bundle = stage / "assets/microphone/VoodooHDA.kext"
        (bundle / "Contents/MacOS").mkdir(parents=True)
        copy_plain(source_binary, bundle / "Contents/MacOS/VoodooHDA", executable=True)
        (bundle / "Contents/Info.plist").write_bytes(
            plistlib.dumps(info, fmt=plistlib.FMT_XML, sort_keys=False)
        )
        (bundle / "Contents/Info.plist").chmod(0o644)
        run("/usr/bin/codesign", "--force", "--sign", "-", str(bundle))
        run("/usr/bin/codesign", "--verify", "--strict", str(bundle))
        verify_macho(bundle / "Contents/MacOS/VoodooHDA")
        manifest, payload_hashes = canonical_manifest(bundle)
        manifest_sha = digest(manifest)
        sums = stage / "assets/microphone/SHA256SUMS"
        sums.write_bytes(manifest)
        sums.chmod(0o644)
        for name in ("INSTALLA-MICROFONO.command", "ANNULLA-MICROFONO.command", "VERIFICA-MICROFONO.command"):
            copy_plain(REPO / "packages/microphone" / name, stage / name, executable=True)
        helper_source = REPO / "packages/microphone/tools/microphone_driver_test.sh"
        regular_file(helper_source)
        helper_text = helper_source.read_text(encoding="utf-8")
        if helper_text.count("MICROPHONE_MANIFEST_SHA_PENDING") != 1:
            fail("Il segnaposto del manifest nel helper non è unico.")
        helper = stage / "tools/microphone_driver_test.sh"
        helper.parent.mkdir()
        helper.write_text(
            helper_text.replace("MICROPHONE_MANIFEST_SHA_PENDING", manifest_sha), encoding="utf-8"
        )
        helper.chmod(0o755)
        copy_plain(REPO / "packages/microphone/tools/verify_microphone_driver.sh", stage / "tools/verify_microphone_driver.sh", executable=True)
        copy_plain(REPO / "docs/guides/MICROFONO-FIX.md", stage / "LEGGIMI.md")
        for name in LICENSES:
            copy_plain(REPO / "licenses/audio-tahoe" / name, stage / "licenses/audio-tahoe" / name)
        # This validates only the packaged payload. It must not install/load it,
        # inspect a user's live driver, invoke kmutil, or require root in CI.
        run("/bin/bash", str(helper), "payload-check")
        artifact_lock = {
            "format": 1,
            "version": VERSION,
            "source_commit": SOURCE_COMMIT,
            "kernel_sdk_commit": SDK_COMMIT,
            "patch_sha256": file_digest(patch),
            "original_release_archive_sha256": ARCHIVE_SHA,
            "payload_manifest_sha256": manifest_sha,
            "files": payload_hashes,
        }
        write_json(stage / "profiles/audio-microphone-assets.lock.json", artifact_lock)
        provenance = {
            "format": 1,
            "package": PACKAGE,
            "github_sha": commit,
            "upstream_repository": "CloverHackyColor/VoodooHDA",
            "upstream_commit": SOURCE_COMMIT,
            "kernel_sdk_repository": "joevt/MacKernelSDK",
            "kernel_sdk_commit": SDK_COMMIT,
            "patch_sha256": file_digest(patch),
            "compiled_macho_sha256_before_signing": file_digest(source_binary),
            "payload_manifest_sha256": manifest_sha,
            "payload_files": payload_hashes,
            "package_file_sha256_excluding_BUILD": {
                item.relative_to(stage).as_posix(): file_digest(item)
                for item in sorted(stage.rglob("*")) if item.is_file()
            },
            "validation": ["upstream archive size and SHA256", "three upstream file SHA256", "thin x86_64 MH_KEXT_BUNDLE", "S540InputGainFixActive marker", "ad-hoc codesign --verify --strict", "native read-only helper payload-check"],
        }
        write_json(stage / "BUILD.json", provenance)
        staged_zip = Path(temporary) / archive_path.name
        with zipfile.ZipFile(staged_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for item in sorted(stage.rglob("*")):
                if not item.is_file():
                    continue
                if item.is_symlink() or item.name == ".DS_Store":
                    fail("Il pacchetto contiene file non ammessi.")
                relative = (Path(PACKAGE) / item.relative_to(stage)).as_posix()
                entry = zipfile.ZipInfo(relative, date_time=(2026, 10, 14, 0, 0, 0))
                entry.create_system = 3
                entry.external_attr = (stat.S_IFREG | stat.S_IMODE(item.stat().st_mode)) << 16
                entry.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(entry, item.read_bytes())
        staged_zip.chmod(0o644)
        zip_sha = file_digest(staged_zip)
        # Publish only after every verification has completed.
        shutil.move(stage, package)
        shutil.move(staged_zip, archive_path)
        (output / f"{archive_path.name}.sha256").write_text(
            f"{zip_sha}  {archive_path.name}\n", encoding="ascii"
        )
    return archive_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--built-bundle", required=True, help="Absolute path of the native CI-built VoodooHDA.kext")
    parser.add_argument("--output-dir", required=True, help="Absolute output directory")
    arguments = parser.parse_args()
    try:
        if sys.platform != "darwin" or platform.machine() != "x86_64":
            fail("La creazione del pacchetto richiede macOS Intel e gli strumenti Apple nativi.")
        built_bundle = absolute_plain_path(arguments.built_bundle, directory=True)
        output = absolute_plain_path(arguments.output_dir)
        output.mkdir(parents=True, exist_ok=True)
        if not output.is_dir():
            fail("La destinazione non è una cartella.")
        archive = make_package(built_bundle, output)
        print(f"Pacchetto verificato: {archive}")
        print(f"SHA256: {file_digest(archive)}")
        return 0
    except (ValueError, OSError, KeyError, plistlib.InvalidFileException, json.JSONDecodeError, zipfile.BadZipFile, subprocess.SubprocessError) as error:
        print(f"Pacchetto non creato: {error}", file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.stderr:
            print(error.stderr[-4000:], file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
