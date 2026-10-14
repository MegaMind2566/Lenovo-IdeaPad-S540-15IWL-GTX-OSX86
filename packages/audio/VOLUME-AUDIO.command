#!/bin/bash
set -u
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd -P)
/bin/bash "$SCRIPT_DIR/tools/audio_tahoe.sh" volume "$@"
result=$?
printf '\nPremi INVIO per chiudere.\n'
read -r _
exit "$result"
