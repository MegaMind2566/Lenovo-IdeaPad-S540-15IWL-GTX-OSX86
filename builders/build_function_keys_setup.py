#!/usr/bin/env python3
"""Build the targeted Fn preference transaction and native key observer."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import re
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import zipfile

from build_function_key_events import digest, plain_path, run

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "S540-function-keys-setup"
INPUTS = {
    "PREPARE-FUNCTION-KEYS.command": "packages/function-keys-setup/PREPARE-FUNCTION-KEYS.command",
    "RESTORE-FN-SHORTCUTS.command": "packages/function-keys-setup/RESTORE-FN-SHORTCUTS.command",
    "README.md": "packages/function-keys-setup/README.md",
    "LICENSES/Preferences-MIT.txt": "packages/function-key-preferences/LICENSE",
    "LICENSES/Observer-MIT.txt": "packages/function-key-events/LICENSE",
}
NATIVE = {
    "function-key-preferences": ("packages/function-key-preferences/src/function_key_preferences.m",
                                 "org.s540.function-key-preferences", ["Foundation", "CoreFoundation"]),
    "function-key-events": ("packages/function-key-events/src/function_key_events.m",
                           "org.s540.function-key-events",
                           ["AppKit", "Foundation", "CoreFoundation", "CoreGraphics", "CoreAudio"]),
}


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
    if any(path.exists() or path.is_symlink() for path in (output / PACKAGE, archive_path, sidecar)):
        raise ValueError("The setup destination already exists.")
    sources = set(INPUTS.values()) | {entry[0] for entry in NATIVE.values()}
    source_hashes = {}
    for relative in sorted(sources):
        path = plain_path(ROOT / relative)
        if not path.is_file():
            raise ValueError("A required setup source is missing.")
        source_hashes[relative] = digest(path.read_bytes())
    with tempfile.TemporaryDirectory(prefix="function-setup-build-", dir=output) as name:
        temporary = Path(name)
        stage = temporary / PACKAGE
        (stage / "bin").mkdir(parents=True)
        native_results = {}
        for executable, (relative, identifier, frameworks) in NATIVE.items():
            binary = stage / "bin" / executable
            arguments = ["/usr/bin/clang", "-arch", "x86_64", "-mmacosx-version-min=13.0",
                         "-O2", "-fobjc-arc", "-Wall", "-Wextra", "-Werror", str(ROOT / relative)]
            for framework in frameworks:
                arguments.extend(["-framework", framework])
            arguments.extend(["-o", str(binary)])
            run(arguments)
            run(["/usr/bin/codesign", "--force", "--sign", "-", "--timestamp=none",
                 "--identifier", identifier, str(binary)])
            run(["/usr/bin/codesign", "--verify", "--strict", str(binary)])
            raw = binary.read_bytes()
            if len(raw) < 32 or struct.unpack_from("<4I", raw)[:2] != (0xFEEDFACF, 0x01000007) or struct.unpack_from("<4I", raw)[3] != 2:
                raise ValueError("A native helper is not a thin x86_64 Mach-O executable.")
            self_test = run([str(binary), "--self-test"], timeout=20)
            marker = "Pure shortcut fixture checks passed:" if executable == "function-key-preferences" else "Function-key decoder and privacy self-test passed."
            if marker not in self_test:
                raise ValueError("A native fixture self-test did not pass.")
            binary.chmod(0o755)
            native_results[executable] = {"sha256": digest(raw), "signature": "ad-hoc: " + identifier,
                                          "self_test": self_test}
        for target, relative in INPUTS.items():
            destination = stage / target
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, destination)
            destination.chmod(0o755 if target.endswith(".command") else 0o644)
            if target.endswith(".command"):
                run(["/bin/bash", "-n", str(destination)], timeout=15)
        record = {"schema": 1, "package": PACKAGE, "version": "1.0.0", "source_commit": source_commit,
                  "architecture": "x86_64", "minimum_macos": "13.0", "source_sha256": source_hashes,
                  "native_helpers": native_results,
                  "preference_scope": "Only enabled fields of plain F9-F12 symbolic IDs 32, 33, 36, 62.",
                  "hardware_status": "Fn events are recorded; preference refresh and targeted key events require the laptop result."}
        (stage / "BUILD.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        files = sorted(path for path in stage.rglob("*") if path.is_file())
        (stage / "SHA256SUMS").write_text("".join(digest(path.read_bytes()) + "  " +
            path.relative_to(stage).as_posix() + "\n" for path in files), encoding="ascii")
        files = sorted(path for path in stage.rglob("*") if path.is_file())
        archive = temporary / archive_path.name
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
            for path in files:
                relative = path.relative_to(stage).as_posix()
                if path.is_symlink():
                    raise ValueError("A link appeared in the setup staging directory.")
                entry = zipfile.ZipInfo(PACKAGE + "/" + relative, (2026, 10, 14, 0, 0, 0))
                entry.create_system = 3
                entry.external_attr = (stat.S_IFREG | stat.S_IMODE(path.stat().st_mode)) << 16
                entry.compress_type = zipfile.ZIP_DEFLATED
                bundle.writestr(entry, path.read_bytes())
        with zipfile.ZipFile(archive) as bundle:
            expected = {PACKAGE + "/" + path.relative_to(stage).as_posix() for path in files}
            if bundle.testzip() is not None or len(bundle.namelist()) != len(expected) or set(bundle.namelist()) != expected:
                raise ValueError("The final setup ZIP has invalid contents.")
            for path in files:
                if bundle.read(PACKAGE + "/" + path.relative_to(stage).as_posix()) != path.read_bytes():
                    raise ValueError("The final setup ZIP differs from its verified staging files.")
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
        print("Native Fn setup package: " + str(result))
        print("ZIP SHA256: " + digest(result.read_bytes()))
        return 0
    except (ValueError, OSError, subprocess.SubprocessError, zipfile.BadZipFile) as error:
        print("Fn setup package not created: " + str(error), file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.stderr:
            print(error.stderr[-6000:], file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
