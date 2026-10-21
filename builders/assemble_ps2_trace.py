#!/usr/bin/env python3
"""Assemble a PS/2 trace package using the pinned, unchanged native guard."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import zipfile

ARTIFACT_SHA = "ee21910af50dbbc86882294d46617fffc21268e54a00f1dbaf8360f78fc95ce4"
BINARY_SHA = "658d784f0e5de692e17e35df090982ae13c32a8fc1f993193cbdade72a667ef4"
SOURCE_SHA = "825d0daee8a8143e4e216199fe95c4d6baa260ea0dc9b819b65c54b7ce4d8731"
ORIGINAL_COMMIT = "b8461368dac069de2d8f8b7911e29cd206b6bbc3"
PACKAGE = "S540-PS2-Trace-v1"
OLD_PACKAGE = "S540-function-key-scancodes"
SOURCE_FILES = ("CONTROLLA-TASTI.command", "parse-trace.js", "LEGGIMI.txt")


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def assemble(source: Path, artifact: Path, output: Path) -> Path:
    raw = artifact.read_bytes()
    if sha(raw) != ARTIFACT_SHA:
        raise ValueError("Original GitHub artifact digest does not match the pinned build.")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        inner = archive.read(OLD_PACKAGE + ".zip")
        sidecar = archive.read(OLD_PACKAGE + ".zip.sha256").decode("ascii")
        if sidecar.split()[0] != sha(inner):
            raise ValueError("Original package sidecar does not match.")
    with zipfile.ZipFile(io.BytesIO(inner)) as archive:
        prefix = OLD_PACKAGE + "/"
        original_build = archive.read(prefix + "BUILD.json")
        original = json.loads(original_build)
        binary = archive.read(prefix + "bin/function-key-scancodes")
        license_bytes = archive.read(prefix + "LICENSE")
        for line in archive.read(prefix + "SHA256SUMS").decode("ascii").splitlines():
            digest, relative = line.split(None, 1)
            relative = relative.lstrip(" *")
            if sha(archive.read(prefix + relative)) != digest:
                raise ValueError("Original manifest mismatch: " + relative)
    if sha(binary) != BINARY_SHA or original["binary_sha256"] != BINARY_SHA:
        raise ValueError("Native binary changed.")
    if original["source_commit"] != ORIGINAL_COMMIT or original["source_sha256"]["src/function_key_scancodes.m"] != SOURCE_SHA:
        raise ValueError("Original source provenance changed.")
    files = {relative: (source / relative).read_bytes() for relative in SOURCE_FILES}
    helper_source = (source / "src/function_key_scancodes.m").read_bytes()
    if sha(helper_source) != SOURCE_SHA:
        raise ValueError("The included guard source does not match the original build.")
    files.update({"bin/function-key-scancodes": binary, "LICENSE": license_bytes,
                  "ORIGINAL-BUILD.json": original_build, "src/function_key_scancodes.m": helper_source})
    build = {
        "schema": 1, "package": PACKAGE, "version": "1.0.0",
        "architecture": "x86_64", "minimum_macos": "13.0",
        "native_guard_unchanged": True, "native_guard_binary_sha256": BINARY_SHA,
        "original_build_commit": ORIGINAL_COMMIT, "original_workflow_run": 38614049964,
        "original_native_self_test": original["native_self_test"],
        "new_native_build_performed": False,
        "target_hardware_validation": "Pending: the first Fn+F5 control must validate trace visibility.",
        "source_sha256": {name: sha(data) for name, data in sorted(files.items()) if name != "bin/function-key-scancodes"},
    }
    files["BUILD.json"] = (json.dumps(build, indent=2, sort_keys=True) + "\n").encode()
    files["SHA256SUMS"] = "".join(f"{sha(data)}  {name}\n" for name, data in sorted(files.items())).encode()
    output.mkdir(parents=True, exist_ok=True)
    target = output / (PACKAGE + ".zip")
    if target.exists():
        raise ValueError("Output already exists; use a new output directory.")
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(PACKAGE + "/" + name, (1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            mode = 0o100755 if name in ("CONTROLLA-TASTI.command", "bin/function-key-scancodes") else 0o100644
            info.external_attr = mode << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
    (output / (target.name + ".sha256")).write_text(f"{sha(target.read_bytes())}  {target.name}\n", encoding="ascii")
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--original-artifact", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(assemble(args.source, args.original_artifact, args.output_dir))
