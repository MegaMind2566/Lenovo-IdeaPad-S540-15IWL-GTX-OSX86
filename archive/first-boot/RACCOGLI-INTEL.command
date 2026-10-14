#!/bin/bash
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
exec /bin/bash "$root/tools/collect_gui_logs.sh" --intel "$@"
