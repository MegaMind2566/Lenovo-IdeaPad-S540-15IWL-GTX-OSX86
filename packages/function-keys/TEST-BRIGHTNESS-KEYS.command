#!/bin/bash
set -u
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd -P)
/bin/bash "$SCRIPT_DIR/tools/brightness_keys_test.sh" test "$@"
result=$?
printf '\nPress ENTER to close.\n'
read -r _
exit "$result"
