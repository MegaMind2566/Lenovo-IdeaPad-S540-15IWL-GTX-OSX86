#!/bin/zsh
set -euo pipefail

script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)"
exec /usr/bin/python3 "$script_dir/bin/s540_release.py" \
  --kit-root "$script_dir" verify-install
