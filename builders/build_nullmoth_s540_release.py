#!/usr/bin/env python3
"""Build the deterministic v0.4.0 S540 NVIDIA experimental release kit."""

import argparse
import importlib.util
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
RELEASE_ROOT = ROOT / "packages/nullmoth-s540/release"
MODULE_PATH = RELEASE_ROOT / "s540_release.py"

if str(RELEASE_ROOT) not in sys.path:
    sys.path.insert(0, str(RELEASE_ROOT))
_SPEC = importlib.util.spec_from_file_location("s540_release_kit", MODULE_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError(f"Cannot load release implementation: {MODULE_PATH}")
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)

DEFAULT_LOCK = _MODULE.DEFAULT_LOCK
load_source_lock = _MODULE.load_source_lock
sha256_data = _MODULE.sha256_data
sha256_file = _MODULE.sha256_file
safe_extract_zip = _MODULE.safe_extract_zip
safe_extract_tar = _MODULE.safe_extract_tar
validate_public_config = _MODULE.validate_public_config
validate_target_host = _MODULE.validate_target_host
build_release = _MODULE.build_release


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=ROOT / "build/nullmoth-s540-release",
    )
    args = parser.parse_args()
    destination = build_release(args.output_directory)
    print(f"Built {destination}")
    print(f"SHA-256 {sha256_file(destination)}")


if __name__ == "__main__":
    main()
