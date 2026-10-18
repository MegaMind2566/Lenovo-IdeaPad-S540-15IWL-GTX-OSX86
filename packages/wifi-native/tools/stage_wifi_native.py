#!/usr/bin/env python3
"""Prepare an offline EFI copy for the AC9560 Tahoe trial; never install it."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import plistlib
import shutil
import struct
import subprocess
import tempfile


IDENTIFIER = "com.zxystd.AirportItlwm"
PACKAGE = "S540-wifi-native-v1"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def regular_tree(root: Path) -> None:
    if root.is_symlink() or not root.is_dir():
        raise ValueError("A regular directory is required.")
    for path in root.rglob("*"):
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise ValueError("Links and special files are not accepted.")


def verify_kext(kext: Path) -> dict:
    regular_tree(kext)
    info = plistlib.loads((kext / "Contents/Info.plist").read_bytes())
    if (info.get("CFBundleIdentifier") != IDENTIFIER
            or info.get("CFBundleExecutable") != "AirportItlwm"
            or info.get("CFBundlePackageType") != "KEXT"):
        raise ValueError("The payload is not the expected AirportItlwm extension.")
    libraries = info.get("OSBundleLibraries", {})
    if not {"com.apple.iokit.IO80211Family", "com.apple.iokit.IOSkywalkFamily"} <= libraries.keys():
        raise ValueError("The native Tahoe Wi-Fi dependencies are missing.")
    personalities = info.get("IOKitPersonalities", {})
    matches = personalities.get("itlwm", {}).get("IOPCIMatch", "").lower().split()
    if "0x9df08086" not in matches:
        raise ValueError("The AC9560 PCI match is absent.")
    if personalities.get("NetworkController", {}).get("IONetworkRootType") != "airport":
        raise ValueError("The controller is not declared as Airport.")
    raw = (kext / "Contents/MacOS/AirportItlwm").read_bytes()
    if len(raw) < 32 or struct.unpack_from("<4I", raw) != (0xfeedfacf, 0x01000007, 3, 11):
        raise ValueError("The executable must be a thin x86_64 Mach-O kernel extension.")
    return {"identifier": IDENTIFIER, "version": info["CFBundleVersion"],
            "executable_sha256": hashlib.sha256(raw).hexdigest()}


def verify_package(package: Path) -> dict:
    regular_tree(package)
    record = json.loads((package / "manifest.json").read_text())
    if (record.get("package") != PACKAGE or record.get("schema") != 1
            or record.get("build_status") != "compiled_and_verified"
            or record.get("laptop_validated") is not False):
        raise ValueError("A compiled, verified Wi-Fi trial package is required.")
    files = record.get("files")
    if not isinstance(files, dict) or not files:
        raise ValueError("The package checksum manifest is missing.")
    for name, expected in files.items():
        relative = PurePosixPath(name)
        if relative.is_absolute() or ".." in relative.parts or str(relative) != name or "\\" in name:
            raise ValueError("The package manifest contains an unsafe path.")
        path = package / name
        if not path.is_file() or digest(path) != expected:
            raise ValueError("A package file failed checksum verification.")
    required = {"tools/ocvalidate", "payload/AirportItlwm.kext/Contents/Info.plist",
                "payload/AirportItlwm.kext/Contents/MacOS/AirportItlwm"}
    actual = {str(p.relative_to(package)) for p in (package / "payload").rglob("*") if p.is_file()}
    if not required <= files.keys() or not actual <= files.keys():
        raise ValueError("The payload is not fully covered by the manifest.")
    verify_kext(package / "payload/AirportItlwm.kext")
    return record


def native_config(original: dict) -> dict:
    result = copy.deepcopy(original)
    kernel = result["Kernel"]
    entries = kernel["Add"]
    for entry in kernel.get("Block", []):
        if entry.get("Enabled") and entry.get("Identifier") in {
                "com.apple.iokit.IO80211Family", "com.apple.iokit.IOSkywalkFamily"}:
            raise ValueError("Remove the legacy Wi-Fi stack block before preparing this trial.")
    for entry in entries:
        name = str(entry.get("BundlePath", "")).lower()
        if "airportitlwm" in name:
            raise ValueError("An AirportItlwm entry is already present; review it before staging.")
        if entry.get("Enabled") and any(x in name for x in (
                "io80211familylegacy", "ioskywalkfamily", "airportbrcmfixup", "airport.brcmnic")):
            raise ValueError("An injected legacy Wi-Fi stack conflicts with the Tahoe build.")
    drivers = [e for e in entries if str(e.get("BundlePath", "")).lower() == "itlwm.kext"]
    if len(drivers) != 1 or drivers[0].get("Enabled") is not True:
        raise ValueError("Exactly one enabled itlwm.kext entry is required.")
    drivers[0]["Enabled"] = False
    entries.append({
        "Arch": "x86_64", "BundlePath": "AirportItlwm.kext",
        "Comment": "AC9560 native Tahoe trial; pinned laobamac 738d4c6",
        "Enabled": True, "ExecutablePath": "Contents/MacOS/AirportItlwm",
        "MaxKernel": "25.99.99", "MinKernel": "25.0.0", "PlistPath": "Contents/Info.plist",
    })
    return result


def validate(validator: Path, config: Path) -> None:
    run = subprocess.run([str(validator), str(config)], capture_output=True, text=True, timeout=30)
    if run.returncode:
        # Do not copy private config values from validator output into a public log.
        raise ValueError("OpenCore 1.0.8 ocvalidate rejected the configuration.")


def stage(efi: Path, output: Path, package: Path) -> None:
    efi, output, package = map(lambda p: Path(os.path.abspath(p)), (efi, output, package))
    verify_package(package)
    regular_tree(efi)
    source, target = efi.resolve(), output.resolve()
    if (target == source or target.is_relative_to(source) or source.is_relative_to(target)
            or target.is_relative_to(package.resolve()) or package.resolve().is_relative_to(target)):
        raise ValueError("The output must be separate from the original EFI and the package.")
    if target.is_relative_to(Path("/Volumes")) or output.exists() or output.is_symlink():
        raise ValueError("Choose a new offline output folder outside /Volumes.")
    for name in ("OC/config.plist", "OC/OpenCore.efi", "BOOT/BOOTx64.efi",
                 "OC/Kexts/itlwm.kext/Contents/Info.plist"):
        if not (efi / name).is_file():
            raise ValueError("The source is not a complete working itlwm EFI.")
    if (efi / "OC/Kexts/AirportItlwm.kext").exists():
        raise ValueError("An AirportItlwm payload is already present in the source EFI.")
    config = native_config(plistlib.loads((efi / "OC/config.plist").read_bytes()))
    validator = package / "tools/ocvalidate"
    validate(validator, efi / "OC/config.plist")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".s540-wifi-", dir=output.parent) as temporary:
        staged = Path(temporary) / "EFI"
        shutil.copytree(efi, staged)
        shutil.copytree(package / "payload/AirportItlwm.kext", staged / "OC/Kexts/AirportItlwm.kext")
        (staged / "OC/config.plist").write_bytes(plistlib.dumps(config, sort_keys=False))
        validate(validator, staged / "OC/config.plist")
        if output.exists() or output.is_symlink():
            raise ValueError("The output appeared during staging; refusing to overwrite it.")
        staged.rename(output)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--efi", required=True, type=Path, help="Current private EFI directory")
    parser.add_argument("--output", required=True, type=Path, help="New offline EFI directory")
    args = parser.parse_args()
    try:
        stage(args.efi, args.output, Path(__file__).resolve().parents[1])
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as error:
        parser.exit(1, f"Cannot prepare native Wi-Fi: {error}\n")
    print("Native Wi-Fi EFI copy prepared and validated. Original EFI unchanged.")
    print("This is a Tahoe-only boot trial. The prepared EFI contains private data; do not upload it.")


if __name__ == "__main__":
    main()
