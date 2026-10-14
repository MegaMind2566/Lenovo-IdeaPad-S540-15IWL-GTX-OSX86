#!/usr/bin/env python3
"""CI-only interrupted-swap regression tests; no live kext/kernel operations.

Run as root on the Intel macOS Actions runner, after building the package:
sudo env GITHUB_ACTIONS=true RUNNER_TEMP="$RUNNER_TEMP" python3 \
    tests/test_volume_installer.py build/audio-volume/S540-volume-fine-v1
"""
import hashlib
import os
from pathlib import Path
import plistlib
import re
import shlex
import shutil
import struct
import subprocess
import sys
import tempfile


FILES = (
    "Contents/Info.plist",
    "Contents/MacOS/VoodooHDA",
    "Contents/_CodeSignature/CodeResources",
)
VOLUME_UUID = "11111111-2222-3333-4444-555555555555"
BOOT_UUID = "AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fingerprints(bundle):
    return tuple(digest(Path(bundle) / name) for name in FILES)


def manifest(bundle, destination):
    destination.write_text(
        "".join(f"{digest(bundle / name)}  {name}\n" for name in FILES),
        encoding="ascii",
    )
    destination.chmod(0o600)


def command(*args):
    subprocess.run(args, check=True, timeout=75)


def copy_bundle(source, destination):
    assert not destination.exists()
    destination.parent.mkdir(parents=True, exist_ok=True)
    command(
        "/usr/bin/ditto", "--norsrc", "--noextattr", "--noacl", "--noqtn",
        str(source), str(destination),
    )
    for item in (destination, *destination.rglob("*")):
        assert not item.is_symlink()
        item.chmod(item.stat().st_mode & 0o777 & ~0o022)


def write_plist(path, values):
    with path.open("wb") as stream:
        plistlib.dump(values, stream, sort_keys=False)
    path.chmod(0o600)


def main():
    if (
        os.environ.get("GITHUB_ACTIONS") != "true"
        or sys.platform != "darwin"
        or os.uname().machine != "x86_64"
        or os.geteuid() != 0
    ):
        raise SystemExit("Run this fixture as root on the Intel macOS Actions runner.")
    if len(sys.argv) != 2:
        raise SystemExit("Usage: test_volume_installer.py BUILT_PACKAGE_DIRECTORY")
    runner_temp = Path(os.environ["RUNNER_TEMP"]).resolve(strict=True)
    package = Path(sys.argv[1]).resolve(strict=True)
    helper = package / "tools/volume_driver_test.sh"
    payload = package / "assets/volume/VoodooHDA.kext"
    payload_sums = package / "assets/volume/SHA256SUMS"
    text = helper.read_text(encoding="utf-8")
    marker = 'case "$MODE" in install|restore|verify'
    assert text.count(marker) == 1, "Expected exactly one main CLI boundary."
    prefix = text[:text.index(marker)]
    assert re.search(r"^install_driver\(\)", prefix, re.MULTILINE)
    assert re.search(r"^restore_driver\(\)", prefix, re.MULTILINE)
    assert re.search(r"^verify_macho_header\(\)", prefix, re.MULTILINE)
    runtime_source = "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("#")
    )
    assert not re.search(r"\b(?:lipo|otool|xcrun)\b", runtime_source), (
        "Installer must not invoke Xcode-managed tools on the user's Mac."
    )
    locked_sha = re.search(r"^PAYLOAD_MANIFEST_SHA='([0-9a-f]{64})'$", text, re.MULTILINE)
    assert locked_sha, "Package must contain its injected manifest lock."
    assert digest(payload_sums) == locked_sha.group(1)

    with tempfile.TemporaryDirectory(prefix="s540-installer-journal-", dir=runner_temp) as folder:
        root = Path(folder).resolve(strict=True)
        assert root.parent == runner_temp and root.name.startswith("s540-installer-journal-")
        root.chmod(0o700)
        functions = root / "actual-helper-functions.sh"
        functions.write_text(prefix, encoding="utf-8")
        functions.chmod(0o600)
        approved_payload = root / "approved-payload/VoodooHDA.kext"
        copy_bundle(payload, approved_payload)
        approved_sums = root / "approved-payload/SHA256SUMS"
        shutil.copyfile(payload_sums, approved_sums)
        approved_sums.chmod(0o600)
        assert digest(approved_sums) == locked_sha.group(1)

        # Exercise the production byte-header reader, not a duplicate parser.
        # Its thin-header check complements the full manifest/signature checks
        # in verify_payload; these tiny crafted files are never loaded as kexts.
        header_folder = root / "macho-header-fixtures"
        header_folder.mkdir(mode=0o700)

        def check_header(path, accepts, unprivileged=False):
            shell = prefix + "\nverify_macho_header " + shlex.quote(str(path)) + "\n"
            options = {"user": 501, "group": 20, "extra_groups": []} if unprivileged else {}
            result = subprocess.run(
                ["/bin/bash", "-c", shell], capture_output=True, text=True,
                timeout=15, **options,
            )
            assert (result.returncode == 0) == accepts, (
                f"Header {path.name}: unexpected status {result.returncode}\n"
                f"{result.stdout}\n{result.stderr}"
            )

        check_header(approved_payload / FILES[1], True)
        intel_header = struct.pack("<IIII", 0xFEEDFACF, 0x01000007, 3, 0x0B)
        valid = header_folder / "intel-kext-header.bin"
        valid.write_bytes(intel_header)
        valid.chmod(0o600)
        check_header(valid, True)
        subtype = header_folder / "intel-capability-subtype-header.bin"
        subtype.write_bytes(struct.pack("<IIII", 0xFEEDFACF, 0x01000007, 0x80000003, 0x0B))
        check_header(subtype, True)
        rejected_headers = {
            "arm64": struct.pack("<IIII", 0xFEEDFACF, 0x0100000C, 3, 0x0B),
            "intel32": struct.pack("<IIII", 0xFEEDFACF, 0x00000007, 3, 0x0B),
            "fat": struct.pack(">IIII", 0xCAFEBABE, 1, 0x01000007, 3),
            "big-endian": struct.pack(">IIII", 0xFEEDFACF, 0x01000007, 3, 0x0B),
            "non-kext": struct.pack("<IIII", 0xFEEDFACF, 0x01000007, 3, 2),
        }
        rejected_headers.update({
            f"truncated-{length}": intel_header[:length]
            for length in (0, 1, 12, 13, 15)
        })
        for name, contents in rejected_headers.items():
            path = header_folder / f"{name}.bin"
            path.write_bytes(contents)
            check_header(path, False)
        check_header(header_folder / "absent.bin", False)
        # Root can read chmod 000 files. Drop credentials only for this read so
        # a real permission-denied error tests od/awk pipefail handling.
        unreadable = header_folder / "unreadable.bin"
        unreadable.write_bytes(intel_header)
        unreadable.chmod(0o000)
        check_header(unreadable, False, unprivileged=True)
        print("PASS: native Mach-O header reader accepts Intel kexts and rejects invalid/unreadable headers.")

        # A signed, never-loaded fixture models the prior 3.6.9 installation.
        # Its hashes are bound to the private source state, as on the laptop.
        # Signal processing is covered by the separate actual-function C++ tests.
        legacy = root / "previous-microphone/VoodooHDA.kext"
        copy_bundle(approved_payload, legacy)
        info_path = legacy / FILES[0]
        with info_path.open("rb") as stream:
            info = plistlib.load(stream)
        info["CFBundleVersion"] = "3.6.9"
        info["CFBundleShortVersionString"] = "3.6.9"
        info["IOKitPersonalities"]["VoodooHDA"].pop("S540OutputRangeFix", None)
        write_plist(info_path, info)
        command("/usr/bin/codesign", "--force", "--sign", "-", str(legacy))
        command("/usr/bin/codesign", "--verify", "--strict", str(legacy))
        original_hashes = fingerprints(legacy)
        payload_hashes = fingerprints(approved_payload)
        assert original_hashes != payload_hashes

        def make_case(name, phase="swapping", driver="original", stage=None, previous=None, fresh=False):
            base = root / name
            data = base / "Fake Data"
            extensions = data / "Library/Extensions"
            extensions.mkdir(parents=True)
            backup = data / "Library/Application Support/S540-volume-fine"
            backup.mkdir(parents=True, mode=0o700)
            backup.chmod(0o700)
            original = backup / "original.kext"
            copy_bundle(legacy, original)
            original_sums = backup / "original-SHA256SUMS"
            manifest(original, original_sums)
            source_backup = data / "Library/Application Support/S540-microfono"
            source_backup.mkdir(mode=0o700)
            source_manifest = base / "source-SHA256SUMS"
            manifest(legacy, source_manifest)
            source_state = source_backup / "state.plist"
            write_plist(source_state, {
                "Format": 1, "Phase": "rebootrequired", "VolumeUUID": VOLUME_UUID,
                "PayloadManifestHash": digest(source_manifest), "RuntimeSipData": "03000000",
            })
            config = base / "fake-efi/config.plist"
            config.parent.mkdir()
            write_plist(config, {"boot-args": "-v voodoo-layout-id=11 -igfxblr"})
            paths = {
                "FIXTURE_ROOT": root,
                "CASE_ROOT": base,
                "ROOT_DATA": data,
                "DRIVER_PARENT": extensions,
                "DRIVER": extensions / "VoodooHDA.kext",
                "STAGE": extensions / ".VoodooHDA-s540-volume-stage.kext",
                "PREVIOUS": extensions / ".VoodooHDA-s540-volume-previous.kext",
                "BACKUP": backup,
                "STATE": backup / "state.plist",
                "ORIGINAL": original,
                "ORIGINAL_SUMS": original_sums,
                "TEMP": base / "private-temp",
                "CONFIG": config,
                "AUDIO_BACKUP": base / "never-read-audio-backup",
                "CHECK": base / "never-run-original-check.sh",
                "PACKAGE": root / "approved-payload",
                "PAYLOAD": approved_payload,
                "PAYLOAD_SUMS": approved_sums,
                "SYSTEM_ROOT": base / "never-read-system-volume",
            }
            paths["TEMP"].mkdir(mode=0o700)
            assert all(path == root or root in path.parents for path in paths.values())
            state = {
                "Format": 1,
                "Phase": phase,
                "VolumeUUID": VOLUME_UUID,
                "OriginalManifestHash": digest(original_sums),
                "PayloadManifestHash": locked_sha.group(1),
                "OriginalBootSessionUUID": BOOT_UUID,
                "RuntimeSipData": "03000000",
            }
            write_plist(paths["STATE"], state)
            for key, which in (("DRIVER", driver), ("STAGE", stage), ("PREVIOUS", previous)):
                if which:
                    copy_bundle(legacy if which == "original" else approved_payload, paths[key])
            paths["SOURCE_STATE"] = source_state
            if fresh:
                shutil.rmtree(backup)
            return paths

        def run_case(paths, mode, succeeds=True, message=None, recovery=False):
            paths["TEMP"].mkdir(mode=0o700, exist_ok=True)
            assignments = "\n".join(f"{key}={shlex.quote(str(value))}" for key, value in paths.items())
            shell = f"""
source {shlex.quote(str(functions))}
{assignments}
MODE={shlex.quote(mode)}
VOLUME_UUID={shlex.quote(VOLUME_UUID)}
BOOT_UUID={shlex.quote(BOOT_UUID)}
RECOVERY={int(recovery)}
RECOVERY_GROUP_MATCH=0
for name in ROOT_DATA DRIVER_PARENT DRIVER STAGE PREVIOUS BACKUP STATE ORIGINAL ORIGINAL_SUMS TEMP CONFIG AUDIO_BACKUP CHECK PACKAGE PAYLOAD PAYLOAD_SUMS SYSTEM_ROOT SOURCE_STATE; do
    value=${{!name}}
    case "$value" in "$FIXTURE_ROOT"/*) ;; *) echo "Unsafe fixture global: $name" >&2; exit 95;; esac
done
# The real swap and journal functions remain unchanged. Only session/volume
# queries and kernel rebuilding are replaced; no live command is permitted.
runtime_sip() {{ :; }}
source_runtime_ok() {{ :; }}
check_kernel_symbols() {{ :; }}
volume_uuid() {{ VOLUME_UUID={shlex.quote(VOLUME_UUID)}; }}
rebuild() {{
    if [ "$MODE" = install ]; then write_phase rebootrequired;
    elif [ "$RECOVERY" -eq 1 ]; then write_phase restorepending;
    else write_phase restorerebootrequired; fi
}}
set -T
trap 'case "$BASH_COMMAND" in /usr/bin/kmutil*|/usr/sbin/nvram*|/usr/sbin/diskutil*|/usr/bin/sudo*) echo "Live command prohibited in fixture" >&2; exit 96;; esac' DEBUG
verify_payload
{mode}_driver
"""
            result = subprocess.run(
                ["/bin/bash", "-c", shell], capture_output=True, text=True, timeout=45,
            )
            if (result.returncode == 0) != succeeds:
                raise AssertionError(f"{paths['CASE_ROOT'].name}: unexpected status {result.returncode}\n{result.stdout}\n{result.stderr}")
            if message:
                assert message in result.stderr, f"Expected diagnostic {message!r}: {result.stderr}"
            if paths["ORIGINAL"].exists():
                assert fingerprints(paths["ORIGINAL"]) == original_hashes
            assert fingerprints(approved_payload) == payload_hashes
            return result

        def phase(paths):
            with paths["STATE"].open("rb") as stream:
                return plistlib.load(stream)["Phase"]

        def assert_finished(paths, hashes, expected_phase):
            assert fingerprints(paths["DRIVER"]) == hashes
            assert not paths["STAGE"].exists() and not paths["PREVIOUS"].exists()
            assert phase(paths) == expected_phase

        assert "'/Volumes/240 GB" not in prefix and '$CONFIG' not in prefix
        case = make_case("fresh-upgrade-without-efi", fresh=True)
        before_source = case["SOURCE_STATE"].read_bytes()
        case["CONFIG"].unlink()
        run_case(case, "install")
        assert_finished(case, payload_hashes, "rebootrequired")
        assert case["SOURCE_STATE"].read_bytes() == before_source
        assert not case["CONFIG"].exists()

        for name, field, value, diagnostic in (
            ("wrong-source-volume", "VolumeUUID", "00000000-2222-3333-4444-555555555555", "another Data volume"),
            ("wrong-source-manifest", "PayloadManifestHash", "0" * 64, "private microphone payload reference"),
            ("source-restored", "Phase", "restored", "not in an installed state"),
        ):
            case = make_case(name, fresh=True)
            with case["SOURCE_STATE"].open("rb") as stream:
                source_state = plistlib.load(stream)
            source_state[field] = value
            write_plist(case["SOURCE_STATE"], source_state)
            run_case(case, "install", False, diagnostic)
            assert fingerprints(case["DRIVER"]) == original_hashes
            assert not case["BACKUP"].exists()
            assert not case["STAGE"].exists() and not case["PREVIOUS"].exists()

        case = make_case("source-state-writable", fresh=True)
        case["SOURCE_STATE"].chmod(0o666)
        run_case(case, "install", False, "writable by other users")
        assert fingerprints(case["DRIVER"]) == original_hashes and not case["BACKUP"].exists()

        case = make_case("normal-install", phase="staging")
        run_case(case, "install")
        assert_finished(case, payload_hashes, "rebootrequired")

        case = make_case("install-after-first-rename", driver=None, stage="payload", previous="original")
        run_case(case, "install")
        assert_finished(case, payload_hashes, "rebootrequired")

        case = make_case("install-after-second-rename", driver="payload", previous="original")
        run_case(case, "install")
        assert_finished(case, payload_hashes, "rebootrequired")

        case = make_case("restore-after-first-rename", phase="restoring", driver=None, stage="payload", previous="original")
        before_config = case["CONFIG"].read_bytes()
        run_case(case, "restore")
        assert_finished(case, original_hashes, "restorerebootrequired")
        assert case["CONFIG"].read_bytes() == before_config

        case = make_case("unknown-stage", phase="staging", stage="payload")
        with (case["STAGE"] / FILES[1]).open("ab") as stream:
            stream.write(b"unknown-stage-marker")
        unknown_hashes = fingerprints(case["STAGE"])
        run_case(case, "install", False, "Unrecognized staging content.")
        assert fingerprints(case["DRIVER"]) == original_hashes
        assert fingerprints(case["STAGE"]) == unknown_hashes
        assert not case["PREVIOUS"].exists() and phase(case) == "staging"

        case = make_case("changed-config", phase="staging")
        write_plist(case["CONFIG"], {"boot-args": "-v voodoo-layout-id=11 -igfxblr", "LaterSetting": True})
        changed_config = case["CONFIG"].read_bytes()
        run_case(case, "install")
        assert_finished(case, payload_hashes, "rebootrequired")
        run_case(case, "restore")
        assert_finished(case, original_hashes, "restorerebootrequired")
        assert case["CONFIG"].read_bytes() == changed_config

        for name, writable in (("writable-state", "STATE"), ("writable-manifest", "ORIGINAL_SUMS")):
            case = make_case(name, phase="staging")
            case[writable].chmod(0o666)
            run_case(case, "install", False, "A backup entry is writable by other users.")
            assert fingerprints(case["DRIVER"]) == original_hashes
            assert not case["STAGE"].exists() and not case["PREVIOUS"].exists()
            assert phase(case) == "staging"

        case = make_case("non-root-backup-file", phase="staging")
        os.chown(case["ORIGINAL"] / FILES[0], 501, -1)
        run_case(case, "install", False, "A backup entry is not owned by root or is a link.")
        assert fingerprints(case["DRIVER"]) == original_hashes
        assert phase(case) == "staging"

        case = make_case("interrupted-state-commit", driver="payload", previous="original")
        with case["STATE"].open("rb") as stream:
            draft = plistlib.load(stream)
        draft["Phase"] = "swapped"
        write_plist(case["BACKUP"] / "state-next.plist", draft)
        run_case(case, "install")
        assert_finished(case, payload_hashes, "rebootrequired")
        assert not (case["BACKUP"] / "state-next.plist").exists()

        case = make_case("unexpected-state-draft", driver="payload", previous="original")
        with case["STATE"].open("rb") as stream:
            draft = plistlib.load(stream)
        draft["Phase"] = "swapped"
        draft["UnexpectedChange"] = "rejected"
        write_plist(case["BACKUP"] / "state-next.plist", draft)
        run_case(case, "install", False, "The temporary state contains changes beyond the phase; the test has stopped.")
        assert fingerprints(case["DRIVER"]) == payload_hashes
        assert fingerprints(case["PREVIOUS"]) == original_hashes
        assert phase(case) == "swapping"

        case = make_case("offline-restore-without-efi", phase="verified", driver="payload")
        case["CONFIG"].unlink()
        shutil.rmtree(case["SOURCE_STATE"].parent)
        run_case(case, "restore", recovery=True)
        assert_finished(case, original_hashes, "restorepending")
        assert not case["CONFIG"].exists()

        print("PASS: source ownership, fresh upgrade, interrupted swaps and exact rollback; no live kext or kernel operations.")


if __name__ == "__main__":
    main()
