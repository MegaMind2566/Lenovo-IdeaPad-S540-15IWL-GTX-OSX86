#!/bin/bash
set -euo pipefail
S540_PACKAGE=$(cd "$(dirname "$0")" && pwd -P)
. "$S540_PACKAGE/tools/s540-common.sh"
s540_verify
