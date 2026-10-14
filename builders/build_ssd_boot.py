#!/usr/bin/env python3
"""Package the reversible external-SSD EFI transfer helper without compilation."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "packages/ssd-boot"
PACKAGE = "S540-ssd-boot"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build(output: Path) -> Path:
    output = output.absolute()
    if any(path.is_symlink() for path in (output, *output.parents)):
        raise ValueError("The build output path contains a symbolic link.")
    output.mkdir(parents=True, exist_ok=True)
    archive_path = output / (PACKAGE + ".zip")
    sidecar_path = output / (PACKAGE + ".zip.sha256")
    if archive_path.exists() or sidecar_path.exists():
        raise ValueError("The package destination already exists.")
    source_commit = os.environ.get("GITHUB_SHA")
    if source_commit is not None and not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        raise ValueError("GITHUB_SHA must identify the source commit.")
    payload = {}
    for filename in ("INSTALL-SSD-BOOT.command", "README.md"):
        path = SOURCE / filename
        if path.is_symlink() or not path.is_file():
            raise ValueError("A required plain source file is missing.")
        payload[filename] = path.read_bytes()
    subprocess.run(["/bin/bash", "-n", str(SOURCE / "INSTALL-SSD-BOOT.command")], check=True, timeout=10)
    tested = subprocess.run(["/bin/bash", str(SOURCE / "INSTALL-SSD-BOOT.command"), "--self-test"],
                            check=True, capture_output=True, text=True, timeout=10)
    expected = "SSD boot guard fixtures passed.\n"
    if tested.stdout != expected:
        raise ValueError("The deterministic SSD boot guard fixtures did not pass.")
    record = {"schema": 1, "package": PACKAGE, "version": "1.0.0",
              "source_commit": source_commit, "runtime": "macOS Intel; built-in Bash 3.2 and Apple command-line utilities",
              "source_sha256": {name: digest(data) for name, data in payload.items()},
              "fixture_checks": tested.stdout.strip(),
              "hardware_status": "Guard and copy fixtures passed; independent laptop boot remains pending.",
              "operation": "Copy current private BOOT and OC to the existing EFI partition on the external macOS system disk"}
    payload["BUILD.json"] = (json.dumps(record, indent=2, sort_keys=True) + "\n").encode("utf-8")
    payload["SHA256SUMS"] = "".join(digest(data) + "  " + name + "\n"
                                     for name, data in sorted(payload.items())).encode("ascii")
    with tempfile.TemporaryDirectory(prefix="ssd-boot-build-", dir=output) as temporary:
        temporary_archive = Path(temporary) / archive_path.name
        with zipfile.ZipFile(temporary_archive, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
            for name, data in sorted(payload.items()):
                entry = zipfile.ZipInfo(PACKAGE + "/" + name, (2026, 10, 14, 0, 0, 0))
                entry.create_system = 3
                entry.external_attr = (stat.S_IFREG | (0o755 if name.endswith(".command") else 0o644)) << 16
                entry.compress_type = zipfile.ZIP_DEFLATED
                bundle.writestr(entry, data)
        with zipfile.ZipFile(temporary_archive) as bundle:
            if bundle.testzip() is not None or len(bundle.namelist()) != len(payload):
                raise ValueError("The ZIP failed its structure or CRC check.")
            for name, data in payload.items():
                if bundle.read(PACKAGE + "/" + name) != data:
                    raise ValueError("The ZIP differs from its verified source files.")
        os.replace(temporary_archive, archive_path)
    sidecar_path.write_text(digest(archive_path.read_bytes()) + "  " + archive_path.name + "\n", encoding="ascii")
    return archive_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = build(args.output_dir)
        print("SSD boot package: " + str(result))
        print("ZIP SHA256: " + digest(result.read_bytes()))
        return 0
    except (OSError, ValueError, subprocess.SubprocessError, zipfile.BadZipFile) as error:
        print("SSD boot package not created: " + str(error))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
