#!/usr/bin/env python3
"""Attach the reviewed, unchanged audio ZIP to the existing v0.2.0 release.

No build, tag move, release creation, asset replacement, or EFI modification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import subprocess
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86"
TAG = "v0.2.0"
RELEASE_ID = 418900887
TARGET = "e612c52f765fb0592003fcb4b2d221168c247067"
NAME = "S540-audio-Tahoe-3.6.10-v1.zip"
SHA256 = "3059329f58463e1fefc4a2921cee8e5c49a249cfac5534301aaebcb071459be6"
ARCHIVE_SIZE = 148860
ASSETS = ROOT / "packages/audio-fresh/releases"
DOCS = ROOT / "docs/releases/v0.2.0"
ORIGINAL_ASSETS = {
    "S540-Tahoe-EFI-v0.2.0.zip": (660543394, 47102989, "sha256:659b1223c16b719a860c509571858b6685b0333b98c19222e480381fa601c039"),
    "S540-Tahoe-EFI-v0.2.0.zip.sha256": (660543398, 92, "sha256:92f756f87ec7097a3fde232034bd9d8ec059add288f7be21c7a4b7526765bc3f"),
}
DRIVER_FILES = {
    "Contents/Info.plist": "6f8f4695afae0a11ee2234d0290529c16615707a6d746cc52db58506ad6dcd6d",
    "Contents/MacOS/VoodooHDA": "4d47ff26768ce23ac06b363d0a7092a7c7b9463a9a6bebf6d796a9ad836d7003",
    "Contents/_CodeSignature/CodeResources": "6686de10a28a2fe11b36cbb86dcbacc827cfc4ea116b4dabf1845e5aee629e9b",
}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def validate_local():
    archive = ASSETS / NAME
    data = archive.read_bytes()
    require(len(data) == ARCHIVE_SIZE and sha(data) == SHA256, "Audio archive differs from reviewed ZIP")
    sidecar = ASSETS / (NAME + ".sha256")
    require(sidecar.read_bytes() == f"{SHA256}  {NAME}\n".encode(), "Incorrect checksum sidecar")
    with zipfile.ZipFile(archive) as z:
        require(z.testzip() is None, "ZIP CRC failure")
        names = z.namelist()
        require(len(names) == len(set(names)) == 12, "Unexpected or duplicate archive entries")
        base = NAME.removesuffix(".zip") + "/"
        for item in names:
            require(item.startswith(base) and ".." not in Path(item).parts and not Path(item).is_absolute(), "Unsafe archive entry")
        for rel, expected in DRIVER_FILES.items():
            require(sha(z.read(base + "assets/VoodooHDA.kext/" + rel)) == expected, "Original driver bytes changed")
        info = plistlib.loads(z.read(base + "assets/VoodooHDA.kext/Contents/Info.plist"))
        require(info["CFBundleVersion"] == "3.6.10", "Wrong driver version")
        for rel in ("INSTALLA-AUDIO.command", "VERIFICA-AUDIO.command", "RIMUOVI-AUDIO.command", "tools/audio_fresh.sh"):
            member = z.getinfo(base + rel)
            require((member.external_attr >> 16) & 0o777 == 0o755, "Lost executable permissions")
            subprocess.run(["bash", "-n"], input=z.read(member), check=True)
    return [archive, sidecar]


def api(endpoint, method="GET", body=None):
    command = ["gh", "api", endpoint, "--method", method]
    if body is not None:
        command.extend(["--input", "-"])
    return json.loads(subprocess.check_output(command, input=None if body is None else json.dumps(body).encode()))


def release():
    value = api(f"repos/{REPOSITORY}/releases/{RELEASE_ID}")
    require(value["id"] == RELEASE_ID and value["tag_name"] == TAG and value["target_commitish"] == TARGET,
            "Unexpected release identity")
    require(not value["draft"] and not value["prerelease"] and not value.get("immutable", False), "Release is not the expected published mutable release")
    latest = api(f"repos/{REPOSITORY}/releases/latest")
    require(latest["id"] == RELEASE_ID, "Latest release changed; refusing to update another release")
    ref = api(f"repos/{REPOSITORY}/git/ref/tags/{TAG}")
    require(ref["object"]["type"] == "commit" and ref["object"]["sha"] == TARGET, "Release tag changed")
    existing = {a["name"]: a for a in value["assets"]}
    require(len(existing) == len(value["assets"]), "Duplicate release asset names")
    for name, expected in ORIGINAL_ASSETS.items():
        a = existing.get(name, {})
        require((a.get("id"), a.get("size"), a.get("digest")) == expected and a.get("state") == "uploaded", "Original EFI asset changed")
    return value


def revised_body(body):
    previous = (DOCS / "AUDIO-PREVIOUS-SECTION.md").read_text().rstrip() + "\n\n"
    updated = (DOCS / "AUDIO-FRESH-INSTALL.md").read_text().rstrip() + "\n\n"
    start = "## Audio is a separate installed component\n"
    end = "## Remaining limitations\n"
    require(body.count(start) == body.count(end) == 1, "Release audio section is ambiguous")
    a, b = body.index(start), body.index(end)
    require(a < b, "Release sections are out of order")
    current = body[a:b]
    require(current in (previous, updated), "Audio section changed since review; refusing to overwrite it")
    return body[:a] + updated + body[b:]


def validate_asset(asset, path):
    data = path.read_bytes()
    require(asset["state"] == "uploaded" and asset["size"] == len(data) and asset["digest"] == "sha256:" + sha(data),
            "Published audio asset differs: " + path.name)


def publish():
    require(os.environ.get("GITHUB_REPOSITORY") == REPOSITORY, "Unexpected Actions repository")
    require(os.environ.get("GITHUB_REF") == "refs/heads/release/efi-v0.2.0-audio", "Unexpected publication branch")
    files = validate_local()
    before = release()
    revised_body(before["body"])  # Validate notes before any mutation.
    for path in files:
        current = release()
        matches = [a for a in current["assets"] if a["name"] == path.name]
        if matches:
            validate_asset(matches[0], path)
        else:
            subprocess.run(["gh", "release", "upload", TAG, str(path), "--repo", REPOSITORY], check=True)
        current = release()
        asset = next(a for a in current["assets"] if a["name"] == path.name)
        validate_asset(asset, path)
        with tempfile.TemporaryDirectory(prefix="audio-release-verify-") as tmp:
            subprocess.run(["gh", "release", "download", TAG, "--repo", REPOSITORY,
                            "--pattern", path.name, "--dir", tmp], check=True)
            require((Path(tmp) / path.name).read_bytes() == path.read_bytes(), "Downloaded audio asset differs")
    current = release()
    old_body = current["body"]
    new_body = revised_body(old_body)
    if new_body != old_body:
        require(release()["body"] == old_body, "Release notes changed during upload")
        api(f"repos/{REPOSITORY}/releases/{RELEASE_ID}", "PATCH", {"body": new_body})
    after = release()
    require(after["body"] == new_body, "Published instructions differ")
    for path in files:
        validate_asset(next(a for a in after["assets"] if a["name"] == path.name), path)
    print("Audio ZIP and checksum attached and downloaded bytes verified; original EFI assets preserved.")
    print(after["html_url"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check-only", action="store_true")
    group.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    if args.publish:
        publish()
    else:
        validate_local()
        print("Exact audio archive, original driver hashes, shell syntax and checksum verified.")


if __name__ == "__main__":
    main()
