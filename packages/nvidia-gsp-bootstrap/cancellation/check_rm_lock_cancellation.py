#!/usr/bin/env python3
"""Exercise patched original lock and nvport bodies with actual local services."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

SOURCES = {
    "src/nvidia/src/kernel/core/locks.c": "5fe7602495678926921119c3c69a03b4febc243fc53e7e52000bc661a3a5ee62",
    "src/nvidia/src/kernel/rmapi/rmapi.c": "cf0f6f8df903b9e39061ffa7cde0c528122c2aec7f10ba6ccbee82bcef6a6fe5",
    "src/nvidia/src/libraries/nvport/sync/sync_unix_kernel_os.c": "251ec5da384f6cddd51c3ebbef09fde118734687c83955c3a085652bcce53372",
}
PORT = "src/nvidia/src/libraries/nvport/sync/sync_unix_kernel_os.c"
GPU = "src/nvidia/src/kernel/core/locks.c"
API = "src/nvidia/src/kernel/rmapi/rmapi.c"
FUNCTIONS = [(PORT, name) for name in [
    "portSyncSpinlockAcquire", "portSyncSpinlockRelease", "portSyncSemaphoreAcquire",
    "portSyncSemaphoreRelease", "portSyncRwLockAcquireRead", "portSyncRwLockAcquireReadConditional",
    "portSyncRwLockAcquireWrite", "portSyncRwLockAcquireWriteConditional", "portSyncRwLockReleaseRead",
    "portSyncRwLockReleaseWrite", "portSyncExSafeToSleep", "portSyncExSafeToWake",
]] + [(GPU, name) for name in [
    "_gpuInstLoopHead", "_gpuInstLoopNext", "_gpuInstLoopTail", "_gpuInstLoopPrev",
    "_gpuInstLoopShouldContinue", "_rmGpuAllocLockIsOwner", "_rmGpuLockIsOwner",
    "rmGpuLocksGetOwnedMask", "_rmGpuLocksRelease", "_rmGpuLocksAcquire",
]] + [(API, name) for name in ["rmapiLockIsOwner", "rmapiLockAcquire", "rmapiLockRelease"]]

def extract(source: str, name: str) -> str:
    starts = [match for match in re.finditer(r"(?m)^(?:static\s+)?(?:inline\s+)?(?:NV_STATUS|NvBool|NvU32|void)\s+" + re.escape(name) + r"\s*\(", source)
              if ";" not in source[match.end():source.index("{", match.end())]]
    if len(starts) != 1:
        raise ValueError(f"Expected one source definition for {name}: {len(starts)}")
    start = starts[0].start()
    brace = source.index("{", starts[0].end())
    token = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|/\*.*?\*/|//[^\n]*|[{}]', re.S)
    depth = 0
    for match in token.finditer(source, brace):
        if match.group() == "{": depth += 1
        elif match.group() == "}":
            depth -= 1
            if depth == 0: return source[start:match.end()] + "\n"
    raise ValueError(f"Unbalanced definition: {name}")

def run(argv: list[str], **kwargs) -> subprocess.CompletedProcess:
    result = subprocess.run(argv, text=True, capture_output=True, **kwargs)
    if result.returncode:
        raise RuntimeError(f"{argv!r}\n{result.stdout}\n{result.stderr}")
    return result

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cc", default=os.environ.get("CC", "clang"))
    parser.add_argument("--cxx", default=os.environ.get("CXX", "clang++"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    here = Path(__file__).resolve().parent
    services = here.parent.parent / "nvidia-darwin-services/src"
    patch = here / "rm-lock-cancellation-prospective.patch"
    report = {"format": 1, "upstream_commit": "1a82fbfda8f321b056eb3568850f9316c5e465c5",
              "patch_sha256": hashlib.sha256(patch.read_bytes()).hexdigest(), "sources": SOURCES,
              "actual_original_bodies": len(FUNCTIONS), "variants": {}}
    for variant in ("baseline", "candidate"):
        root = args.output / variant
        root.mkdir(exist_ok=True)
        for relative, digest in SOURCES.items():
            data = (args.upstream / relative).read_bytes()
            if hashlib.sha256(data).hexdigest() != digest:
                raise ValueError(f"Pinned original source changed: {relative}")
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        if variant == "candidate":
            run(["git", "apply", "--check", str(patch)], cwd=root)
            run(["git", "apply", str(patch)], cwd=root)
        bodies = [f'\n#line 1 "{relative}:{name}"\n' + extract((root / relative).read_text(), name)
                  for relative, name in FUNCTIONS]
        (root / "rm_lock_actual_bodies.inc").write_text("\n".join(bodies))
        for mode in ("plain", "sanitized"):
            sanitize = ["-fsanitize=address,undefined,function", "-fno-sanitize-recover=all", "-fno-omit-frame-pointer"] if mode == "sanitized" else []
            common = ["-O1", "-g", "-Wall", "-Wextra", "-Werror", "-Wno-unused-parameter"]
            cancel_object = root / f"{mode}-cancellation.o"
            run([args.cc, "-std=gnu11", *common, *sanitize, "-c", str(here / "S540NvidiaGspCancellation.c"), "-o", str(cancel_object)])
            binary = root / mode
            command = [args.cxx, "-std=gnu++17", *common, *sanitize, "-pthread", "-I", str(here), "-I", str(root),
                       str(here / "check_rm_lock_cancellation_native.cpp"),
                       str(services / "S540NvidiaDarwinPlatform.cpp"), str(services / "S540NvidiaDarwinSync.cpp"),
                       str(cancel_object), "-o", str(binary)]
            run(command)
            executed = run([str(binary)] + (["--baseline"] if variant == "baseline" else []), timeout=20)
            result = json.loads(executed.stdout)
            (root / f"{mode}.json").write_text(json.dumps(result, indent=2) + "\n")
            report["variants"][f"{variant}_{mode}"] = result
    (args.output / "results.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    main()
