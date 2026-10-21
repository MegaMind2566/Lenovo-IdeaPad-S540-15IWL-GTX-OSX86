#!/usr/bin/env python3
"""Build app 0.1.1 and package the exact previously signed kernel 0.1.0.

No kernel compiler, SDK download, driver loading or kernel dependency probe is
invoked. The reused bundle and its original provenance are immutable inputs.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import platform
import plistlib
import shutil
import stat
import subprocess
import sys
import zipfile

BUILDER = Path(__file__).resolve()
BASE_BUILDER = BUILDER.with_name("build_s540_hotkeys.py")
spec = importlib.util.spec_from_file_location("s540_build_helpers", BASE_BUILDER)
assert spec and spec.loader
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
BuildError, require = base.BuildError, base.require
file_hash, digest, write_json = base.file_hash, base.digest, base.write_json
tree_hashes, copy_file, zip_tree = base.tree_hashes, base.copy_file, base.zip_tree

PACKAGE = "S540-Tasti-v1.1"
APP_VERSION = "0.1.1"
KERNEL_VERSION = "0.1.0"
KERNEL_SHA = "5e529274ecba7905e023e5b807de4dda2e14be51cbff45dcf84bceeb01b78fc4"
KERNEL_ID = "org.s540.HotkeysVPC"
KERNEL_NAME = "S540HotkeysVPC"
APP_ID, APP_NAME = "org.s540.Hotkeys", "S540Tasti"
SOURCE_REVIEW = "SOURCE-REVIEW.json"
WORKFLOW = ".github/workflows/build-s540-hotkeys-app-update.yml"
WRAPPERS = ("INSTALLA-TASTI.command", "RIPRISTINA-TASTI.command", "VERIFICA-TASTI.command")
REQUIRED = (
    "app/S540Tasti.m", "app/HotkeyPolicy.h", "app/policy_tests.c", "app/Info.plist", "app/LICENSE",
    "kernel/S540HotkeysVPC.cpp", "kernel/S540HotkeysVPC.hpp", "kernel/ProtocolCore.hpp", "kernel/Info.plist", "kernel/LICENSE",
    *("installer/" + name for name in WRAPPERS), "installer/tools/s540-common.sh", "installer/tests/test-manifest.sh",
    "prebuilt/KERNEL-INPUT.json", "prebuilt/S540HotkeysVPC-0.1.0.zip",
    "LEGGIMI.txt", "README.md", "LICENSE", "licenses/NOTICES.txt", "licenses/GPL-2.0-YogaSMC.txt",
)


def builder_hashes() -> dict[str, str]:
    return {p.name: file_hash(p) for p in (BUILDER, BASE_BUILDER)}


def verify_prebuilt(source: Path, destination: Path | None = None) -> dict:
    directory = source / "prebuilt"
    contract = json.loads((directory / "KERNEL-INPUT.json").read_text())
    require(contract.get("schema") == 1 and contract.get("archive") == "S540HotkeysVPC-0.1.0.zip" and
            contract.get("bundle_root") == KERNEL_NAME + ".kext", "Wrong prebuilt kernel input contract")
    require(contract.get("binary_sha256") == KERNEL_SHA and contract.get("bundle_identifier") == KERNEL_ID and
            contract.get("bundle_version") == KERNEL_VERSION, "The reused kernel must remain exact signed 0.1.0")
    archive = directory / contract["archive"]
    require(file_hash(archive) == contract["archive_sha256"], "Prebuilt kernel archive changed")
    expected_files = {"Contents/Info.plist", "Contents/MacOS/" + KERNEL_NAME, "Contents/_CodeSignature/CodeResources"}
    require(set(contract["bundle_files"]) == expected_files, "Unexpected prebuilt bundle file set")
    require(contract["bundle_files"]["Contents/MacOS/" + KERNEL_NAME] == KERNEL_SHA, "Wrong prebuilt binary hash")
    require(contract.get("native_ci_commit") == "816edfda9c5a7e6217ac344c044edd94ef66042d" and
            contract.get("native_ci_run_id") == "39631773181", "Wrong reused-kernel native provenance")
    prefix = contract["bundle_root"] + "/"
    with zipfile.ZipFile(archive) as reader:
        require(reader.testzip() is None, "Corrupt prebuilt kernel archive")
        require(len(reader.namelist()) == 3 and set(reader.namelist()) == {prefix + p for p in expected_files},
                "Prebuilt archive must contain exactly the three original bundle files")
        for entry in reader.infolist():
            relative = entry.filename[len(prefix):]
            mode = entry.external_attr >> 16
            require(stat.S_ISREG(mode), "Non-regular prebuilt archive member")
            expected_mode = 0o755 if relative.startswith("Contents/MacOS/") else 0o644
            require(stat.S_IMODE(mode) == expected_mode, "Wrong prebuilt archive permissions")
            content = reader.read(entry)
            require(digest(content) == contract["bundle_files"][relative], "Prebuilt bundle file changed: " + relative)
            if destination is not None:
                path = destination / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
                path.chmod(expected_mode)
        info_bytes = reader.read(prefix + "Contents/Info.plist")
        info = plistlib.loads(info_bytes)
        require(info.get("CFBundleIdentifier") == KERNEL_ID and info.get("CFBundleVersion") == KERNEL_VERSION and
                info.get("CFBundleExecutable") == KERNEL_NAME and info.get("CFBundlePackageType") == "KEXT",
                "Wrong reused-kernel bundle metadata")
        require((source / "kernel/Info.plist").read_bytes() == info_bytes, "Packaged kernel source Info.plist differs from reused bundle")
    proof_names = contract.get("provenance_files", {})
    require({"BUILD.json", "kernel-symbols-reviewed.json", "s540-hotkeys-bzero-review.json"} <= set(proof_names),
            "Missing original kernel build and ABI proof")
    for name, expected in proof_names.items():
        require(PurePosixPath(name).name == name and name.endswith(".json"), "Invalid kernel provenance filename")
        require(file_hash(directory / "provenance" / name) == expected, "Original kernel provenance changed: " + name)
    metadata = json.loads((directory / "provenance/BUILD.json").read_text())
    abi = json.loads((directory / "provenance/kernel-symbols-reviewed.json").read_text())
    require(metadata.get("kernel_binary_sha256") == KERNEL_SHA and metadata.get("native_build") is True and
            metadata.get("ci_commit") == contract["native_ci_commit"] and metadata.get("ci_run_id") == contract["native_ci_run_id"],
            "Reused-kernel native build record disagrees with pinned input")
    require(abi.get("sha256") == KERNEL_SHA and abi.get("unapproved_imports") == [], "Missing completed original kernel ABI review")
    original_sources = metadata["source_review"]["files"]
    for name, expected in original_sources.items():
        if name.startswith("kernel/"):
            require(file_hash(source / name) == expected, "Reused kernel source body changed: " + name)
    if destination is not None:
        actual = base.macho_symbols(destination / "Contents/MacOS" / KERNEL_NAME, 11)
        require(all(actual[key] == abi[key] for key in ("sha256", "cpu", "filetype", "defined", "undefined")),
                "Reused kernel Mach-O differs from the original reviewed artifact")
    return contract


def validate_sources(source: Path) -> dict[str, str]:
    files = tree_hashes(source, (SOURCE_REVIEW,))
    require(set(REQUIRED) <= files.keys(), "Missing update inputs: " + ", ".join(sorted(set(REQUIRED) - files.keys())))
    info = plistlib.loads((source / "app/Info.plist").read_bytes())
    require(info.get("CFBundleIdentifier") == APP_ID and info.get("CFBundleExecutable") == APP_NAME and
            info.get("CFBundlePackageType") == "APPL" and info.get("CFBundleVersion") == APP_VERSION and
            info.get("CFBundleShortVersionString") == APP_VERSION and info.get("LSMinimumSystemVersion") == "13.0" and
            info.get("LSUIElement") is True, "App must be version 0.1.1 for Intel macOS 13 or later")
    verify_prebuilt(source)
    for script in sorted((source / "installer").rglob("*")):
        if script.is_file() and script.suffix in (".command", ".sh"):
            result = subprocess.run(["/bin/bash", "-n", str(script)], capture_output=True, text=True)
            require(result.returncode == 0, "Installer shell syntax failed: " + str(script) + result.stderr)
    # Existing pure manifest/upgrade fixtures use temporary directories only.
    for test in sorted((source / "installer/tests").glob("test-*.sh")):
        result = subprocess.run(["/bin/bash", str(test)], capture_output=True, text=True, timeout=30)
        require(result.returncode == 0, "Installer pure fixture failed: " + test.name + result.stdout + result.stderr)
    return files


def freeze_sources(source: Path) -> None:
    files = validate_sources(source)
    write_json(source / SOURCE_REVIEW, {"schema": 1, "mode": "app-only-update", "package": PACKAGE,
        "app_version": APP_VERSION, "kernel_version": KERNEL_VERSION, "kernel_binary_sha256": KERNEL_SHA,
        "builder_inputs": builder_hashes(), "files": files})
    print(f"Frozen {len(files)} app-update inputs; reused kernel is exactly {KERNEL_SHA}")


def check_sources(source: Path) -> dict:
    files = validate_sources(source)
    review = json.loads((source / SOURCE_REVIEW).read_text())
    require(review.get("schema") == 1 and review.get("mode") == "app-only-update" and review.get("package") == PACKAGE,
            "Wrong app-update source freeze")
    require(review.get("app_version") == APP_VERSION and review.get("kernel_version") == KERNEL_VERSION and
            review.get("kernel_binary_sha256") == KERNEL_SHA, "Wrong independent app/kernel version contract")
    require(review.get("files") == files and review.get("builder_inputs") == builder_hashes(),
            "App-update source or builder changed after explicit review freeze")
    print(f"PASS: {len(files)} frozen input hashes, original signed kernel/provenance, app plist, installer syntax and pure fixtures")
    return review


def verify_request(request: Path, source: Path, repository: Path) -> None:
    paths = {BUILDER.relative_to(repository).as_posix(), BASE_BUILDER.relative_to(repository).as_posix(), WORKFLOW}
    paths.update(p.relative_to(repository).as_posix() for p in source.rglob("*") if p.is_file())
    data = json.loads(request.read_text())
    require(data.get("schema") == 1 and data.get("files") == {p: file_hash(repository / p) for p in sorted(paths)},
            "Native app-only request must bind both builders, dedicated workflow and every package/prebuilt/provenance input")
    print(f"PASS: dedicated app-only native request binds {len(paths)} exact inputs")


def build(source: Path, output: Path, review: dict) -> Path:
    require(platform.system() == "Darwin" and platform.machine() == "x86_64", "App native build requires Intel macOS")
    require(not output.exists(), "Use a new app-update output directory")
    output.mkdir(parents=True)
    stage, work = output / PACKAGE, output / "native-work"
    stage.mkdir()
    work.mkdir()
    runner = base.Runner(work)
    metadata = {"schema": 1, "package": PACKAGE, "mode": "app-only-update", "app_version": APP_VERSION,
        "kernel_version": KERNEL_VERSION, "kernel_rebuilt": False, "kernel_resigned": False, "kernel_loaded": False,
        "native_app_build": False, "target_hardware_tested": False, "source_review": review,
        "source_review_sha256": file_hash(source / SOURCE_REVIEW), "builder_inputs": builder_hashes(),
        "ci_commit": os.environ.get("GITHUB_SHA", ""), "ci_run_id": os.environ.get("GITHUB_RUN_ID", ""),
        "ci_repository": os.environ.get("GITHUB_REPOSITORY", ""), "runner_arch": platform.machine(),
        "validation_scope": "New app compilation, pure policy/self-tests, code signatures and exact reuse of the original signed kernel/provenance. No new kernel build, driver load, kmutil or physical action."}
    try:
        kext = stage / "assets" / (KERNEL_NAME + ".kext")
        metadata["reused_kernel"] = verify_prebuilt(source, kext)
        runner.run(["/usr/bin/codesign", "--verify", "--strict", "--verbose=2", str(kext)], label="verify-original-kernel-signature-read-only")
        metadata["clang_version"] = runner.run(["xcrun", "clang", "--version"], label="app-compiler-version")
        metadata["macos_version"] = runner.run(["sw_vers"], label="app-build-macos-version")
        metadata["xcode_version"] = runner.run(["xcodebuild", "-version"], label="app-build-xcode-version")
        test = work / "policy-tests"
        runner.run(["xcrun", "clang", "-std=c11", "-arch", "x86_64", "-Wall", "-Wextra", "-Werror", "-O2",
                    str(source / "app/policy_tests.c"), "-o", str(test)], label="compile-app-policy-fixtures")
        runner.run([str(test)], label="pure-app-policy-fixtures")
        app = stage / "assets" / (APP_NAME + ".app")
        executable = app / "Contents/MacOS" / APP_NAME
        executable.parent.mkdir(parents=True)
        object_path = work / (APP_NAME + ".o")
        flags = ["-arch", "x86_64", "-mmacosx-version-min=13.0", "-fobjc-arc", "-Wall", "-Wextra", "-Werror", "-O2"]
        runner.run(["xcrun", "clang", *flags, "-c", str(source / "app/S540Tasti.m"), "-o", str(object_path)], label="compile-app-only")
        link = ["xcrun", "clang", *flags, str(object_path), "-o", str(executable)]
        for framework in ("Foundation", "Cocoa", "IOKit", "CoreAudio", "CoreWLAN", "IOBluetooth", "ApplicationServices"):
            link.extend(["-framework", framework])
        runner.run(link, label="link-app-only")
        copy_file(source / "app/Info.plist", app / "Contents/Info.plist")
        executable.chmod(0o755)
        require(runner.run(["xcrun", "lipo", "-archs", str(executable)], label="app-architecture") == "x86_64", "Wrong app architecture")
        base.macho_symbols(executable, 2)
        runner.run(["/usr/bin/plutil", "-lint", str(app / "Contents/Info.plist")], label="app-plist")
        runner.run(["/usr/bin/codesign", "--force", "--sign", "-", "--timestamp=none", "--identifier", APP_ID, str(app)], label="sign-new-app-only")
        runner.run(["/usr/bin/codesign", "--verify", "--strict", "--verbose=2", str(app)], label="verify-new-app-signature")
        runner.run([str(executable), "--self-test"], label="app-pure-self-test")
        app_abi = base.macho_symbols(executable, 2)
        require(not any("IOBluetoothPreferenceSetControllerPowerState" in name for name in app_abi["undefined"]),
                "Bluetooth setter must remain dynamically resolved")
        write_json(work / "app-symbols.json", app_abi)
        require(check_sources(source) == review, "App-update inputs changed during build")
        require(all(file_hash(kext / relative) == expected for relative, expected in metadata["reused_kernel"]["bundle_files"].items()),
                "An original signed kernel bundle file changed during packaging")
        metadata.update({"native_app_build": True, "app_binary_sha256": file_hash(executable), "app_abi": app_abi,
                         "kernel_binary_sha256": KERNEL_SHA, "native_commands": runner.commands,
                         "result": "NATIVE_APP_UPDATE_VERIFIED_ORIGINAL_KERNEL_REUSED_TARGET_NOT_TESTED"})
        for name in WRAPPERS:
            copy_file(source / "installer" / name, stage / name, True)
        source_tools = source / "installer/tools"
        tools_manifest = tree_hashes(source_tools)
        for relative in tools_manifest:
            copy_file(source_tools / relative, stage / "tools" / relative,
                      relative.endswith((".sh", ".command")))
        require(tree_hashes(stage / "tools") == tools_manifest,
                "Packaged root tools file set or contents differ from installer/tools")
        for name in ("LEGGIMI.txt", "README.md", "LICENSE"):
            copy_file(source / name, stage / name)
        for relative in tree_hashes(source):
            copy_file(source / relative, stage / "src" / relative, relative.endswith((".command", ".sh")))
        copy_file(source / "kernel/LICENSE", stage / "licenses/kernel-GPL-2.0.txt")
        copy_file(source / "app/LICENSE", stage / "licenses/app-MIT.txt")
        for path in sorted((source / "licenses").rglob("*")):
            if path.is_file():
                copy_file(path, stage / "licenses" / path.relative_to(source / "licenses"))
        for path in (BUILDER, BASE_BUILDER):
            copy_file(path, stage / "src/builders" / path.name)
        for path in sorted((source / "prebuilt/provenance").glob("*.json")):
            copy_file(path, stage / "validation/original-kernel" / path.name)
        for path in sorted(work.glob("*")):
            if path.is_file() and path.suffix in (".txt", ".json"):
                copy_file(path, stage / "validation/app-update" / path.name)
        write_json(stage / "BUILD.json", metadata)
        hashes = tree_hashes(stage)
        (stage / "SHA256SUMS").write_text("".join(f"{h}  {p}\n" for p, h in hashes.items()))
        require(tree_hashes(stage, ("SHA256SUMS",)) == hashes, "Full update manifest mismatch")
        archive = output / (PACKAGE + ".zip")
        zip_tree(stage, archive)
        print(f"PASS: app-only native update, unchanged signed kernel/provenance, full installer package: {archive}")
        return archive
    except Exception as error:
        metadata.update({"result": "APP_UPDATE_FAILED_NO_INSTALLABLE_ARCHIVE", "error": str(error), "native_commands": runner.commands})
        write_json(work / "BUILD-FAILED.json", metadata)
        archive = output / (PACKAGE + ".zip")
        archive.unlink(missing_ok=True)
        archive.with_suffix(archive.suffix + ".sha256").unlink(missing_ok=True)
        debug = output / (PACKAGE + "-app-native-debug")
        shutil.copytree(work, debug / "native-work")
        shutil.copytree(stage, debug / "incomplete-package")
        shutil.copytree(source, debug / "reviewed-sources")
        for path in (BUILDER, BASE_BUILDER):
            copy_file(path, debug / "builders" / path.name)
        (debug / "NOT-INSTALLABLE.txt").write_text("App build did not pass. Native diagnostics and incomplete assets only.\n")
        zip_tree(debug, output / (PACKAGE + "-app-native-debug.zip"))
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--freeze-reviewed-sources", action="store_true")
    mode.add_argument("--check-sources", action="store_true")
    parser.add_argument("--verify-native-request", type=Path)
    parser.add_argument("--repository-root", type=Path)
    args = parser.parse_args()
    source = args.source_dir.resolve()
    try:
        if args.freeze_reviewed_sources:
            freeze_sources(source)
            return 0
        review = check_sources(source)
        if args.verify_native_request:
            require(args.repository_root is not None, "Request verification requires --repository-root")
            verify_request(args.verify_native_request.resolve(), source, args.repository_root.resolve())
        if args.check_sources:
            return 0
        require(args.output_dir is not None, "Native app-only build requires --output-dir")
        build(source, args.output_dir.resolve(), review)
        return 0
    except (BuildError, OSError, ValueError, KeyError, zipfile.BadZipFile, plistlib.InvalidFileException) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
