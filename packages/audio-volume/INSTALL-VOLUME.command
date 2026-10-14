#!/bin/bash
set -euo pipefail
PACKAGE=$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd)
exec /bin/bash "$PACKAGE/tools/volume_driver_test.sh" install "$@"
