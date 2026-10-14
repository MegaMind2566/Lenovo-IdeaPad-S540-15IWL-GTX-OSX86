#!/usr/bin/env python3
"""Build a native Intel macOS observer without installing it or capturing events."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "packages/function-key-events"
PACKAGE = "S540-function-key-events"


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def plain_path(path: Path) -> Path:
    absolute = Path(os.path.abspath(path))
    if any(part.is_symlink() for part in (absolute, *absolute.parents)):
        raise ValueError("A build path contains a symbolic link.")
    return absolute


def run(arguments: list[str], timeout: int = 120) -> str:
    result = subprocess.run(arguments, check=True, capture_output=True, text=True, timeout=timeout)
    return result.stdout.strip()


def build(output: Path) -> Path:
    if sys.platform != "darwin" or platform.machine() != "x86_64":
        raise ValueError("Build on the native Intel macOS runner.")
    source_commit = os.environ.get("GITHUB_SHA")
    if source_commit is not None and not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        raise ValueError("GITHUB_SHA must identify the source commit.")
    output = plain_path(output)
    output.mkdir(parents=True, exist_ok=True)
    archive_path = output / (PACKAGE + ".zip")
    sidecar = output / (PACKAGE + ".zip.sha256")
    if any(path.exists() or path.is_symlink() for path in (archive_path, sidecar, output / PACKAGE)):
        raise ValueError("The package destination already exists.")
    inputs = ("COLLECT-KEY-EVENTS.command", "README.md", "LICENSE", "src/function_key_events.m")
    source_hashes = {}
    for relative in inputs:
        path = plain_path(SOURCE / relative)
        if not path.is_file():
            raise ValueError("A required observer source file is missing.")
        source_hashes[relative] = digest(path.read_bytes())
    with tempfile.TemporaryDirectory(prefix="function-events-build-", dir=output) as name:
        temporary = Path(name)
        stage = temporary / PACKAGE
        (stage / "bin").mkdir(parents=True)
        binary = stage / "bin/function-key-events"
        run(["/usr/bin/clang", "-arch", "x86_64", "-mmacosx-version-min=13.0", "-O2", "-fobjc-arc",
             "-Wall", "-Wextra", "-Werror", str(SOURCE / "src/function_key_events.m"),
             "-framework", "AppKit", "-framework", "Foundation", "-framework", "CoreFoundation",
             "-framework", "CoreGraphics", "-framework", "CoreAudio", "-o", str(binary)])
        run(["/usr/bin/codesign", "--force", "--sign", "-", "--timestamp=none",
             "--identifier", "org.s540.function-key-events", str(binary)])
        run(["/usr/bin/codesign", "--verify", "--strict", str(binary)])
        raw = binary.read_bytes()
        if len(raw) < 32 or struct.unpack_from("<4I", raw)[:2] != (0xFEEDFACF, 0x01000007):
            raise ValueError("The observer is not a complete thin x86_64 Mach-O executable.")
        if struct.unpack_from("<4I", raw)[3] != 2:
            raise ValueError("The native observer has the wrong Mach-O file type.")
        self_test = run([str(binary), "--self-test"], timeout=20)
        if "decoder and privacy self-test passed" not in self_test:
            raise ValueError("The deterministic decoder/privacy self-test did not pass.")
        for relative in inputs[:3]:
            destination = stage / relative
            shutil.copyfile(SOURCE / relative, destination)
            destination.chmod(0o755 if relative.endswith(".command") else 0o644)
        binary.chmod(0o755)
        run(["/bin/bash", "-n", str(stage / "COLLECT-KEY-EVENTS.command")], timeout=15)
        record = {"schema": 1, "package": PACKAGE, "version": "1.0.0",
                  "source_commit": source_commit, "architecture": "x86_64", "minimum_macos": "13.0",
                  "source_sha256": source_hashes, "binary_sha256": digest(binary.read_bytes()),
                  "signature": "ad-hoc, identifier org.s540.function-key-events",
                  "native_self_test": self_test,
                  "hardware_status": "Event capture and hardware key behavior require the laptop report."}
        (stage / "BUILD.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        files = sorted(path for path in stage.rglob("*") if path.is_file())
        (stage / "SHA256SUMS").write_text("".join(digest(path.read_bytes()) + "  " +
            path.relative_to(stage).as_posix() + "\n" for path in files), encoding="ascii")
        files = sorted(path for path in stage.rglob("*") if path.is_file())
        archive = temporary / archive_path.name
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
            for path in files:
                relative = path.relative_to(stage).as_posix()
                parts = PurePosixPath(relative)
                if parts.is_absolute() or ".." in parts.parts or path.is_symlink():
                    raise ValueError("An unsafe file appeared in the staging directory.")
                entry = zipfile.ZipInfo(PACKAGE + "/" + relative, (2026, 10, 14, 0, 0, 0))
                entry.create_system = 3
                entry.external_attr = (stat.S_IFREG | stat.S_IMODE(path.stat().st_mode)) << 16
                entry.compress_type = zipfile.ZIP_DEFLATED
                bundle.writestr(entry, path.read_bytes())
        with zipfile.ZipFile(archive) as bundle:
            if bundle.testzip() is not None:
                raise ValueError("The final ZIP failed CRC verification.")
            expected = {PACKAGE + "/" + path.relative_to(stage).as_posix() for path in files}
            if len(bundle.namelist()) != len(expected) or set(bundle.namelist()) != expected:
                raise ValueError("The final ZIP has an unexpected file list.")
            for path in files:
                if bundle.read(PACKAGE + "/" + path.relative_to(stage).as_posix()) != path.read_bytes():
                    raise ValueError("The final ZIP differs from its verified staging files.")
        shutil.move(stage, output / PACKAGE)
        shutil.move(archive, archive_path)
        sidecar.write_text(digest(archive_path.read_bytes()) + "  " + archive_path.name + "\n", encoding="ascii")
    return archive_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    arguments = parser.parse_args()
    try:
        result = build(arguments.output_dir)
        print("Native function-key observer: " + str(result))
        print("ZIP SHA256: " + digest(result.read_bytes()))
        return 0
    except (ValueError, OSError, subprocess.SubprocessError, zipfile.BadZipFile) as error:
        print("Observer package not created: " + str(error), file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.stderr:
            print(error.stderr[-5000:], file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
