#!/usr/bin/env python3
"""Build the reviewed S540 hotkey package; never load or install its driver.

Source review is frozen explicitly on the development host. Native CI verifies
that freeze, compiles once, runs only pure tests, signs and records the ABI.
Unknown kernel imports prevent an installable archive. A failure archive keeps
the native objects and diagnostics available for review without another build.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import plistlib
import re
import shutil
import stat
import struct
import subprocess
import sys
import zipfile

PACKAGE = "S540-Tasti-v1"
VERSION = "0.1.0"
KERNEL = "S540HotkeysVPC"
KERNEL_ID = "org.s540.HotkeysVPC"
APP = "S540Tasti"
APP_ID = "org.s540.Hotkeys"
SDK_PIN = "3f750085caa17ec3a7880f11c11bf4f48cd6a164"
SOURCE_REVIEW = "SOURCE-REVIEW.json"
POLICY_NAME = "s540-hotkeys-abi-allowlist.json"
BUILDER = Path(__file__).resolve()
POLICY = BUILDER.with_name(POLICY_NAME)
WRAPPERS = ("INSTALLA-TASTI.command", "RIPRISTINA-TASTI.command", "VERIFICA-TASTI.command")
LIBRARIES = {
    "com.apple.iokit.IOACPIFamily": "1.2.0",
    "com.apple.kpi.iokit": "8.0.0",
    "com.apple.kpi.libkern": "8.0.0",
    "com.apple.kpi.mach": "8.0.0",
}
REQUIRED = (
    "kernel/S540HotkeysVPC.cpp", "kernel/S540HotkeysVPC.hpp",
    "kernel/ProtocolCore.hpp", "kernel/tests/ProtocolCoreTests.cpp",
    "kernel/Info.plist", "kernel/LICENSE", "app/S540Tasti.m",
    "app/HotkeyPolicy.h", "app/policy_tests.c", "app/Info.plist", "app/LICENSE",
    *("installer/" + name for name in WRAPPERS),
    "installer/tools/s540-common.sh", "installer/tests/test-manifest.sh",
    "LEGGIMI.txt", "README.md", "LICENSE", "licenses/NOTICES.txt", "licenses/GPL-2.0-YogaSMC.txt",
)
MODULE_INFO = r'''#include <mach/kmod.h>
extern "C" {
extern kern_return_t _start(kmod_info_t *, void *);
extern kern_return_t _stop(kmod_info_t *, void *);
KMOD_EXPLICIT_DECL(org.s540.HotkeysVPC, "0.1.0", _start, _stop)
__attribute__((visibility("hidden"))) kmod_start_func_t *_realmain = 0;
__attribute__((visibility("hidden"))) kmod_stop_func_t *_antimain = 0;
__attribute__((visibility("hidden"))) int _kext_apple_cc = __APPLE_CC__;
}
'''


class BuildError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise BuildError(message)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_hash(path: Path) -> str:
    return digest(path.read_bytes())


def write_json(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def tree_hashes(root: Path, exclude: tuple[str, ...] = ()) -> dict[str, str]:
    require(root.is_dir() and not root.is_symlink(), f"Missing real source directory: {root}")
    files = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        require(not path.is_symlink(), f"Symlinks are not accepted: {relative}")
        require(not any(c in relative for c in "\n\r\\"), f"Invalid source path: {relative!r}")
        require(not any(p.startswith(".") or p == "__pycache__" for p in path.relative_to(root).parts),
                f"Unreviewed generated/hidden path: {relative}")
        if path.is_file() and relative not in exclude:
            files[relative] = file_hash(path)
    return files


def validate_layout(source: Path) -> dict[str, str]:
    hashes = tree_hashes(source, (SOURCE_REVIEW,))
    require(set(REQUIRED) <= hashes.keys(), "Missing required source files: " +
            ", ".join(sorted(set(REQUIRED) - hashes.keys())))
    kernel = plistlib.loads((source / "kernel/Info.plist").read_bytes())
    app = plistlib.loads((source / "app/Info.plist").read_bytes())
    for info, identifier, executable, kind in (
        (kernel, KERNEL_ID, KERNEL, "KEXT"), (app, APP_ID, APP, "APPL")
    ):
        require(info.get("CFBundleIdentifier") == identifier, "Wrong bundle identifier")
        require(info.get("CFBundleExecutable") == executable, "Wrong bundle executable")
        require(info.get("CFBundlePackageType") == kind, "Wrong bundle package type")
        require(info.get("CFBundleVersion") == VERSION and
                info.get("CFBundleShortVersionString") == VERSION, "Wrong bundle version")
    personality = kernel.get("IOKitPersonalities", {})
    require(set(personality) == {KERNEL}, "Expected one exact driver personality")
    require(personality[KERNEL].get("CFBundleIdentifier") == KERNEL_ID and
            personality[KERNEL].get("IOClass") == KERNEL and
            personality[KERNEL].get("IOProviderClass") == "IOACPIPlatformDevice" and
            personality[KERNEL].get("IONameMatch") == "VPC2004", "Driver matching contract changed")
    require(kernel.get("OSBundleLibraries") == LIBRARIES, "Driver library contract changed")
    require(app.get("LSMinimumSystemVersion") == "13.0" and app.get("LSUIElement") is True,
            "App deployment/menu-bar contract changed")
    kernel_text = "\n".join((source / p).read_text() for p in
                            ("kernel/S540HotkeysVPC.cpp", "kernel/S540HotkeysVPC.hpp", "kernel/ProtocolCore.hpp"))
    require("0xFE0D0014" in kernel_text and "VPC0" in kernel_text,
            "Missing exact firmware identity guard")
    require("kIOReturnUnsupported" in kernel_text and "setProperties" in kernel_text,
            "Missing denial of user-triggered EC command API")
    require("GNU GENERAL PUBLIC LICENSE" in (source / "kernel/LICENSE").read_text(), "Missing kernel GPL license")
    require("MIT License" in (source / "app/LICENSE").read_text(), "Missing app MIT license")
    for relative in ("installer/" + x for x in WRAPPERS):
        result = subprocess.run(["/bin/bash", "-n", str(source / relative)], capture_output=True, text=True)
        require(result.returncode == 0, f"Shell syntax: {relative}: {result.stderr}")
    result = subprocess.run(["/bin/bash", "-n", str(source / "installer/tools/s540-common.sh")],
                            capture_output=True, text=True)
    require(result.returncode == 0, "Shell syntax: s540-common.sh: " + result.stderr)
    result = subprocess.run(["/bin/bash", str(source / "installer/tests/test-manifest.sh")],
                            capture_output=True, text=True, timeout=30)
    require(result.returncode == 0, "Installer pure manifest fixtures: " + result.stdout + result.stderr)
    return hashes


def freeze_sources(source: Path) -> None:
    hashes = validate_layout(source)
    policy = json.loads(POLICY.read_text())
    require(policy.get("sdk_commit") == SDK_PIN and policy.get("schema") == 1, "Wrong ABI policy")
    write_json(source / SOURCE_REVIEW, {
        "schema": 1,
        "purpose": "Explicit source review freeze; hashes alone do not assert hardware validation.",
        "sdk_commit": SDK_PIN,
        "abi_policy_sha256": file_hash(POLICY),
        "builder_sha256": file_hash(BUILDER),
        "files": hashes,
    })
    print(f"Frozen {len(hashes)} reviewed source files: {source / SOURCE_REVIEW}")


def check_sources(source: Path) -> dict:
    actual = validate_layout(source)
    review = json.loads((source / SOURCE_REVIEW).read_text())
    require(review.get("schema") == 1 and review.get("sdk_commit") == SDK_PIN, "Wrong source review schema/SDK")
    require(review.get("files") == actual, "Sources differ from SOURCE-REVIEW.json; finish review and freeze again")
    require(review.get("abi_policy_sha256") == file_hash(POLICY), "ABI policy changed after source review")
    require(review.get("builder_sha256") == file_hash(BUILDER), "Builder changed after source review")
    print(f"PASS: {len(actual)} exact source hashes, bundle contracts, licenses, shell syntax, ABI-policy binding")
    return review


def verify_request(request: Path, source: Path, repository: Path) -> None:
    data = json.loads(request.read_text())
    require(data.get("schema") == 1, "Wrong native request schema")
    paths = {BUILDER.relative_to(repository).as_posix(), POLICY.relative_to(repository).as_posix(),
             ".github/workflows/build-s540-hotkeys.yml"}
    paths.update(path.relative_to(repository).as_posix() for path in source.rglob("*") if path.is_file())
    expected = {p: file_hash(repository / p) for p in sorted(paths)}
    require(data.get("files") == expected, "Native request must bind exactly builder, ABI policy, workflow and all package sources")
    print(f"PASS: native request binds {len(expected)} files")


def macho_symbols(path: Path, filetype: int) -> dict:
    data = path.read_bytes()
    require(len(data) >= 32 and data[:4] == b"\xcf\xfa\xed\xfe", f"Not thin little-endian Mach-O64: {path}")
    _, cpu, subtype, kind, count, commands_size, _, _ = struct.unpack_from("<8I", data)
    require(cpu == 0x01000007 and kind == filetype, f"Wrong architecture or Mach-O type: {path}")
    require(commands_size + 32 <= len(data), "Truncated Mach-O load commands")
    offset, symtab = 32, None
    for _ in range(count):
        require(offset + 8 <= 32 + commands_size, "Truncated load command")
        command, size = struct.unpack_from("<II", data, offset)
        require(size >= 8 and offset + size <= 32 + commands_size, "Invalid load command size")
        if command == 2:
            require(size >= 24 and symtab is None, "Invalid/duplicate symbol table")
            symtab = struct.unpack_from("<4I", data, offset + 8)
        offset += size
    require(offset == 32 + commands_size and symtab is not None, "Missing symbol table")
    table, number, strings, strings_size = symtab
    require(table + number * 16 <= len(data) and strings + strings_size <= len(data), "Truncated symbol/string table")
    defined, undefined = set(), set()
    for index in range(number):
        name_offset, type_, section, desc, value = struct.unpack_from("<IBBHQ", data, table + index * 16)
        if type_ & 0xe0:  # N_STAB debug entries do not describe linker imports.
            continue
        require(name_offset < strings_size, "Symbol name offset outside string table")
        end = data.find(b"\0", strings + name_offset, strings + strings_size)
        require(end >= 0, "Unterminated symbol name")
        name = data[strings + name_offset:end].decode("ascii")
        if not name:
            continue
        if type_ & 0x0e:
            defined.add(name)
        elif type_ & 1:
            require(value == 0, f"Unexpected common symbol: {name}")
            undefined.add(name)
    return {"cpu": cpu, "cpu_subtype": subtype, "filetype": kind,
            "defined": sorted(defined), "undefined": sorted(undefined), "sha256": digest(data)}


def zip_tree(root: Path, archive: Path) -> None:
    """Stable order, permissions and timestamp; rejects links and metadata files."""
    require(not archive.exists(), f"Refusing to replace existing archive: {archive}")
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as output:
        for path in sorted(root.rglob("*")):
            require(not path.is_symlink(), f"Symlink in package: {path}")
            if not path.is_file():
                continue
            name = path.relative_to(root.parent).as_posix()
            require(not any(p == "__MACOSX" or p.startswith("._") for p in Path(name).parts), "Unexpected archive metadata")
            mode = 0o755 if path.stat().st_mode & 0o111 else 0o644
            entry = zipfile.ZipInfo(name, date_time=(2026, 10, 21, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = (stat.S_IFREG | mode) << 16
            output.writestr(entry, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    with zipfile.ZipFile(archive) as check:
        require(check.testzip() is None, "ZIP integrity failure")
        require(len(check.namelist()) == len(set(check.namelist())), "Duplicate archive member")
    archive.with_suffix(archive.suffix + ".sha256").write_text(f"{file_hash(archive)}  {archive.name}\n")


class Runner:
    def __init__(self, work: Path):
        self.work = work
        self.commands: list[dict] = []

    def run(self, command: list[str], *, label: str, input_: str | None = None, timeout: int = 180) -> str:
        number = len(self.commands) + 1
        record = {"label": label, "argv": command}
        self.commands.append(record)
        try:
            result = subprocess.run(command, input=input_, text=True, capture_output=True, timeout=timeout)
        except (OSError, subprocess.TimeoutExpired) as error:
            record.update({"error": str(error), "passed": False})
            write_json(self.work / "commands.json", self.commands)
            raise BuildError(f"{label}: {error}") from error
        record.update({"exit_code": result.returncode, "passed": result.returncode == 0,
                       "stdout_sha256": digest(result.stdout.encode()), "stderr_sha256": digest(result.stderr.encode())})
        safe_label = re.sub(r"[^a-zA-Z0-9_-]", "-", label)
        (self.work / f"{number:02d}-{safe_label}.stdout.txt").write_text(result.stdout)
        (self.work / f"{number:02d}-{safe_label}.stderr.txt").write_text(result.stderr)
        write_json(self.work / "commands.json", self.commands)
        require(result.returncode == 0, f"{label} failed ({result.returncode}):\n{result.stdout}\n{result.stderr}")
        return result.stdout.strip()


def inspect_imports(binary: Path, runner: Runner, source: Path, output: Path) -> dict:
    result = macho_symbols(binary, 11)
    # Keep the native tool's actual output as well as independently parsed nlist64.
    native = runner.run(["xcrun", "nm", "-u", "-j", str(binary)], label="kernel-native-undefined-symbols")
    require(set(native.splitlines()) == set(result["undefined"]), "Native nm and independent import parser disagree")
    native_defined = runner.run(["xcrun", "nm", "-j", str(binary)], label="kernel-native-all-symbols")
    require(set(result["defined"]) <= set(native_defined.splitlines()), "Native nm and defined-symbol parser disagree")
    needed = {"_kmod_info", "__start", "__stop", "__realmain", "__antimain", "__kext_apple_cc"}
    require(needed <= set(result["defined"]), "Missing standard KMOD runtime declarations")
    mangled = [s[1:] if s.startswith("__Z") else s for s in result["undefined"]]
    decoded = runner.run(["xcrun", "c++filt", "-n"], input_="\n".join(mangled) + "\n", label="kernel-demangle-symbols").splitlines()
    require(len(decoded) == len(mangled), "Demangler changed symbol count")
    policy = json.loads(POLICY.read_text())
    require(policy.get("schema") == 1 and policy.get("sdk_commit") == SDK_PIN, "Invalid ABI policy")
    sources = "\n".join((source / p).read_text() for p in policy["bound_source_files"])
    approved, unknown = [], []
    for symbol, demangled in zip(result["undefined"], decoded):
        rule = policy["exact_mangled"].get(symbol) or policy["exact_demangled"].get(demangled)
        if rule and all(token in sources for token in rule.get("source_tokens", [])):
            approved.append({"symbol": symbol, "demangled": demangled, "reason": rule["reason"]})
        else:
            unknown.append({"symbol": symbol, "demangled": demangled})
    result.update({"imports": approved, "unapproved_imports": unknown,
                   "abi_policy_sha256": file_hash(POLICY), "sdk_commit": SDK_PIN,
                   "bound_source_hashes": {p: file_hash(source / p) for p in policy["bound_source_files"]},
                   "required_module_symbols": sorted(needed)})
    write_json(output, result)
    return result


def copy_file(source: Path, destination: Path, executable: bool = False) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(source.read_bytes())
    destination.chmod(0o755 if executable else 0o644)


def native_build(source: Path, output: Path, sdk: Path, review: dict) -> Path:
    require(platform.system() == "Darwin" and platform.machine() == "x86_64", "Native Intel macOS is required; no cross-build or hardware test is performed here")
    output.mkdir(parents=True, exist_ok=True)
    require(not (output / PACKAGE).exists(), f"Output package already exists: {output / PACKAGE}")
    require(not list(output.glob(PACKAGE + "*.zip")), "Output archives already exist; use a new output directory")
    stage = output / PACKAGE
    stage.mkdir()
    work = output / "native-work"
    require(not work.exists(), "Native work directory already exists; use a new output directory")
    work.mkdir()
    runner = Runner(work)
    metadata = {"schema": 1, "package": PACKAGE, "version": VERSION,
                "native_build": False, "target_hardware_tested": False, "kernel_loaded": False,
                "source_review": review, "source_review_sha256": file_hash(source / SOURCE_REVIEW),
                "builder_sha256": file_hash(BUILDER), "abi_policy_sha256": file_hash(POLICY),
                "mac_kernel_sdk_commit": SDK_PIN, "runner_os": platform.platform(),
                "runner_arch": platform.machine(), "ci_commit": os.environ.get("GITHUB_SHA", ""),
                "ci_run_id": os.environ.get("GITHUB_RUN_ID", ""),
                "ci_repository": os.environ.get("GITHUB_REPOSITORY", ""),
                "validation_scope": "Compilation, pure fixtures, code signatures, public ABI import policy and read-only dependency resolution; no driver load or physical action."}
    try:
        require((sdk / "Headers/IOKit/IOService.h").is_file() and (sdk / "Library/x86_64/libkmod.a").is_file(), "Incomplete MacKernelSDK")
        require(runner.run(["git", "-C", str(sdk), "rev-parse", "HEAD"], label="sdk-commit") == SDK_PIN, "Wrong SDK commit")
        require(runner.run(["git", "-C", str(sdk), "status", "--porcelain", "--untracked-files=all"], label="sdk-clean") == "", "SDK contains modified or untracked files")
        metadata["clang_version"] = runner.run(["xcrun", "clang", "--version"], label="compiler-version")
        metadata["ld_version"] = runner.run(["xcrun", "ld", "-version_details"], label="linker-version")
        metadata["macos_version"] = runner.run(["sw_vers"], label="macos-version")
        metadata["xcode_version"] = runner.run(["xcodebuild", "-version"], label="xcode-version")
        # Exercise the installer's read-only CLI shape on this macOS release.
        loaded = runner.run(["sudo", "-n", "/usr/bin/kmutil", "showloaded", "--list-only", "--bundle-identifier", KERNEL_ID],
                            label="read-only-showloaded-cli-contract")
        require(KERNEL_ID not in loaded, "The hotkey driver is unexpectedly loaded on the build runner")
        # Pure protocol and policy tests run before compiling the real components.
        protocol_test = work / "protocol-tests"
        runner.run(["xcrun", "clang++", "-std=c++14", "-arch", "x86_64", "-Wall", "-Wextra", "-Werror", "-O2",
                    str(source / "kernel/tests/ProtocolCoreTests.cpp"), "-o", str(protocol_test)], label="compile-protocol-fixtures")
        runner.run([str(protocol_test)], label="pure-protocol-fixtures")
        policy_test = work / "policy-tests"
        runner.run(["xcrun", "clang", "-std=c11", "-arch", "x86_64", "-Wall", "-Wextra", "-Werror", "-O2",
                    str(source / "app/policy_tests.c"), "-o", str(policy_test)], label="compile-policy-fixtures")
        runner.run([str(policy_test)], label="pure-companion-policy-fixtures")
        kext = stage / "assets" / (KERNEL + ".kext")
        app = stage / "assets" / (APP + ".app")
        kernel_bin = kext / "Contents/MacOS" / KERNEL
        app_bin = app / "Contents/MacOS" / APP
        kernel_bin.parent.mkdir(parents=True)
        app_bin.parent.mkdir(parents=True)
        flags = ["-target", "x86_64-apple-macos10.15", "-std=c++14", "-mkernel", "-fapple-kext", "-fno-builtin",
                 "-fno-exceptions", "-fno-rtti", "-fno-common", "-fno-stack-protector", "-fno-threadsafe-statics",
                 "-nostdinc", "-DKERNEL", "-D__KERNEL__", "-I", str(sdk / "Headers"), "-Wall", "-Wextra", "-Werror", "-O2"]
        shim = work / "module-info.cpp"
        shim.write_text(MODULE_INFO)
        for file, name in ((source / "kernel/S540HotkeysVPC.cpp", "driver"), (shim, "module-info")):
            runner.run(["xcrun", "clang++", *flags, "-c", str(file), "-o", str(work / (name + ".o"))], label="compile-" + name)
        runner.run(["xcrun", "ld", "-arch", "x86_64", "-kext", "-undefined", "dynamic_lookup", "-no_function_starts",
                    "-o", str(kernel_bin), str(work / "driver.o"), str(work / "module-info.o"),
                    str(sdk / "Library/x86_64/libkmod.a")], label="link-kernel")
        copy_file(source / "kernel/Info.plist", kext / "Contents/Info.plist")
        frameworks = ("Foundation", "Cocoa", "IOKit", "CoreAudio", "CoreWLAN", "IOBluetooth", "ApplicationServices")
        app_command = ["xcrun", "clang", "-arch", "x86_64", "-mmacosx-version-min=13.0", "-fobjc-arc",
                       "-Wall", "-Wextra", "-Werror", "-O2", str(source / "app/S540Tasti.m"), "-o", str(app_bin)]
        for framework in frameworks:
            app_command.extend(["-framework", framework])
        runner.run(app_command, label="compile-link-app")
        copy_file(source / "app/Info.plist", app / "Contents/Info.plist")
        for bundle, identifier, binary, kind in ((kext, KERNEL_ID, kernel_bin, 11), (app, APP_ID, app_bin, 2)):
            binary.chmod(0o755)
            require(runner.run(["xcrun", "lipo", "-archs", str(binary)], label="architecture-" + identifier) == "x86_64", "Unexpected fat/alternate architecture")
            macho_symbols(binary, kind)
            runner.run(["/usr/bin/plutil", "-lint", str(bundle / "Contents/Info.plist")], label="plist-" + identifier)
            runner.run(["/usr/bin/codesign", "--force", "--sign", "-", "--timestamp=none", "--identifier", identifier, str(bundle)], label="sign-" + identifier)
            runner.run(["/usr/bin/codesign", "--verify", "--strict", "--verbose=2", str(bundle)], label="verify-signature-" + identifier)
        runner.run([str(app_bin), "--self-test"], label="app-pure-self-test")
        kernel_manifest = inspect_imports(kernel_bin, runner, source, work / "kernel-symbols.json")
        app_manifest = macho_symbols(app_bin, 2)
        require(not any("IOBluetoothPreferenceSetControllerPowerState" in s for s in app_manifest["undefined"]),
                "Bluetooth private setter must not be a direct binary import")
        write_json(work / "app-symbols.json", app_manifest)
        # Resolves declared OSBundleLibraries only. This command never loads a kext.
        dependency_xml = runner.run(["sudo", "-n", "/usr/bin/kmutil", "libraries", "--bundle-path", str(kext), "--xml"],
                                    label="read-only-kernel-library-resolution")
        (work / "kmutil-libraries.xml").write_text(dependency_xml + "\n")
        require(dependency_xml, "kmutil dependency resolution returned no report")
        metadata.update({"native_build": True, "kernel_binary_sha256": file_hash(kernel_bin),
                         "app_binary_sha256": file_hash(app_bin), "kernel_abi": kernel_manifest,
                         "app_abi": app_manifest, "native_commands": runner.commands,
                         "kmutil_libraries_sha256": digest((dependency_xml + "\n").encode()),
                         "libkmod_sha256": file_hash(sdk / "Library/x86_64/libkmod.a")})
        # Recheck source after native work; no changing source tree may be sealed.
        require(check_sources(source) == review, "Sources changed during native compilation")
        require(not kernel_manifest["unapproved_imports"], "Unreviewed kernel imports; native-debug.zip retains the exact signed objects and full manifest for ABI review")
        for name in WRAPPERS:
            copy_file(source / "installer" / name, stage / name, True)
        copy_file(source / "installer/tools/s540-common.sh", stage / "tools/s540-common.sh", True)
        copy_file(source / "LEGGIMI.txt", stage / "LEGGIMI.txt")
        copy_file(source / "README.md", stage / "README.md")
        copy_file(source / "LICENSE", stage / "LICENSE")
        for relative in sorted(tree_hashes(source)):
            copy_file(source / relative, stage / "src" / relative, relative.endswith((".command", ".sh")))
        copy_file(source / "kernel/LICENSE", stage / "licenses/kernel-GPL-2.0.txt")
        copy_file(source / "app/LICENSE", stage / "licenses/app-MIT.txt")
        for license_file in sorted((source / "licenses").rglob("*")):
            if license_file.is_file():
                copy_file(license_file, stage / "licenses" / license_file.relative_to(source / "licenses"))
        copy_file(BUILDER, stage / "src/builders" / BUILDER.name)
        copy_file(POLICY, stage / "src/builders" / POLICY.name)
        copy_file(shim, stage / "src/builders/module-info.cpp")
        for name in ("kernel-symbols.json", "app-symbols.json", "kmutil-libraries.xml", "commands.json"):
            copy_file(work / name, stage / "validation" / name)
        # Raw command logs include compiler output and code-signature checks.
        for log in sorted(work.glob("*.txt")):
            copy_file(log, stage / "validation" / log.name)
        metadata["result"] = "NATIVE_BUILD_VERIFIED_TARGET_NOT_TESTED"
        write_json(stage / "BUILD.json", metadata)
        hashes = tree_hashes(stage)
        (stage / "SHA256SUMS").write_text("".join(f"{h}  {p}\n" for p, h in hashes.items()))
        require(set(tree_hashes(stage)) == set(hashes) | {"SHA256SUMS"}, "Manifest does not cover package")
        for relative, expected in hashes.items():
            require(file_hash(stage / relative) == expected, "Package changed while sealing")
        archive = output / (PACKAGE + ".zip")
        zip_tree(stage, archive)
        print(f"PASS: native build, pure fixtures, exact ABI policy, signatures, read-only library resolution and reproducible ZIP: {archive}")
        return archive
    except Exception as error:
        metadata.update({"result": "BUILD_FAILED_NO_INSTALLABLE_ARCHIVE", "error": str(error), "native_commands": runner.commands})
        write_json(work / "BUILD-FAILED.json", metadata)
        debug = output / (PACKAGE + "-native-debug")
        debug.mkdir(exist_ok=True)
        shutil.copytree(work, debug / "native-work", dirs_exist_ok=True)
        if stage.exists():
            shutil.copytree(stage, debug / "incomplete-package", dirs_exist_ok=True)
        shutil.copytree(source, debug / "reviewed-sources", dirs_exist_ok=True)
        copy_file(BUILDER, debug / "builder" / BUILDER.name)
        copy_file(POLICY, debug / "builder" / POLICY.name)
        (debug / "NOT-INSTALLABLE.txt").write_text("Build did not pass. These are native diagnostics and incomplete assets, not an installer.\n")
        zip_tree(debug, output / (PACKAGE + "-native-debug.zip"))
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--sdk-path", type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--freeze-reviewed-sources", action="store_true", help="Explicitly record hashes after human/agent source review; no build")
    mode.add_argument("--check-sources", action="store_true", help="Cross-platform frozen source validation only")
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
            require(args.repository_root is not None, "--repository-root is required for request verification")
            verify_request(args.verify_native_request.resolve(), source, args.repository_root.resolve())
        if args.check_sources:
            return 0
        require(args.output_dir is not None and args.sdk_path is not None, "Native build requires --output-dir and --sdk-path")
        native_build(source, args.output_dir.resolve(), args.sdk_path.resolve(), review)
        return 0
    except (BuildError, OSError, ValueError, plistlib.InvalidFileException) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
