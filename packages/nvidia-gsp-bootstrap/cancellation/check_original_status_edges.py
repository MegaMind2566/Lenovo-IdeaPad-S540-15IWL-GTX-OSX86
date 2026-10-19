#!/usr/bin/env python3
"""Check isolated reset-status and disabled-caps guards on actual source bodies."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
from check_gsp_teardown_status import extract, run

SOURCES = {
    "src/nvidia/src/kernel/gpu/falcon/arch/turing/kernel_falcon_tu102.c": "a4d4f25fc0fb4a686194ddb292649421ba7732144c6e1e6c820ab1928579c41c",
    "src/nvidia/arch/nvalloc/unix/src/os.c": "057b50fcb738be90a073b60f63e70559706864ddcec3bf703282563173e3dce4",
}
FUNCTIONS = [(next(iter(SOURCES)), "kflcnReset_TU102"),
             ("src/nvidia/arch/nvalloc/unix/src/os.c", "osRmCapRegisterGpu")]
PATCHES = ["falcon-reset-status-prospective.patch", "caps-minor-guard-prospective.patch"]

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cxx", default=os.environ.get("CXX", "clang++"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    here = Path(__file__).resolve().parent
    report = {"format": 1, "upstream_commit": "1a82fbfda8f321b056eb3568850f9316c5e465c5",
              "sources": SOURCES, "patches": {name: hashlib.sha256((here / name).read_bytes()).hexdigest()
                                               for name in PATCHES}, "variants": {}}
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
            for name in PATCHES:
                run(["git", "apply", "--check", str(here / name)], cwd=root)
                run(["git", "apply", str(here / name)], cwd=root)
        (root / "original_status_edges_actual_bodies.inc").write_text("\n".join(
            f'\n#line 1 "{relative}:{name}"\n' + extract((root / relative).read_text(), name)
            for relative, name in FUNCTIONS))
        for mode in ("plain", "sanitized"):
            binary = root / mode
            command = [args.cxx, "-std=gnu++17", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
                       "-Wno-unused-parameter", "-I", str(here), "-I", str(root),
                       str(here / "check_original_status_edges_native.cpp"), "-o", str(binary)]
            if mode == "sanitized":
                command += ["-fsanitize=address,undefined,function", "-fno-sanitize-recover=all", "-fno-omit-frame-pointer"]
            run(command)
            result = json.loads(run([str(binary)] + (["--baseline"] if variant == "baseline" else [])).stdout)
            (root / f"{mode}.json").write_text(json.dumps(result, indent=2) + "\n")
            report["variants"][f"{variant}_{mode}"] = result
    (args.output / "results.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    main()
