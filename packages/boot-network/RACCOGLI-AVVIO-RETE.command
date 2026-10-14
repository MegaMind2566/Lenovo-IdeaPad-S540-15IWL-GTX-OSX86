#!/bin/bash
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd -P) || exit 1
/bin/bash "$SCRIPT_DIR/tools/collect_boot_network.sh" "$@"
rc=$?
if [ -t 0 ]; then
    printf '\nPremi INVIO per chiudere.\n'
    read -r _
fi
exit "$rc"
