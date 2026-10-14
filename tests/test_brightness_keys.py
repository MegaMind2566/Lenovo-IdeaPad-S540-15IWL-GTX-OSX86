#!/usr/bin/env python3
"""Native CI fixtures for a reversible BrightnessKeys-only EFI change.

Run on the Intel macOS Actions runner, after constructing both packages:
python3 tests/test_brightness_keys.py BUILT_BRIGHTNESS_PACKAGE CURRENT_EFI_DIRECTORY

All fixture copies and every mutation are confined to RUNNER_TEMP. The private
helper copy replaces only the hardware/session guard; production file, payload,
config, ocvalidate, journal, and restore checks run unchanged. No driver is loaded
and no live EFI, NVRAM, SIP, or system volume is accessed for mutation.
"""
from __future__ import annotations

import copy
import hashlib
import os
from pathlib import Path
import plistlib
import re
import shutil
import struct
import subprocess
import sys
import tempfile


BUNDLE = "BrightnessKeys.kext"
HELPER = "tools/brightness_keys_test.sh"
BACKUP = "EFI/OC/backup-function-keys"


def fingerprint(root: Path) -> dict[str, str]:
    """Capture every regular file and symlink without following symlinks."""
    result = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            result[relative] = "symlink:" + os.readlink(path)
        elif path.is_file():
            result[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def private_guard_copy(source: Path, destination: Path) -> None:
    text = source.read_text(encoding="utf-8")
    pattern = re.compile(r"(?ms)^runtime_guard\(\) \{\n.*?^\}\n")
    matches = list(pattern.finditer(text))
    assert len(matches) == 1, "Expected one dedicated runtime hardware guard."
    guard = matches[0]
    # The native runner is Intel but has Darwin 24, rather than the laptop's
    # Darwin 25.6. No file/payload/config checks are bypassed by this replacement.
    replacement = "runtime_guard() {\n    :\n}\n"
    modified = text[:guard.start()] + replacement + text[guard.end():]
    assert modified[:guard.start()] == text[:guard.start()]
    assert modified[guard.start() + len(replacement):] == text[guard.end():]
    destination.write_text(modified, encoding="utf-8")
    destination.chmod(0o700)


def write_config(path: Path, value: dict) -> None:
    path.write_bytes(plistlib.dumps(value, sort_keys=False))


def apple_double(*, out_of_bounds: bool = False) -> bytes:
    """A bounded FinderInfo/resource-fork table in the native AppleDouble format."""
    header = struct.pack(">II16sH", 0x00051607, 0x00020000, b"\0" * 16, 2)
    finder = struct.pack(">III", 9, 50, 33 if out_of_bounds else 32)
    resource = struct.pack(">III", 2, 82, 0)
    return header + finder + resource + b"\0" * 32


def finder_store() -> bytes:
    """The signature/length recognized by the helper; never executable payload."""
    return b"\x00\x00\x00\x01Bud1" + b"\0" * 24


def main() -> int:
    if (
        os.environ.get("GITHUB_ACTIONS") != "true"
        or sys.platform != "darwin"
        or os.uname().machine != "x86_64"
    ):
        raise SystemExit("Run these fixtures on the Intel macOS Actions runner.")
    if len(sys.argv) != 3:
        raise SystemExit("Usage: test_brightness_keys.py BUILT_PACKAGE CURRENT_EFI_DIRECTORY")
    runner_temp = Path(os.environ["RUNNER_TEMP"]).resolve(strict=True)
    package = Path(sys.argv[1]).resolve(strict=True)
    reference = Path(sys.argv[2]).resolve(strict=True)
    assert (reference / "OC/config.plist").is_file()
    assert (reference / "OC/OpenCore.efi").is_file()
    assert (reference / "BOOT/BOOTx64.efi").is_file()
    assert (package / HELPER).is_file()
    assert (package / "payload" / BUNDLE / "Contents/Info.plist").is_file()
    assert (package / "payload/manifest.plist").is_file()
    assert (package / "bin/ocvalidate").is_file()
    for source in (package, reference):
        assert not any(path.is_symlink() for path in (source, *source.rglob("*")))
    with (package / "payload" / BUNDLE / "Contents/Info.plist").open("rb") as stream:
        info = plistlib.load(stream)
    assert info["CFBundleIdentifier"] == "as.acidanthera.BrightnessKeys"
    assert info["CFBundleVersion"] == "1.0.3"
    source_payload = fingerprint(package / "payload" / BUNDLE)
    assert source_payload
    baseline = plistlib.loads((reference / "OC/config.plist").read_bytes())
    assert isinstance(baseline["Kernel"]["Add"], list)
    assert not any(entry.get("BundlePath") == BUNDLE for entry in baseline["Kernel"]["Add"])
    assert not (reference / "OC/Kexts" / BUNDLE).exists()

    with tempfile.TemporaryDirectory(prefix="s540-brightness-fixtures-", dir=runner_temp) as name:
        fixture_root = Path(name).resolve(strict=True)
        assert fixture_root.parent == runner_temp
        fixture_root.chmod(0o700)
        sentinel = fixture_root / "outside-boot-sentinel.txt"
        sentinel.write_bytes(b"This file is outside every fixture boot volume.\n")
        sentinel_hash = hashlib.sha256(sentinel.read_bytes()).hexdigest()
        count = 0

        def make_case(label: str) -> dict[str, Path]:
            base = fixture_root / label
            base.mkdir(mode=0o700)
            boot = base / "Boot HDD"
            boot.mkdir(mode=0o700)
            shutil.copytree(reference, boot / "EFI")
            private_package = base / "package"
            shutil.copytree(package, private_package)
            private_guard_copy(package / HELPER, private_package / HELPER)
            temporary = base / "temporary"
            temporary.mkdir(mode=0o700)
            case = {"base": base, "boot": boot, "package": private_package,
                    "helper": private_package / HELPER,
                    "config": boot / "EFI/OC/config.plist",
                    "bundle": boot / "EFI/OC/Kexts" / BUNDLE,
                    "backup": boot / BACKUP, "temp": temporary}
            assert all(path == fixture_root or fixture_root in path.parents for path in case.values())
            return case

        def run(case: dict[str, Path], mode: str, succeeds: bool = True) -> subprocess.CompletedProcess:
            nonlocal count
            count += 1
            assert fixture_root in case["boot"].resolve(strict=True).parents
            environment = dict(os.environ, TMPDIR=str(case["temp"]) + "/")
            result = subprocess.run(
                ["/bin/bash", str(case["helper"]), mode, str(case["boot"])],
                capture_output=True, text=True, timeout=75, env=environment,
            )
            assert (result.returncode == 0) == succeeds, (
                f"{case['base'].name}/{mode}: unexpected status {result.returncode}\n"
                f"{result.stdout}\n{result.stderr}"
            )
            assert hashlib.sha256(sentinel.read_bytes()).hexdigest() == sentinel_hash
            assert fingerprint(package / "payload" / BUNDLE) == source_payload
            return result

        def assert_refused(case: dict[str, Path], mode: str = "test") -> None:
            before = fingerprint(case["boot"])
            run(case, mode, succeeds=False)
            assert fingerprint(case["boot"]) == before, (
                f"{case['base'].name}: refused operation changed EFI files"
            )

        # The unmodified production runtime guard must reject the generic CI
        # machine before making any EFI change. It does not have the laptop's
        # loaded Intel graphics/Lilu/WhateverGreen runtime.
        case = make_case("production-runtime-guard")
        shutil.copyfile(package / HELPER, case["helper"])
        assert_refused(case)

        # Exercise the normal user CLI, a real ocvalidate binary, and the exact
        # public EFI. Only one appended kext entry may change config semantics.
        case = make_case("normal-install-and-restore")
        original_bytes = case["config"].read_bytes()
        original_tree = fingerprint(case["boot"] / "EFI")
        run(case, "test")
        changed = plistlib.loads(case["config"].read_bytes())
        old_entries = baseline["Kernel"]["Add"]
        new_entries = changed["Kernel"]["Add"]
        assert new_entries[:-1] == old_entries and len(new_entries) == len(old_entries) + 1
        entry = new_entries[-1]
        assert entry["BundlePath"] == BUNDLE
        assert entry["ExecutablePath"] == "Contents/MacOS/BrightnessKeys"
        assert entry["PlistPath"] == "Contents/Info.plist"
        assert entry["Enabled"] is True and entry["Arch"] == "Any"
        assert entry["MinKernel"] == "25.0.0" and entry["MaxKernel"] == "25.99.99"
        assert isinstance(entry["Comment"], str)
        expected = copy.deepcopy(baseline)
        expected["Kernel"]["Add"].append(entry)
        assert changed == expected, "Only one Kernel.Add entry may change config semantics."
        assert fingerprint(case["bundle"]) == source_payload
        assert (case["backup"] / "before.plist").read_bytes() == original_bytes
        after_apply = fingerprint(case["boot"] / "EFI")
        for relative, digest in original_tree.items():
            if relative != "OC/config.plist":
                assert after_apply.get(relative) == digest, f"Existing EFI file changed: {relative}"
        run(case, "test")
        assert fingerprint(case["boot"] / "EFI") == after_apply, "Repeat application must be idempotent."
        run(case, "restore")
        assert case["config"].read_bytes() == original_bytes, "Restore must preserve original config bytes."
        assert not case["bundle"].exists()
        restored_tree = fingerprint(case["boot"] / "EFI")
        assert all(restored_tree.get(relative) == digest for relative, digest in original_tree.items())
        assert (case["backup"] / "before.plist").read_bytes() == original_bytes
        run(case, "restore")
        assert case["config"].read_bytes() == original_bytes and not case["bundle"].exists()

        def set_phase(case: dict[str, Path], phase: str, draft: bool = False) -> None:
            path = case["backup"] / "state.plist"
            state = plistlib.loads(path.read_bytes())
            state["Phase"] = phase
            write_config(case["backup"] / ("state-next.plist" if draft else "state.plist"), state)

        def prepared_case(label: str) -> tuple[dict[str, Path], bytes, bytes]:
            """Retain an authentic version-one journal at its first checkpoint."""
            case = make_case(label)
            run(case, "test")
            original_bytes = (case["backup"] / "before.plist").read_bytes()
            tested_bytes = (case["backup"] / "tested.plist").read_bytes()
            state = plistlib.loads((case["backup"] / "state.plist").read_bytes())
            assert state["Format"] == 1
            assert state["Owner"] == "s540-brightness-keys-v1"
            case["config"].write_bytes(original_bytes)
            set_phase(case, "prepared")
            shutil.rmtree(case["bundle"])
            return case, original_bytes, tested_bytes

        # The original helper could create this prepared journal and then stop
        # on macOS metadata written to a FAT boot disk. Reuse the old journal;
        # do not remove metadata or weaken snapshot/manifest checks to resume.
        case, original_bytes, tested_bytes = prepared_case("version-one-prepared-metadata")
        metadata = {}
        for name in ("before.plist", "tested.plist", "manifest.plist", "state.plist"):
            sidecar = case["backup"] / ("._" + name)
            sidecar.write_bytes(apple_double())
            metadata[sidecar] = sidecar.read_bytes()
        store = case["backup"] / ".DS_Store"
        store.write_bytes(finder_store())
        metadata[store] = store.read_bytes()
        run(case, "test")
        assert case["config"].read_bytes() == tested_bytes
        changed = plistlib.loads(tested_bytes)
        expected = copy.deepcopy(baseline)
        expected["Kernel"]["Add"].append(changed["Kernel"]["Add"][-1])
        assert changed == expected, "Metadata recovery must still append only one driver entry."
        assert fingerprint(case["bundle"]) == source_payload
        assert all(path.read_bytes() == contents for path, contents in metadata.items())
        run(case, "restore")
        assert case["config"].read_bytes() == original_bytes and not case["bundle"].exists()
        assert all(path.read_bytes() == contents for path, contents in metadata.items())

        # Matching an AppleDouble prefix alone cannot authorize a malformed
        # table, a foreign backup entry, an orphan sidecar, or any symlink.
        for label, kind in (
            ("malformed-backup-metadata", "malformed"),
            ("short-backup-finder-store", "short-store"),
            ("invalid-backup-finder-store", "invalid-store"),
            ("foreign-backup-file", "foreign"),
            ("orphan-backup-metadata", "orphan"),
            ("symlink-backup-metadata", "symlink"),
        ):
            case, original_bytes, _ = prepared_case(label)
            if kind == "malformed":
                (case["backup"] / "._before.plist").write_bytes(apple_double(out_of_bounds=True))
            elif kind == "short-store":
                (case["backup"] / ".DS_Store").write_bytes(finder_store()[:-1])
            elif kind == "invalid-store":
                (case["backup"] / ".DS_Store").write_bytes(b"NotBud1!" + b"\0" * 24)
            elif kind == "foreign":
                (case["backup"] / "untracked-notes.txt").write_bytes(b"Not owned by this operation.\n")
            elif kind == "orphan":
                # state-next is a recognized optional filename, but the actual
                # journal draft is absent. Its metadata must not be adopted.
                (case["backup"] / "._state-next.plist").write_bytes(apple_double())
            else:
                sidecar_target = case["base"] / "outside-backup-appledouble"
                sidecar_target.write_bytes(apple_double())
                (case["backup"] / "._before.plist").symlink_to(sidecar_target)
                target_before = sidecar_target.read_bytes()
            assert_refused(case)
            assert_refused(case, "restore")
            assert case["config"].read_bytes() == original_bytes and not case["bundle"].exists()
            if kind == "symlink":
                assert sidecar_target.read_bytes() == target_before

        # Finder can add metadata to an extracted bundle, an active bundle, or
        # the removed driver. Only explicitly paired, validated sidecars may be
        # omitted from the logical file list; real payload hashes stay locked.
        case = make_case("paired-bundle-metadata")
        payload = case["package"] / "payload" / BUNDLE
        payload_metadata = {}
        for relative in (
            ".DS_Store", "._Contents", "Contents/.DS_Store", "Contents/._Info.plist",
            "Contents/._MacOS", "Contents/MacOS/.DS_Store", "Contents/MacOS/._BrightnessKeys",
        ):
            path = payload / relative
            path.write_bytes(finder_store() if path.name == ".DS_Store" else apple_double())
            payload_metadata[relative] = path.read_bytes()
        private_payload_before = fingerprint(payload)
        run(case, "test")
        # ditto may suppress rather than copy AppleDouble metadata. Either way,
        # every locked real file must remain byte exact, and source metadata may
        # never be rewritten as part of validation or staging.
        logical_payload = {key: digest for key, digest in fingerprint(case["bundle"]).items()
                           if key not in payload_metadata}
        assert logical_payload == source_payload
        assert fingerprint(payload) == private_payload_before
        active_metadata = {}
        for relative, contents in payload_metadata.items():
            path = case["bundle"] / relative
            path.write_bytes(contents)
            active_metadata[relative] = contents
        active_before = fingerprint(case["bundle"])
        original_bytes = (case["backup"] / "before.plist").read_bytes()
        run(case, "test")
        assert fingerprint(case["bundle"]) == active_before
        run(case, "restore")
        removed = case["backup"] / "removed-BrightnessKeys.kext"
        assert fingerprint(removed) == active_before
        assert case["config"].read_bytes() == original_bytes and not case["bundle"].exists()
        assert fingerprint(payload) == private_payload_before
        assert all((removed / relative).read_bytes() == contents
                   for relative, contents in active_metadata.items())

        for label, relative, contents in (
            ("malformed-bundle-metadata", "Contents/._Info.plist", apple_double(out_of_bounds=True)),
            ("orphan-bundle-metadata", "Contents/MacOS/._untracked-driver", apple_double()),
        ):
            case = make_case(label)
            (case["package"] / "payload" / BUNDLE / relative).write_bytes(contents)
            assert_refused(case)

        # File-content backup must not transfer quarantine or other extended
        # attributes into a FAT backup. cp -X also keeps the replacement config
        # and generated candidate free of attributes inherited from snapshots.
        case = make_case("data-only-backup-copies")
        xattr = "/usr/bin/xattr"
        for path in (case["config"], case["package"] / "payload/manifest.plist"):
            subprocess.run([xattr, "-w", "com.apple.quarantine", "0081;00000000;S540 fixture;", str(path)],
                           check=True, capture_output=True, text=True)
            subprocess.run([xattr, "-w", "org.s540.fixture", "must stay on source only", str(path)],
                           check=True, capture_output=True, text=True)
        manifest_attrs = subprocess.check_output(
            [xattr, str(case["package"] / "payload/manifest.plist")], text=True)
        assert "com.apple.quarantine" in manifest_attrs and "org.s540.fixture" in manifest_attrs
        run(case, "test")
        for path in (case["backup"] / "before.plist", case["backup"] / "tested.plist",
                     case["backup"] / "manifest.plist", case["config"]):
            attributes = subprocess.check_output([xattr, str(path)], text=True)
            assert attributes.strip() == "", f"Copied file retained unexpected attributes: {path.name}"
        assert subprocess.check_output(
            [xattr, str(case["package"] / "payload/manifest.plist")], text=True) == manifest_attrs
        run(case, "restore")
        assert subprocess.check_output([xattr, str(case["config"])], text=True).strip() == ""

        # Use genuine production-created snapshots and journals, then emulate
        # each durable filesystem checkpoint. Resume must recognize only the
        # exact known payload and original/tested configuration bytes.
        for label, phase, placement in (
            ("resume-prepared", "prepared", "absent"),
            ("resume-staged", "staged", "stage"),
            ("resume-copied", "copied", "active"),
        ):
            case = make_case(label)
            run(case, "test")
            original_bytes = (case["backup"] / "before.plist").read_bytes()
            tested_bytes = (case["backup"] / "tested.plist").read_bytes()
            case["config"].write_bytes(original_bytes)
            set_phase(case, phase)
            if placement == "absent":
                shutil.rmtree(case["bundle"])
            elif placement == "stage":
                case["bundle"].rename(case["bundle"].parent / ".BrightnessKeys-s540-stage.kext")
            run(case, "test")
            assert case["config"].read_bytes() == tested_bytes
            assert fingerprint(case["bundle"]) == source_payload
            assert not (case["bundle"].parent / ".BrightnessKeys-s540-stage.kext").exists()
            assert plistlib.loads((case["backup"] / "state.plist").read_bytes())["Phase"] == "installed"
            run(case, "restore")
            assert case["config"].read_bytes() == original_bytes and not case["bundle"].exists()

        for label, removed in (("restore-after-config-replacement", False),
                               ("restore-after-driver-move", True)):
            case = make_case(label)
            run(case, "test")
            original_bytes = (case["backup"] / "before.plist").read_bytes()
            case["config"].write_bytes(original_bytes)
            set_phase(case, "restoring")
            if removed:
                case["bundle"].rename(case["backup"] / "removed-BrightnessKeys.kext")
            run(case, "restore")
            assert case["config"].read_bytes() == original_bytes and not case["bundle"].exists()
            assert fingerprint(case["backup"] / "removed-BrightnessKeys.kext") == source_payload
            assert plistlib.loads((case["backup"] / "state.plist").read_bytes())["Phase"] == "restored"

        case = make_case("phase-only-journal-draft")
        run(case, "test")
        tested_bytes = case["config"].read_bytes()
        set_phase(case, "copied", draft=True)
        run(case, "test")
        assert case["config"].read_bytes() == tested_bytes
        assert not (case["backup"] / "state-next.plist").exists()
        assert fingerprint(case["bundle"]) == source_payload

        case = make_case("foreign-journal-draft")
        run(case, "test")
        set_phase(case, "copied", draft=True)
        path = case["backup"] / "state-next.plist"
        state = plistlib.loads(path.read_bytes())
        state["Owner"] = "foreign-operation"
        write_config(path, state)
        assert_refused(case)

        case = make_case("unknown-interrupted-stage")
        run(case, "test")
        case["config"].write_bytes((case["backup"] / "before.plist").read_bytes())
        set_phase(case, "staged")
        stage = case["bundle"].parent / ".BrightnessKeys-s540-stage.kext"
        case["bundle"].rename(stage)
        with (stage / "Contents/MacOS/BrightnessKeys").open("ab") as stream:
            stream.write(b"unknown-stage-content")
        assert_refused(case)

        case = make_case("interrupted-copy-incomplete-stage")
        run(case, "test")
        original_bytes = (case["backup"] / "before.plist").read_bytes()
        case["config"].write_bytes(original_bytes)
        set_phase(case, "prepared")
        stage = case["bundle"].parent / ".BrightnessKeys-s540-stage.kext"
        case["bundle"].rename(stage)
        (stage / "Contents/MacOS/BrightnessKeys").unlink()
        assert_refused(case)
        assert case["config"].read_bytes() == original_bytes and not case["bundle"].exists()
        assert stage.exists(), "An incomplete interrupted copy must be retained for inspection."

        # Rollback must preserve a later independent EFI edit.
        case = make_case("changed-config-blocks-restore")
        run(case, "test")
        changed = plistlib.loads(case["config"].read_bytes())
        changed["Misc"]["Boot"]["Timeout"] += 1
        write_config(case["config"], changed)
        assert_refused(case, "restore")

        # Existing untracked files and registrations must never be adopted or
        # overwritten, even if they happen to contain the same driver payload.
        case = make_case("existing-bundle-without-backup")
        shutil.copytree(case["package"] / "payload" / BUNDLE, case["bundle"])
        assert_refused(case)

        case = make_case("existing-registration-without-backup")
        changed = copy.deepcopy(baseline)
        changed["Kernel"]["Add"].append(dict(entry, Enabled=False))
        write_config(case["config"], changed)
        assert_refused(case)

        case = make_case("duplicate-registration")
        changed = copy.deepcopy(baseline)
        changed["Kernel"]["Add"].extend([dict(entry), dict(entry)])
        write_config(case["config"], changed)
        assert_refused(case)

        case = make_case("malformed-kernel-add")
        changed = copy.deepcopy(baseline)
        changed["Kernel"]["Add"] = {"unexpected": dict(entry)}
        write_config(case["config"], changed)
        assert_refused(case)

        case = make_case("malformed-entry-value")
        changed = copy.deepcopy(baseline)
        changed["Kernel"]["Add"][0]["Enabled"] = "true"
        write_config(case["config"], changed)
        assert_refused(case)

        # Check the complete pinned payload before the first EFI write.
        case = make_case("tampered-payload")
        executable = case["package"] / "payload" / BUNDLE / "Contents/MacOS/BrightnessKeys"
        with executable.open("ab") as stream:
            stream.write(b"not-the-pinned-release")
        assert_refused(case)

        case = make_case("tampered-validator")
        validator = case["package"] / "bin/ocvalidate"
        with validator.open("ab") as stream:
            stream.write(b"not-the-pinned-validator")
        assert_refused(case)

        case = make_case("different-opencore")
        with (case["boot"] / "EFI/OC/OpenCore.efi").open("ab") as stream:
            stream.write(b"not-the-current-opencore")
        assert_refused(case)

        # A symlink can preserve readable bytes while redirecting writes. Reject
        # it rather than following it into an untracked location.
        case = make_case("symlink-config")
        target = case["base"] / "outside-efi-config.plist"
        case["config"].rename(target)
        case["config"].symlink_to(target)
        target_before = target.read_bytes()
        assert_refused(case)
        assert target.read_bytes() == target_before

        case = make_case("symlink-payload")
        info_path = case["package"] / "payload" / BUNDLE / "Contents/Info.plist"
        target = case["base"] / "outside-payload-info.plist"
        info_path.rename(target)
        info_path.symlink_to(target)
        target_before = target.read_bytes()
        assert_refused(case)
        assert target.read_bytes() == target_before

        # An interrupted or foreign backup cannot authorize any new mutation.
        case = make_case("incomplete-backup")
        case["backup"].mkdir()
        (case["backup"] / "before.plist").write_bytes(case["config"].read_bytes())
        assert_refused(case)

        print(f"PASS: BrightnessKeys EFI scope, exact restore, macOS metadata/xattr handling, collision/tamper guards, symlinks, and incomplete backups ({count} CLI operations).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
