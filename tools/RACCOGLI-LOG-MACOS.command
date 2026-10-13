#!/bin/bash
set -euo pipefail
bundle_root=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
exec /bin/bash "$bundle_root/tools/collect_gui_logs.sh" "$@"
