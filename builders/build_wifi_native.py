#!/usr/bin/env python3
"""Build the pinned AirportItlwm Tahoe source and an offline AC9560 trial bundle."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import platform
import plistlib
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import zipfile


ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "config/profiles/wifi-native.lock.json"
SOURCE = ROOT / "packages/wifi-native"
PACKAGE = "S540-wifi-native-v1"
FIRMWARE_SHA = "d69ab6a3775aaf9424455fb99fe1327f7407aaf26b7711cc699536bfb71b25e5"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fetch(asset: dict, destination: Path) -> Path:
    if destination.is_symlink():
        raise ValueError("The archive cache must not contain links.")
    if not destination.exists():
        partial = destination.with_suffix(destination.suffix + ".partial")
        try:
            # Bound downloads by the pinned asset size. Never accept a moving release.
            with urllib.request.urlopen(asset["url"], timeout=45) as response, partial.open("xb") as output:
                total = 0
                while block := response.read(1024 * 1024):
                    total += len(block)
                    if total > asset["size"]:
                        raise ValueError("Downloaded asset exceeds the pinned size.")
                    output.write(block)
            partial.rename(destination)
        finally:
            partial.unlink(missing_ok=True)
    if destination.stat().st_size != asset["size"] or sha256(destination) != asset["sha256"]:
        raise ValueError("Source archive checksum or size differs from the lock.")
    return destination


def unpack(archive: Path, destination: Path) -> Path:
    destination.mkdir()
    total = 0
    with tarfile.open(archive) as source:
        members = source.getmembers()
        roots = {PurePosixPath(m.name).parts[0] for m in members if m.name}
        if len(roots) != 1:
            raise ValueError("The source archive must have exactly one root.")
        seen = set()
        for member in members:
            relative = PurePosixPath(member.name)
            if (relative.is_absolute() or ".." in relative.parts or "\\" in member.name
                    or not (member.isdir() or member.isfile()) or member.name in seen):
                raise ValueError("The source archive has unsafe or duplicate members.")
            seen.add(member.name)
            total += member.size
            if total > 256 * 1024 * 1024:
                raise ValueError("The source archive exceeds the expanded-size limit.")
            target = destination / relative
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with source.extractfile(member) as data, target.open("xb") as output:
                    shutil.copyfileobj(data, output)
                target.chmod(0o755 if member.mode & 0o111 else 0o644)
    return destination / roots.pop()


def audit_source(upstream: Path) -> dict:
    info = plistlib.loads((upstream / "AirportItlwm/WCL/Info.plist").read_bytes())
    controller = info["IOKitPersonalities"]["NetworkController"]
    matches = info["IOKitPersonalities"]["itlwm"]["IOPCIMatch"].lower().split()
    hal = (upstream / "itlwm/hal_iwm/mac80211.cpp").read_text()
    project = (upstream / "itlwm.xcodeproj/project.pbxproj").read_text()
    required = ["itlwm.xcodeproj/xcshareddata/xcschemes/AirportItlwm-Tahoe.xcscheme",
                "AirportItlwm/WCL/WCL.cpp", "AirportItlwm/WCL/WCL.hpp"]
    if not all((upstream / name).is_file() for name in required):
        raise ValueError("The pinned Tahoe scheme or native WCL sources are missing.")
    if ("0x9df08086" not in matches or controller.get("IONetworkRootType") != "airport"
            or "PCI_PRODUCT_INTEL_WL_9560_1    0x9df0" not in hal
            or 'sc->sc_fwname = "iwm-9000-46"' not in hal
            or '"__IO80211_TARGET=__MAC_26_0"' not in project
            or "AIRPORT_VTD" not in project):
        raise ValueError("The source does not match the reviewed AC9560 native Tahoe path.")
    firmware = upstream / "itlwm/firmware/iwm-9000-46"
    if sha256(firmware) != FIRMWARE_SHA:
        raise ValueError("The AC9560 firmware differs from the reviewed source.")
    for license_name in ("LICENSE", "iwlwifi-firmware-license"):
        if not (upstream / license_name).is_file():
            raise ValueError("A required upstream license is missing.")
    return {"pci_match": "8086:9df0", "firmware": "iwm-9000-46",
            "firmware_sha256": FIRMWARE_SHA, "native_stack": "Tahoe WCL / IO80211 / Skywalk",
            "source_modified": False}


def helper():
    spec = importlib.util.spec_from_file_location("stage_wifi_native", SOURCE / "tools/stage_wifi_native.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def hashes(directory: Path) -> dict:
    return {str(p.relative_to(directory)): sha256(p) for p in sorted(directory.rglob("*")) if p.is_file()}


def build(output: Path, audit_only: bool) -> None:
    output = output.resolve()
    # Work in a new folder: never rebuild over an old package or unrelated work.
    output.mkdir(parents=True, exist_ok=False)
    lock = json.loads(LOCK.read_text())
    assets = lock["assets"]
    cache = output / "archives"
    cache.mkdir()
    paths = {}
    for name in ("itlwm", "MacKernelSDK"):
        archive = fetch(assets[name], cache / f"{name}.tar.gz")
        paths[name] = unpack(archive, output / name)
    upstream = paths["itlwm"]
    record = {"schema": 1, "target": lock["target"], "assets": assets,
              "source_audit": audit_source(upstream), "laptop_validated": False,
              "build_status": "source_audited"}
    (output / "source-audit.json").write_text(json.dumps(record, indent=2) + "\n")
    if audit_only:
        print("PASS: pinned source, SDK archives, AC9560 PCI/firmware and Tahoe target audited. No compilation or device test.")
        return
    if platform.system() != "Darwin" or platform.machine() != "x86_64":
        raise ValueError("The full build requires Intel macOS with Xcode; use --audit-only elsewhere.")
    shutil.copytree(paths["MacKernelSDK"], upstream / "MacKernelSDK")
    products, objects = output / "products", output / "objects"
    command = ["xcodebuild", "-project", "itlwm.xcodeproj", "-scheme", "AirportItlwm-Tahoe",
               "-configuration", "Release", "-jobs", "3", "ARCHS=x86_64", "ONLY_ACTIVE_ARCH=NO",
               f"SYMROOT={products}", f"OBJROOT={objects}", "CODE_SIGNING_ALLOWED=NO",
               f"GIT_COMMIT=_{assets['itlwm']['commit'][:7]}", "build"]
    record["command"] = command
    record["xcode"] = subprocess.check_output(["xcodebuild", "-version"], text=True).strip()
    record["sdk"] = subprocess.check_output(["xcrun", "--sdk", "macosx", "--show-sdk-version"], text=True).strip()
    log = output / "AirportItlwm-Tahoe.log"
    with log.open("w") as stream:
        run = subprocess.run(command, cwd=upstream, stdout=stream, stderr=subprocess.STDOUT, timeout=1200)
    if run.returncode:
        print("\n".join(log.read_text(errors="replace").splitlines()[-70:]), file=sys.stderr)
        raise ValueError("Native Tahoe compilation failed; see AirportItlwm-Tahoe.log.")
    kext = products / "Release/Tahoe/AirportItlwm.kext"
    audited = helper().verify_kext(kext)
    subprocess.run(["/usr/bin/codesign", "--force", "--sign", "-", str(kext)], check=True, capture_output=True)
    subprocess.run(["/usr/bin/codesign", "--verify", "--strict", str(kext)], check=True, capture_output=True)
    audited = helper().verify_kext(kext)
    package = output / PACKAGE
    package.mkdir()
    shutil.copytree(kext, package / "payload/AirportItlwm.kext")
    shutil.copytree(SOURCE / "tools", package / "tools", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copy2(SOURCE / "README.md", package / "README.md")
    shutil.copy2(LOCK, package / "sources.lock.json")
    licenses = package / "licenses"
    licenses.mkdir()
    for name in ("LICENSE", "iwlwifi-firmware-license"):
        shutil.copy2(upstream / name, licenses / name)
    # Include the exact validator for the project's OpenCore, not a different bootloader.
    opencore = fetch(assets["OpenCore"], cache / "OpenCore.zip")
    with zipfile.ZipFile(opencore) as archive:
        (package / "tools/ocvalidate").write_bytes(archive.read("Utilities/ocvalidate/ocvalidate"))
    shutil.copy2(ROOT / "licenses/efi/OpenCore-LICENSE.txt", licenses / "OpenCore-LICENSE.txt")
    (package / "tools/ocvalidate").chmod(0o755)
    corresponding = package / "source"
    corresponding.mkdir()
    for name in ("itlwm", "MacKernelSDK"):
        shutil.copy2(cache / f"{name}.tar.gz", corresponding / f"{name}.tar.gz")
    shutil.copy2(Path(__file__), corresponding / "build_wifi_native.py")
    record.update({"package": PACKAGE, "build_status": "compiled_and_verified", "kext": audited,
                   "signature": "ad-hoc, verified with codesign --verify --strict",
                   "system_patches": False, "live_efi_modified": False, "files": hashes(package)})
    (package / "manifest.json").write_text(json.dumps(record, indent=2) + "\n")
    helper().verify_package(package)
    # Validate the intended two-entry change using the repository's sanitized EFI profile.
    config = plistlib.loads((ROOT / "config/efi/current/config.plist").read_bytes())
    trial = output / "native-trial-config.plist"
    trial.write_bytes(plistlib.dumps(helper().native_config(config), sort_keys=False))
    helper().validate(package / "tools/ocvalidate", trial)
    archive_path = output / f"{PACKAGE}.zip"
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(package.rglob("*")):
            if path.is_file():
                archive.write(path, str(path.relative_to(output)))
    (output / "package-result.json").write_text(json.dumps({
        "package": PACKAGE, "sha256": sha256(archive_path), "size": archive_path.stat().st_size,
        "files": len(record["files"]) + 1, "build_status": record["build_status"],
        "laptop_validated": False,
    }, indent=2) + "\n")
    print(f"PASS: {PACKAGE} compiled, linked, signed, checksummed and packaged. Laptop validation pending.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True, help="New build directory")
    parser.add_argument("--audit-only", action="store_true", help="Inspect exact sources without compiling")
    args = parser.parse_args()
    try:
        build(args.output_dir, args.audit_only)
    except (ValueError, OSError, KeyError, subprocess.SubprocessError) as error:
        parser.exit(1, f"Wi-Fi build failed: {error}\n")


if __name__ == "__main__":
    main()
