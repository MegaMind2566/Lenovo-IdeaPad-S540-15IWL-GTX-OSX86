#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Reproducible real-image CPU validation; never executes the NVIDIA installer."""
from __future__ import annotations
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "packages/nvidia-firmware-assets"
SPEC = importlib.util.spec_from_file_location("nvidia_firmware_assets_acquire", PACKAGE / "acquire.py")
ACQUIRE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ACQUIRE)


def execute(command, *, expected=0, environment=None):
    result = subprocess.run([str(item) for item in command], capture_output=True, text=True,
                            env=environment, timeout=180)
    if result.returncode != expected:
        raise RuntimeError("Firmware check command failed: " + str(command[0]) + "\n" +
                           result.stdout[-3000:] + result.stderr[-3000:])
    return result.stdout


def json_run(command, *, expected=0, environment=None):
    return json.loads(execute(command, expected=expected, environment=environment))


def bridge_failure_checks(executable, assets, work, environment):
    required = ("gsp_tu10x.bin", "ucodes_tu10x.bin", "NVIDIA-DRIVER-LICENSE.txt")
    cases = []
    absent = work / "absent"
    cases.append((absent, "missing_assets"))
    empty = work / "empty"; empty.mkdir()
    cases.append((empty, "missing_assets"))
    linked = work / "linked"; linked.symlink_to(assets, target_is_directory=True)
    cases.append((linked, "unsafe_file"))
    for name, changed in (("symlink", "gsp_tu10x.bin"),
                          ("fifo", "gsp_tu10x.bin"),
                          ("truncated", "gsp_tu10x.bin"),
                          ("corrupt", "gsp_tu10x.bin"),
                          ("notice-corrupt", "NVIDIA-DRIVER-LICENSE.txt")):
        folder = work / name; folder.mkdir()
        for filename in required:
            target = folder / filename
            if filename != changed:
                os.link(assets / filename, target)
            elif name == "symlink":
                target.symlink_to(assets / filename)
            elif name == "fifo":
                os.mkfifo(target)
            elif name == "truncated":
                target.write_bytes(b"x")
            elif name == "corrupt":
                with target.open("wb") as handle:
                    handle.truncate(22901632)
            else:
                data = bytearray((assets / filename).read_bytes()); data[0] ^= 1
                target.write_bytes(data)
        reason = "unsafe_file" if name in ("symlink", "fifo") else ("size_mismatch" if name == "truncated" else "hash_mismatch")
        cases.append((folder, reason))
    for folder, reason in cases:
        report = json_run([executable, folder], expected=1, environment=environment)
        if report["pair_ready"] is not False or report["cleanup"] is not True or report["reason"] != reason:
            raise RuntimeError("Userspace asset failure did not fail closed with cleanup")
    return len(cases)


def run_checks(assets_dir: Path, build_dir: Path, *, download=False, archive_path=None,
               cache_dir=None, sanitizers=True):
    build_dir.mkdir(parents=True, exist_ok=True)
    assets_dir = assets_dir.absolute()
    manifest = ACQUIRE.MANIFEST
    if manifest["source_commit"] != "1a82fbfda8f321b056eb3568850f9316c5e465c5" or manifest["release"] != "615.78.08":
        raise RuntimeError("Firmware source/release pin changed")
    if archive_path is not None or download:
        acquisition = ACQUIRE.acquire(assets_dir, cache=cache_dir, archive_path=archive_path)
    else:
        acquisition = {"assets": ACQUIRE.verify_assets(assets_dir),
                       "archive_sha256": manifest["archive"]["sha256"],
                       "cache_reused": True}
    execute([os.environ.get("PYTHON", "python3"), PACKAGE / "tests/test_assets.py"])
    cxx = shutil.which(os.environ.get("CXX", "clang++")) or shutil.which("c++")
    cc = shutil.which(os.environ.get("CC", "clang")) or shutil.which("cc")
    if not cxx or not cc:
        raise RuntimeError("A native C/C++ compiler is required")
    sources = [ROOT / "packages/nvidia-hardware-transport/firmware/S540NvidiaFirmware.cpp",
               PACKAGE / "src/S540NvidiaFirmwareAssets.cpp"]
    include = ROOT / "packages/nvidia-os-adapter/upstream/include"
    environment = os.environ.copy()
    environment.setdefault("ASAN_OPTIONS", "detect_leaks=0:halt_on_error=1:abort_on_error=1")
    environment.setdefault("UBSAN_OPTIONS", "halt_on_error=1:print_stacktrace=1")
    runs = {}
    for variant in (["plain", "sanitized"] if sanitizers else ["plain"]):
        output = build_dir / variant; output.mkdir(exist_ok=True)
        flags = ["-std=c++14", "-O1", "-g", "-Wall", "-Wextra", "-Werror", "-I", include]
        sanitize = ["-fsanitize=address,undefined", "-fno-sanitize-recover=all", "-fno-omit-frame-pointer"] if variant == "sanitized" else []
        native = output / "check-assets-native"
        execute([cxx, *flags, *sanitize, *sources, PACKAGE / "tests/check_assets_native.cpp", "-o", native])
        native_report = json_run([native, assets_dir / "gsp_tu10x.bin", assets_dir / "ucodes_tu10x.bin"], environment=environment)
        if native_report.get("status") != "passed" or native_report.get("image_verified") is not True or native_report.get("ucodes_verified") is not True:
            raise RuntimeError("Actual asset pair failed CPU/native validation")
        obj = output / "bridge-c.o"
        execute([cc, "-std=c11", "-Wall", "-Wextra", "-Werror", *sanitize, "-c", PACKAGE / "tests/check_assets_bridge.c", "-o", obj])
        bridge = output / "check-assets-bridge"
        execute([cxx, *flags, *sanitize, *sources, PACKAGE / "src/S540NvidiaFirmwareAssetsUser.cpp", obj, "-o", bridge])
        bridge_report = json_run([bridge, assets_dir], environment=environment)
        if bridge_report["pair_ready"] is not True or bridge_report["cleanup"] is not True:
            raise RuntimeError("C ABI did not verify and release the actual assets")
        with tempfile.TemporaryDirectory(prefix="failure-cases-", dir=output) as failure_work:
            failures_checked = bridge_failure_checks(bridge, assets_dir, Path(failure_work), environment)
        runs[variant] = {"native": native_report, "bridge": bridge_report,
                         "bridge_failure_cases": failures_checked}
    report = {"format": 1, "component": "nvidia-firmware-assets", "release": manifest["release"],
              "source_commit": manifest["source_commit"], "status": "passed",
              "real_image_verified": True, "firmware_loaded": False, "gpu_initialized": False,
              "execution": "native-user-space", "kernel_runtime": "not_tested",
              "asset_pair": acquisition["assets"], "official_archive_sha256": manifest["archive"]["sha256"],
              "provenance_tests": 16, "runs": runs}
    (build_dir / "firmware-assets-checks.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets-dir", type=Path, required=True)
    parser.add_argument("--build-dir", type=Path)
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--cache-dir", type=Path, default=Path(tempfile.gettempdir()) / "s540-nvidia-615-cache")
    parser.add_argument("--no-sanitizers", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="s540-firmware-check-") as temporary:
        report = run_checks(args.assets_dir, args.build_dir or Path(temporary), download=args.download,
                            archive_path=args.archive, cache_dir=args.cache_dir, sanitizers=not args.no_sanitizers)
    payload = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(payload)
    print(payload, end="")


if __name__ == "__main__":
    main()
