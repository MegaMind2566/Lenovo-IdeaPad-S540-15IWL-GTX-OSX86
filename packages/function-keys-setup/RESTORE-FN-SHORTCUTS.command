#!/bin/bash
# SPDX-License-Identifier: MIT
set -eu
PACKAGE_ROOT=$(cd "$(dirname "$0")" && pwd -P)
[ "$(/usr/bin/uname -s)" = Darwin ] && [ "$(/usr/bin/uname -m)" = x86_64 ] || { printf 'Intel macOS is required.\n' >&2; exit 1; }
[ -f "$PACKAGE_ROOT/SHA256SUMS" ] && [ ! -L "$PACKAGE_ROOT/SHA256SUMS" ] || { printf 'The checksum list is missing.\n' >&2; exit 1; }
(cd "$PACKAGE_ROOT" && /usr/bin/shasum -a 256 -c SHA256SUMS >/dev/null) || exit 1
"$PACKAGE_ROOT/bin/function-key-preferences" --restore
printf 'Restart normally to refresh the restored macOS shortcuts.\n'
