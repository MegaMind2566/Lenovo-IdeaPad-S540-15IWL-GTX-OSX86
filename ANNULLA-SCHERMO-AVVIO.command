#!/bin/bash
set -u
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd -P)
/bin/bash "$SCRIPT_DIR/tools/backlight_boot_test.sh" restore "$@"
result=$?
printf '\nPremi INVIO per chiudere.\n'
read -r _
exit "$result"
