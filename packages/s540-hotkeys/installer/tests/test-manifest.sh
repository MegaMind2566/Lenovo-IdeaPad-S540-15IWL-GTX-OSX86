#!/bin/bash
set -euo pipefail
S540_PACKAGE=$(cd "$(dirname "$0")/.." && pwd -P)
. "$S540_PACKAGE/tools/s540-common.sh"
FIXTURE=$(mktemp -d)
trap 'rm -rf "$FIXTURE"' EXIT
mkdir -p "$FIXTURE/source/Contents/empty" "$FIXTURE/copy/Contents/empty"
printf 'original\n' > "$FIXTURE/source/Contents/data"
cp "$FIXTURE/source/Contents/data" "$FIXTURE/copy/Contents/data"
s540_tree_manifest "$FIXTURE/source" "$FIXTURE/expected"
S540_RUN="$FIXTURE"
s540_tree_matches "$FIXTURE/copy" "$FIXTURE/expected"
printf 'changed\n' > "$FIXTURE/copy/Contents/data"
if s540_tree_matches "$FIXTURE/copy" "$FIXTURE/expected"; then exit 1; fi
cp "$FIXTURE/source/Contents/data" "$FIXTURE/copy/Contents/data"
mkdir "$FIXTURE/copy/unexpected-empty"
if s540_tree_matches "$FIXTURE/copy" "$FIXTURE/expected"; then exit 1; fi
rmdir "$FIXTURE/copy/unexpected-empty"
ln -s data "$FIXTURE/copy/Contents/link"
if s540_tree_manifest "$FIXTURE/copy" "$FIXTURE/rejected"; then exit 1; fi
printf 'PASS: exact content, changed content, extra directory and symlink rejection.\n'
