#!/usr/bin/env python3
"""Exercise the native EFI stager in private filesystem fixtures on macOS."""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import plistlib
import stat
import subprocess
import tempfile

GUID = "7C436110-AB2A-4BBB-A880-FE41995C9F82"


def base_config() -> dict:
    return {
        "ACPI": {"Add": [{"Enabled": True, "Path": "SSDT-PLUG.aml"}]},
        "DeviceProperties": {"Add": {"PciRoot(0x0)/Pci(0x2,0x0)": {"framebuffer-patch-enable": b"\x01\x00\x00\x00"}}},
        "NVRAM": {
            "Add": {GUID: {"boot-args": "-v\t-wegnoegpu  -igfxblr foo-wegnoegpu=1", "csr-active-config": b"\x03\x00\x00\x00"}},
            "Delete": {GUID: ["boot-args", "csr-active-config"]},
            "WriteFlash": True,
            "LegacyOverwrite": False,
        },
        "PlatformInfo": {"Generic": {"SystemProductName": "FixtureModel"}},
    }


def fingerprint(directory: Path) -> dict[str, str]:
    return {str(item.relative_to(directory)): hashlib.sha256(item.read_bytes()).hexdigest()
            for item in directory.rglob("*") if item.is_file() and not item.is_symlink()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tool", required=True, type=Path)
    args = parser.parse_args()
    tool = args.tool.resolve(strict=True)
    subprocess.run([str(tool), "--self-test"], check=True, timeout=20)
    with tempfile.TemporaryDirectory(prefix="nvidia-visibility-fixtures-") as temporary:
        # Darwin /var may be a link to /private/var. Use the real fixture path.
        root = Path(temporary).resolve()
        source = root / "mounted EFI" / "EFI"
        output_parent = root / "Desktop"
        output_parent.mkdir()
        for directory in ("BOOT", "OC", "OC/ACPI", "OC/Kexts/Fixture.kext/Contents", "Microsoft"):
            (source / directory).mkdir(parents=True, exist_ok=True)
        (source / "BOOT/BOOTx64.efi").write_bytes(b"Fixture boot image\n")
        (source / "OC/OpenCore.efi").write_bytes(b"Fixture OpenCore image\n")
        (source / "OC/ACPI/SSDT-PLUG.aml").write_bytes(b"Fixture table\n")
        (source / "OC/Kexts/Fixture.kext/Contents/Info.plist").write_bytes(plistlib.dumps({"Enabled": True}))
        (source / "Microsoft/keep.efi").write_bytes(b"Unrelated source EFI\n")
        config = source / "OC/config.plist"
        config.write_bytes(plistlib.dumps(base_config()))
        validator = root / "fixture-validator"
        validator.write_text("#!/bin/sh\n[ \"$#\" -eq 1 ] && [ -r \"$1\" ] || exit 2\nprintf 'Fixture validation passed.\\n'\n", encoding="utf-8")
        validator.chmod(0o700)
        initial = fingerprint(source)

        def run(expected: int = 0, source_path: Path = source, parent_path: Path = output_parent) -> subprocess.CompletedProcess:
            result = subprocess.run([str(tool), str(source_path), str(parent_path), str(validator)],
                                    capture_output=True, text=True, timeout=30)
            if result.returncode != expected:
                raise AssertionError(f"Unexpected stager status {result.returncode}: {result.stdout}\n{result.stderr}")
            return result

        run()
        outputs = list(output_parent.glob("NVIDIA-VISIBILITY.*"))
        assert len(outputs) == 1
        output = outputs[0]
        candidate = output / "EFI"
        assert fingerprint(source) == initial
        assert not (candidate / "Microsoft").exists()
        assert (output / "original-config.plist").read_bytes() == config.read_bytes()
        assert (output / "source-before.sha256").read_bytes() == (output / "source-after.sha256").read_bytes()
        expected = base_config()
        expected["NVRAM"]["Add"][GUID]["boot-args"] = "-v\t  -igfxblr foo-wegnoegpu=1"
        assert plistlib.loads((candidate / "OC/config.plist").read_bytes()) == expected
        copied = fingerprint(candidate)
        assert set(copied) == {name for name in initial if name.startswith(("BOOT/", "OC/"))}
        for name, digest in copied.items():
            if name != "OC/config.plist":
                assert initial[name] == digest
        assert (output / "READY.txt").is_file()
        assert not (output / "FAILED.txt").exists()
        assert "Fixture validation passed." in (output / "baseline-ocvalidate.txt").read_text()
        assert "Fixture validation passed." in (output / "candidate-ocvalidate.txt").read_text()
        for item in (output, *output.rglob("*")):
            assert stat.S_IMODE(item.stat().st_mode) & 0o077 == 0

        # The real program rejects risky source shapes before creating a new output.
        old_count = len(list(output_parent.iterdir()))
        link = source / "OC/linked.efi"
        link.symlink_to(source / "BOOT/BOOTx64.efi")
        assert "Symbolic links" in run(1).stderr
        link.unlink()
        os.link(source / "BOOT/BOOTx64.efi", link)
        assert "Hard-linked" in run(1).stderr
        link.unlink()
        assert len(list(output_parent.iterdir())) == old_count
        assert "must not overlap" in run(1, parent_path=source).stderr

        original_config = config.read_bytes()
        for mutation in ("missing-delete", "missing-panel", "prefix-only", "mixed-disable", "flash-off", "legacy-on", "numeric-flash"):
            changed = base_config()
            if mutation == "missing-delete":
                changed["NVRAM"]["Delete"][GUID] = ["csr-active-config"]
            elif mutation == "missing-panel":
                changed["NVRAM"]["Add"][GUID]["boot-args"] = "-wegnoegpu -v"
            elif mutation == "prefix-only":
                changed["NVRAM"]["Add"][GUID]["boot-args"] = "-wegnoegpu=1 -igfxblr"
            elif mutation == "mixed-disable":
                changed["NVRAM"]["Add"][GUID]["boot-args"] = "-wegnoegpu -igfxblr -wegnoegpu=1"
            elif mutation == "flash-off":
                changed["NVRAM"]["WriteFlash"] = False
            elif mutation == "legacy-on":
                changed["NVRAM"]["LegacyOverwrite"] = True
            else:
                changed["NVRAM"]["WriteFlash"] = 1
            config.write_bytes(plistlib.dumps(changed))
            run(1)
            assert len(list(output_parent.iterdir())) == old_count
        config.write_bytes(original_config)

        # A validator failure retains private diagnostics but never a READY marker.
        validator.write_text("#!/bin/sh\nprintf 'Fixture validation rejected.\\n'\nexit 1\n", encoding="utf-8")
        assert "validation failed" in run(1).stderr
        failed = [path for path in output_parent.iterdir() if path != output]
        assert len(failed) == 1
        assert (failed[0] / "FAILED.txt").is_file()
        assert not (failed[0] / "READY.txt").exists()
        assert fingerprint(source) == initial

        # The stager executes only the supplied validator. Its output is a private
        # prepared copy; it never needs diskutil, nvram, sudo or a kernel interface.
        print("Native NVIDIA visibility filesystem fixtures passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
