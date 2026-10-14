#!/bin/bash
set -u
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd -P)
/bin/bash "$SCRIPT_DIR/tools/audio_tahoe.sh" restore "$@"
result=$?
printf '\nPress ENTER to close.\n'
read -r _
exit "$result"
