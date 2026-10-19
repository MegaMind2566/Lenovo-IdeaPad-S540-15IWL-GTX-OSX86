#!/usr/bin/env python3
"""Apply the isolated candidate to copies and exercise actual function bodies."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

SOURCES = {
    "src/nvidia/src/kernel/gpu/gsp/kernel_gsp.c": "ed6d7020a8a1772bc44608178aa13a77a72b8bf0eabe3293c12bc9d2b122c6c9",
    "src/nvidia/src/kernel/gpu/gsp/arch/turing/kernel_gsp_tu102.c": "df312262254d712e8340c2d428bb5869354756f41b7a5758aac2f1825fdf2550",
    "src/nvidia/src/kernel/gpu/gsp/arch/turing/kernel_gsp_booter_tu102.c": "d5870180adf108bd127744aeb0ea1c4f8b070b1a3ca8aece4d773258ee567792",
    "src/nvidia/src/kernel/gpu/gpu.c": "287b204497d90139836f15b1d05a5abca50a67cd2c235e0351194c00153a2257",
}
FUNCTIONS = [
    ("src/nvidia/src/kernel/gpu/gsp/arch/turing/kernel_gsp_booter_tu102.c", "kgspExecuteBooterUnloadIfNeeded_TU102"),
    ("src/nvidia/src/kernel/gpu/gsp/arch/turing/kernel_gsp_tu102.c", "kgspTeardown_TU102"),
    ("src/nvidia/src/kernel/gpu/gsp/kernel_gsp.c", "kgspUnloadRm_IMPL"),
    ("src/nvidia/src/kernel/gpu/gpu.c", "gpuStatePreUnload"),
    ("src/nvidia/src/kernel/gpu/gpu.c", "gpuStatePostUnload"),
    ("src/nvidia/src/kernel/gpu/gpu.c", "gpuStateUnload_IMPL"),
    ("src/nvidia/src/kernel/gpu/gpu.c", "gpuEnterShutdown_IMPL"),
    ("src/nvidia/src/kernel/gpu/gpu.c", "gpuStateDestroy_IMPL"),
]

def extract(source: str, name: str) -> str:
    starts = list(re.finditer(r"(?m)^(?:static )?NV_STATUS\n" + re.escape(name) + r"\s*\(", source))
    if len(starts) != 1:
        raise ValueError(f"Expected one original definition for {name}: {len(starts)}")
    start = starts[0].start()
    brace = source.index("{", starts[0].end())
    # Lex strings/comments so braces in diagnostic text cannot change extraction.
    token = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|/\*.*?\*/|//[^\n]*|[{}]', re.S)
    depth = 0
    for match in token.finditer(source, brace):
        if match.group() == "{": depth += 1
        elif match.group() == "}":
            depth -= 1
            if depth == 0: return source[start:match.end()] + "\n"
    raise ValueError(f"Unbalanced original definition: {name}")

def run(argv: list[str], **kwargs) -> subprocess.CompletedProcess:
    result = subprocess.run(argv, text=True, capture_output=True, **kwargs)
    if result.returncode:
        raise RuntimeError(f"{argv!r}\n{result.stdout}\n{result.stderr}")
    return result

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cxx", default=os.environ.get("CXX", "clang++"))
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    args.output.mkdir(parents=True, exist_ok=True)
    report = {"format": 1, "upstream_commit": "1a82fbfda8f321b056eb3568850f9316c5e465c5",
              "patch_sha256": hashlib.sha256((here / "gsp-teardown-status-prospective.patch").read_bytes()).hexdigest(),
              "sources": SOURCES, "variants": {}}
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
            patch = str(here / "gsp-teardown-status-prospective.patch")
            run(["git", "apply", "--check", patch], cwd=root)
            run(["git", "apply", patch], cwd=root)
        bodies = []
        for relative, function in FUNCTIONS:
            body = extract((root / relative).read_text(), function)
            bodies.append(f'\n#line 1 "{relative}:{function}"\n' + body)
        (root / "gsp_teardown_actual_bodies.inc").write_text("\n".join(bodies))
        for mode in ("plain", "sanitized"):
            binary = root / mode
            command = [args.cxx, "-std=gnu++17", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
                       "-Wno-unused-parameter", "-I", str(here), "-I", str(root),
                       str(here / "check_gsp_teardown_status_native.cpp"), "-o", str(binary)]
            if mode == "sanitized":
                command += ["-fsanitize=address,undefined,function", "-fno-sanitize-recover=all", "-fno-omit-frame-pointer"]
            run(command)
            executed = run([str(binary)] + (["--baseline"] if variant == "baseline" else []))
            result = json.loads(executed.stdout)
            (root / f"{mode}.json").write_text(json.dumps(result, indent=2) + "\n")
            report["variants"][f"{variant}_{mode}"] = result
    (args.output / "results.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report["variants"], indent=2))

if __name__ == "__main__":
    main()
