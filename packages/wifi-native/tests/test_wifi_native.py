#!/usr/bin/env python3
"""Exercise offline EFI isolation with a real ocvalidate and synthetic driver fixtures."""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import plistlib
import shutil
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "packages/wifi-native/tools"
VALIDATOR = None


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, TOOLS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


stage = load("stage_wifi_native")
collector = load("collect_wifi_native")


def tree_hashes(directory: Path) -> dict:
    return {str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in directory.rglob("*") if p.is_file()}


class OfflineTrial(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.original = self.root / "original/EFI"
        self.original.mkdir(parents=True)
        self.output = self.root / "trial/EFI"
        self.package = self.root / "package"
        self.config = plistlib.loads((ROOT / "config/efi/current/config.plist").read_bytes())
        for name, raw in {
            "OC/config.plist": plistlib.dumps(self.config), "OC/OpenCore.efi": b"boot fixture",
            "BOOT/BOOTx64.efi": b"boot fixture", "OC/Kexts/itlwm.kext/Contents/Info.plist":
            plistlib.dumps({"WiFiConfig": {"private-network": {"password": "private-password"}}}),
            "OC/ACPI/existing.aml": b"preserved ACPI fixture",
            "OC/Kexts/S540NvidiaProbe.kext/Contents/Info.plist": b"preserved NVIDIA fixture",
        }.items():
            path = self.original / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        kext = self.package / "payload/AirportItlwm.kext"
        (kext / "Contents/MacOS").mkdir(parents=True)
        (kext / "Contents/Info.plist").write_bytes(plistlib.dumps({
            "CFBundleIdentifier": stage.IDENTIFIER, "CFBundleVersion": "2.4.0",
            "CFBundleExecutable": "AirportItlwm", "CFBundlePackageType": "KEXT",
            "OSBundleLibraries": {"com.apple.iokit.IO80211Family": "1.5.0",
                                  "com.apple.iokit.IOSkywalkFamily": "1.0"},
            "IOKitPersonalities": {"itlwm": {"IOPCIMatch": "0x9df08086"},
                                   "NetworkController": {"IONetworkRootType": "airport"}},
        }))
        # This header is a test fixture only, never a real driver or deliverable.
        (kext / "Contents/MacOS/AirportItlwm").write_bytes(
            struct.pack("<8I", 0xfeedfacf, 0x01000007, 3, 11, 0, 0, 0, 0))
        (self.package / "tools").mkdir()
        shutil.copy2(VALIDATOR, self.package / "tools/ocvalidate")
        (self.package / "tools/ocvalidate").chmod(0o755)
        self.rehash()

    def rehash(self):
        files = tree_hashes(self.package)
        files.pop("manifest.json", None)
        (self.package / "manifest.json").write_text(json.dumps({
            "schema": 1, "package": stage.PACKAGE, "build_status": "compiled_and_verified",
            "laptop_validated": False, "files": files,
        }))

    def test_config_preserves_every_other_setting(self):
        previous = copy.deepcopy(self.config)
        native = stage.native_config(self.config)
        self.assertEqual(self.config, previous)
        extra = native["Kernel"]["Add"].pop()
        self.assertEqual(extra["MinKernel"], "25.0.0")
        self.assertEqual(extra["MaxKernel"], "25.99.99")
        self.assertEqual(extra["BundlePath"], "AirportItlwm.kext")
        next(e for e in native["Kernel"]["Add"] if e["BundlePath"] == "itlwm.kext")["Enabled"] = True
        self.assertEqual(native, previous)

    def test_complete_copy_retains_private_data_and_nvidia(self):
        original = tree_hashes(self.original)
        stage.stage(self.original, self.output, self.package)
        self.assertEqual(tree_hashes(self.original), original)
        for name, expected in original.items():
            if name != "OC/config.plist":
                self.assertEqual(stage.digest(self.output / name), expected)
        native = plistlib.loads((self.output / "OC/config.plist").read_bytes())
        self.assertFalse(next(e for e in native["Kernel"]["Add"] if e["BundlePath"] == "itlwm.kext")["Enabled"])
        self.assertTrue((self.output / "OC/Kexts/AirportItlwm.kext").is_dir())

    def test_legacy_and_duplicate_driver_conflicts_are_rejected(self):
        for extra in (
            {"BundlePath": "AirportItlwm.kext", "Enabled": False},
            {"BundlePath": "itlwm.kext", "Enabled": True},
            {"BundlePath": "IO80211FamilyLegacy.kext", "Enabled": True},
            {"BundlePath": "IOSkywalkFamily.kext", "Enabled": True},
        ):
            with self.subTest(extra=extra):
                config = copy.deepcopy(self.config)
                config["Kernel"]["Add"].append(extra)
                with self.assertRaises(ValueError):
                    stage.native_config(config)
        config = copy.deepcopy(self.config)
        config["Kernel"]["Block"].append({"Identifier": "com.apple.iokit.IOSkywalkFamily", "Enabled": True})
        with self.assertRaises(ValueError):
            stage.native_config(config)

    def test_missing_or_disabled_itlwm_is_rejected(self):
        for remove in (True, False):
            config = copy.deepcopy(self.config)
            entries = config["Kernel"]["Add"]
            driver = next(e for e in entries if e["BundlePath"] == "itlwm.kext")
            if remove:
                entries.remove(driver)
            else:
                driver["Enabled"] = False
            with self.assertRaises(ValueError):
                stage.native_config(config)

    def test_bad_configuration_fails_real_ocvalidate_without_output(self):
        self.config["Kernel"]["Add"].append(copy.deepcopy(self.config["Kernel"]["Add"][0]))
        (self.original / "OC/config.plist").write_bytes(plistlib.dumps(self.config))
        original = tree_hashes(self.original)
        with self.assertRaisesRegex(ValueError, "ocvalidate"):
            stage.stage(self.original, self.output, self.package)
        self.assertFalse(self.output.exists())
        self.assertEqual(tree_hashes(self.original), original)

    def test_checksum_and_unlisted_payload_fail_before_staging(self):
        binary = self.package / "payload/AirportItlwm.kext/Contents/MacOS/AirportItlwm"
        raw = binary.read_bytes()
        binary.write_bytes(raw + b"changed")
        with self.assertRaises(ValueError):
            stage.stage(self.original, self.output, self.package)
        binary.write_bytes(raw)
        (binary.parent / "unlisted").write_bytes(b"extra payload")
        with self.assertRaises(ValueError):
            stage.stage(self.original, self.output, self.package)
        self.assertFalse(self.output.exists())

    def test_live_existing_nested_and_symlink_paths_are_rejected(self):
        for target in (self.original, self.original / "nested", self.root,
                       Path("/Volumes/S540-WIFI-TEST/EFI"), self.package / "new"):
            with self.subTest(target=target), self.assertRaises(ValueError):
                stage.stage(self.original, target, self.package)
        (self.original / "link").symlink_to(self.original / "OC/OpenCore.efi")
        with self.assertRaises(ValueError):
            stage.stage(self.original, self.output, self.package)


class FilteredReport(unittest.TestCase):
    def test_native_path_does_not_export_network_identifiers(self):
        def run(args):
            if args[0].endswith("sw_vers"):
                return "26.0\n", True
            if args[0].endswith("kextstat"):
                return "com.zxystd.AirportItlwm (2.4.0)\n", True
            if "-listallhardwareports" in args:
                return "Hardware Port: Wi-Fi\nDevice: en1\nEthernet Address: aa:bb:cc:dd:ee:ff\n\n", True
            if "-getairportpower" in args:
                return "Wi-Fi Power (en1): On\n", True
            if args[0].endswith("ifconfig"):
                return "inet 192.168.1.23\nether aa:bb:cc:dd:ee:ff\n\tstatus: active\n", True
            return "interface: en1\ngateway: 192.168.1.1\n", True
        with patch.object(collector, "command", side_effect=run):
            report = collector.collect()
        self.assertTrue(report["native_interface_detected"])
        self.assertTrue(report["airportitlwm_loaded"])
        self.assertFalse(report["itlwm_loaded"])
        self.assertEqual(report["native_wifi_interfaces"], [{
            "device": "en1", "power_on": True, "link_active": True, "default_route": True}])
        self.assertNotIn("aa:bb", json.dumps(report))
        self.assertNotIn("192.168", json.dumps(report))

    def test_collection_failure_remains_unknown(self):
        with patch.object(collector, "command", return_value=("", False)):
            report = collector.collect()
        self.assertIsNone(report["native_interface_detected"])
        self.assertIsNone(report["airportitlwm_loaded"])
        self.assertIsNone(report["conflicting_intel_drivers"])
        self.assertEqual(len(report["collection_errors"]), 4)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ocvalidate", required=True, type=Path)
    args, remaining = parser.parse_known_args()
    VALIDATOR = args.ocvalidate.resolve()
    if not VALIDATOR.is_file():
        parser.error("The real OpenCore 1.0.8 validator is required.")
    unittest.main(argv=[sys.argv[0], *remaining])
