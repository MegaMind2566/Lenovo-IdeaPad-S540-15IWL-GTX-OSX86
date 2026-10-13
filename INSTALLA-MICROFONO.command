#!/bin/bash
set -eu
HERE=$(cd -P "$(/usr/bin/dirname "${BASH_SOURCE[0]}")" && pwd)
exec /bin/bash "$HERE/tools/microphone_driver_test.sh" install "$@"
