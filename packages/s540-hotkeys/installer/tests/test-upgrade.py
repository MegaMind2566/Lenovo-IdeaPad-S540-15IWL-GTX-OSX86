#!/usr/bin/env python3
"""Isolated app-upgrade/rollback fixtures. No sudo, launchd, IOKit or kmutil access."""
import hashlib
import os
from pathlib import Path
import plistlib
import shlex
import shutil
import subprocess
import sys
import tempfile

SOURCE = Path(__file__).resolve().parents[1] / "tools/s540-common.sh"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def manifest(root, output):
    entries = ["D ."]
    for path in Path(root).rglob("*"):
        relative = "./" + path.relative_to(root).as_posix()
        entries.append("D " + relative if path.is_dir() else "F " + digest(path) + "  " + relative)
    Path(output).write_text("\n".join(sorted(entries)) + "\n")


STUB = r'''
import os, pathlib, plistlib, shutil, signal, subprocess, sys
p = pathlib.Path(os.environ["FIXTURE"])
mode = os.environ["CASE"]
tool, args = pathlib.Path(sys.argv[0]).name, sys.argv[1:]
def save(path, value):
    with open(path, "wb") as f: plistlib.dump(value, f, sort_keys=True)
def once(name):
    marker = p / name
    if marker.exists(): return False
    marker.touch(); return True
if tool == "sudo":
    while args and args[0] in ("-n", "-v"):
        option = args.pop(0)
        if option == "-v": sys.exit(0)
    os.execv(args[0], args)
if tool in ("chown", "codesign"): sys.exit(0)
if tool == "stat": print(os.getuid()); sys.exit(0)
if tool == "pgrep": sys.exit(1)
if tool == "kmutil":
    (p / "KMUTIL_CALLED").write_text(repr(args)); sys.exit(99)
if tool == "ditto":
    src, dst = map(pathlib.Path, args[-2:])
    if src.is_dir(): shutil.copytree(src, dst, dirs_exist_ok=True)
    else: shutil.copy2(src, dst)
    sys.exit(0)
if tool == "mv":
    result = subprocess.run(["/bin/mv"] + args).returncode
    if result == 0 and mode == "interrupt_rename" and "/upgrade-v1-" in args[-1] and once("signal-sent"):
        os.kill(os.getppid(), signal.SIGTERM)
    sys.exit(result)
if tool == "launchctl":
    state = p / "agent-active"
    if args[0] == "print": sys.exit(0 if state.exists() else 1)
    if args[0] == "bootout": state.unlink(missing_ok=True); sys.exit(0)
    if args[0] == "bootstrap":
        if mode in ("bootstrap_fail", "foreign_app") and once("bootstrap-failed"):
            if mode == "foreign_app": (p / "Applications/S540Tasti.app/Contents/data").write_text("foreign change")
            sys.exit(5)
        state.touch(); sys.exit(0)
    sys.exit(90)
if tool == "plutil":
    operation, path = args[0], pathlib.Path(args[-1])
    if operation == "-create": save(path, {}); sys.exit(0)
    with open(path, "rb") as f: obj = plistlib.load(f)
    key = args[1]
    if operation == "-extract":
        try:
            value = obj
            for bit in key.split("."): value = value[int(bit)] if isinstance(value, list) else value[bit]
            expected = args[args.index("-expect") + 1]
            typ = {"string": str, "integer": int, "bool": bool}[expected]
            if type(value) is not typ: sys.exit(1)
            print(str(value).lower() if type(value) is bool else value)
            sys.exit(0)
        except (KeyError, IndexError, ValueError): sys.exit(1)
    if mode == "receipt_fail" and key == "UpgradeBackupTreeSHA256" and once("receipt-failed"): sys.exit(7)
    option = args[2]
    value = {"-dictionary": {}, "-array": []}.get(option)
    if option == "-string": value = args[3]
    elif option == "-integer": value = int(args[3])
    elif option == "-bool": value = args[3] == "true"
    bits, target = key.split("."), obj
    for bit in bits[:-1]: target = target[int(bit)] if isinstance(target, list) else target[bit]
    last = bits[-1]
    if isinstance(target, list):
        index = int(last)
        if index == len(target): target.append(value)
        else: target[index] = value
    else: target[last] = value
    save(path, obj); sys.exit(0)
sys.exit(95)
'''


def run_case(case):
    with tempfile.TemporaryDirectory(prefix="s540-upgrade-test-") as directory:
        base = Path(directory)
        home, root, package, run = [base / x for x in ("Home", "Root", "Package", "Run")]
        app, kext = base / "Applications/S540Tasti.app", base / "Extensions/S540HotkeysVPC.kext"
        agent = home / "Library/LaunchAgents/org.s540.Hotkeys.plist"
        for path in (root, package / "assets", package / "tools", run, agent.parent, app / "Contents", kext / "Contents"):
            path.mkdir(parents=True, exist_ok=True)
        (app / "Contents/data").write_text("original app")
        (kext / "Contents/data").write_text("unchanged signed kernel")
        agent.write_text("original agent\n")
        (base / "agent-active").touch()
        new = package / "assets/S540Tasti.app"
        shutil.copytree(app, new)
        (new / "Contents/data").write_text("fixed app 0.1.3")
        (new / "Contents/MacOS").mkdir()
        binary = new / "Contents/MacOS/S540Tasti"
        binary.write_text("#!/bin/bash\nprintf '{}\\n'\n")
        binary.chmod(0o755)
        shutil.copytree(kext, package / "assets/S540HotkeysVPC.kext")
        manifest(app, root / "app.manifest")
        manifest(kext, root / "kext.manifest")
        for name in ("app", "kext"):
            shutil.copy2(root / (name + ".manifest"), package / ("tools/upgrade-v1-" + name + ".manifest"))
        shutil.copy2(root / "app.manifest", package / "tools/upgrade-v1.1-app.manifest")
        shutil.copy2(root / "app.manifest", package / "tools/upgrade-v1.2-app.manifest")
        installed_version = "0.1.0" if case == "success_v1" else "0.1.1" if case == "success" else "0.1.2"
        pinned_manifest = {"0.1.0": "upgrade-v1-app.manifest", "0.1.1": "upgrade-v1.1-app.manifest", "0.1.2": "upgrade-v1.2-app.manifest"}[installed_version]
        for name in ("upgrade-v1-app.manifest", "upgrade-v1.1-app.manifest", "upgrade-v1.2-app.manifest"):
            if name != pinned_manifest: (package / "tools" / name).write_text("other delivered app " + name + "\n")
        receipt = dict(Schema=1, OwnerUID=os.getuid(), KextPath=str(kext), AppPath=str(app), AgentPath=str(agent),
                       BundleID="org.s540.HotkeysVPC", LaunchLabel="org.s540.Hotkeys", Version=installed_version, State="ready",
                       KextManifestSHA256=digest(root / "kext.manifest"), AppManifestSHA256=digest(root / "app.manifest"),
                       AgentSHA256=digest(agent))
        prior, earlier = root / "upgrade-v1-PRIOR", root / "upgrade-v1-EARLIER"
        if installed_version != "0.1.0":
            receipt.update(AppVersion=installed_version, KextVersion="0.1.0")
            (prior / "S540Tasti.app/Contents").mkdir(parents=True)
            (prior / "S540Tasti.app/Contents/data").write_text("original 0.1.0 backup" if installed_version == "0.1.1" else "original 0.1.1 backup")
            manifest(prior, run / "prior.manifest")
            receipt.update(UpgradeBackupPath=str(prior), UpgradeBackupTreeSHA256=digest(run / "prior.manifest"))
        if installed_version == "0.1.2":
            (earlier / "S540Tasti.app/Contents").mkdir(parents=True)
            (earlier / "S540Tasti.app/Contents/data").write_text("original 0.1.0 backup")
            manifest(earlier, run / "earlier.manifest")
            receipt.update(PriorUpgradeBackupPath=str(earlier), PriorUpgradeBackupTreeSHA256=digest(run / "earlier.manifest"))
        if case == "duplicate_backup":
            receipt.update(PriorUpgradeBackupPath=str(prior), PriorUpgradeBackupTreeSHA256=receipt["UpgradeBackupTreeSHA256"])
        if case == "orphan_backup":
            del receipt["UpgradeBackupPath"]
            del receipt["UpgradeBackupTreeSHA256"]
        receipt_path = root / "receipt.plist"
        receipt_path.write_bytes(plistlib.dumps(receipt))
        original_receipt, original_agent, original_kernel = receipt_path.read_bytes(), agent.read_bytes(), (kext / "Contents/data").read_bytes()
        (package / "SHA256SUMS").write_text("fixture manifest\n")
        stub = base / "stubs"
        stub.mkdir()
        for name in ("sudo", "chown", "codesign", "stat", "pgrep", "kmutil", "ditto", "mv", "launchctl", "plutil"):
            path = stub / name
            path.write_text("#!" + sys.executable + " -S\n" + STUB)
            path.chmod(0o755)
        source = SOURCE.read_text()
        for old in ("/usr/bin/sudo", "/usr/sbin/chown", "/usr/bin/codesign", "/usr/bin/stat", "/usr/bin/pgrep",
                    "/usr/bin/kmutil", "/usr/bin/ditto", "/bin/mv", "/bin/launchctl", "/usr/bin/plutil"):
            source = source.replace(old, str(stub / Path(old).name))
        altered = base / "common-fixture.sh"
        altered.write_text(source)
        if case == "missing_kernel": shutil.rmtree(kext)
        if case == "tampered_app": (app / "Contents/data").write_text("unknown existing app")
        if case == "tampered_prior": (earlier / "S540Tasti.app/Contents/data").write_text("unknown prior backup")
        script = "\n".join([
            "set -euo pipefail", ". " + shlex.quote(str(altered)),
            *[name + "=" + shlex.quote(str(value)) for name, value in dict(
                S540_PACKAGE=package, S540_ROOT=root, S540_RECEIPT=receipt_path, S540_APP=app,
                S540_APP_BIN=app / "Contents/MacOS/S540Tasti", S540_KEXT=kext, S540_AGENT=agent,
                S540_RUN=run, S540_RUN_ID="FIXTURE", S540_V1_APP_MANIFEST_SHA256=digest(package / "tools/upgrade-v1-app.manifest"),
                S540_V11_APP_MANIFEST_SHA256=digest(package / "tools/upgrade-v1.1-app.manifest"),
                S540_V12_APP_MANIFEST_SHA256=digest(package / "tools/upgrade-v1.2-app.manifest"),
                S540_V1_KEXT_MANIFEST_SHA256=receipt["KextManifestSHA256"]).items()],
            's540_host() { :; }', 's540_new_run() { :; }', 's540_take_lock() { :; }',
            's540_protected() { [ -e "$1" ] && [ ! -L "$1" ]; }',
            's540_ready() { S540_DRIVER_STATE=Ready; return 0; }',
            's540_package() { s540_tree_manifest "$S540_PACKAGE/assets/S540Tasti.app" "$S540_RUN/app.manifest"; s540_tree_manifest "$S540_PACKAGE/assets/S540HotkeysVPC.kext" "$S540_RUN/kext.manifest"; }',
            's540_install',
        ])
        env = dict(os.environ, HOME=str(home), FIXTURE=str(base), CASE=case)
        result = subprocess.run(["/bin/bash", "-c", script], env=env, capture_output=True, text=True, timeout=60)
        details = result.stdout + result.stderr
        assert not (base / "KMUTIL_CALLED").exists(), details
        if case != "missing_kernel": assert (kext / "Contents/data").read_bytes() == original_kernel, details
        if case in ("success", "success_v1", "success_v12"):
            assert result.returncode == 0, details
            assert (app / "Contents/data").read_text() == "fixed app 0.1.3", details
            final = plistlib.loads(receipt_path.read_bytes())
            assert final["AppVersion"] == "0.1.3" and final["KextVersion"] == "0.1.0", details
            assert (Path(final["UpgradeBackupPath"]) / "S540Tasti.app/Contents/data").read_text() == "original app", details
            if installed_version != "0.1.0":
                assert final["PriorUpgradeBackupPath"] == str(prior), details
                assert final["PriorUpgradeBackupTreeSHA256"] == receipt["UpgradeBackupTreeSHA256"], details
                if installed_version == "0.1.2":
                    assert final["EarlierUpgradeBackupPath"] == str(earlier), details
                    assert final["EarlierUpgradeBackupTreeSHA256"] == receipt["PriorUpgradeBackupTreeSHA256"], details
                    # A damaged oldest backup must preserve the entire chain.
                    oldest_data = earlier / "S540Tasti.app/Contents/data"
                    original_oldest = oldest_data.read_bytes()
                    oldest_data.write_text("changed after upgrade")
                    cleanup = subprocess.run(["/bin/bash", "-c", script.rsplit("s540_install", 1)[0] + "s540_remove_upgrade_backup\n"],
                                             env=env, capture_output=True, text=True, timeout=30)
                    assert cleanup.returncode != 0, cleanup.stdout + cleanup.stderr
                    assert prior.exists() and earlier.exists() and Path(final["UpgradeBackupPath"]).exists(), details
                    oldest_data.write_bytes(original_oldest)
                # Exercise complete backup-chain removal without the system restore path.
                cleanup = subprocess.run(["/bin/bash", "-c", script.rsplit("s540_install", 1)[0] + "s540_remove_upgrade_backup\n"],
                                         env=env, capture_output=True, text=True, timeout=30)
                assert cleanup.returncode == 0, cleanup.stdout + cleanup.stderr
                assert not prior.exists() and not Path(final["UpgradeBackupPath"]).exists(), details
                assert not earlier.exists(), details
        else:
            assert result.returncode != 0, details
            if case == "foreign_app":
                assert (app / "Contents/data").read_text() == "foreign change", details
                assert (root / "upgrade-v1-FIXTURE/S540Tasti.app/Contents/data").read_text() == "original app", details
                assert "Ripristino dell’app non completato" in details, details
            else:
                expected = "unknown existing app" if case == "tampered_app" else "original app"
                assert (app / "Contents/data").read_text() == expected, details
                assert receipt_path.read_bytes() == original_receipt, details
                assert agent.read_bytes() == original_agent, details
        print("PASS:", case)


if __name__ == "__main__":
    for scenario in ("success", "success_v1", "success_v12", "missing_kernel", "tampered_app", "tampered_prior", "duplicate_backup", "orphan_backup", "bootstrap_fail", "receipt_fail", "interrupt_rename", "foreign_app"):
        run_case(scenario)
