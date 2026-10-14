#!/bin/bash
set -euo pipefail
bundle_root=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
printf 'Unified collection v4: installed-system data\n'
exec /bin/bash "$bundle_root/diagnosi-unified/collect_gui_logs.sh" --unified "$@"
