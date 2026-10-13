#!/bin/bash
set -euo pipefail
bundle_root=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
printf 'Raccolta unificata v2: diagnostics + uuidtext\n'
exec /bin/bash "$bundle_root/diagnosi-unified/collect_gui_logs.sh" --unified "$@"
