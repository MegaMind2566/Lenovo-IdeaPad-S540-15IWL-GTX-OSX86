#!/bin/bash
# SPDX-License-Identifier: MIT
set -eu
umask 077

fail() { printf 'Function-key event collection: %s\n' "$1" >&2; exit 1; }
TARGETED=0
if [ "$#" -eq 1 ] && [ "$1" = --targeted ]; then
  TARGETED=1
elif [ "$#" -ne 0 ]; then
  fail 'Usage: COLLECT-KEY-EVENTS.command [--targeted]'
fi
PACKAGE_ROOT=$(cd "$(dirname "$0")" && pwd -P)
PROBE="$PACKAGE_ROOT/bin/function-key-events"
[ "$(/usr/bin/uname -s)" = Darwin ] || fail 'This package requires macOS.'
[ "$(/usr/bin/uname -m)" = x86_64 ] || fail 'This package requires an Intel Mac.'
[ -f "$PROBE" ] && [ ! -L "$PROBE" ] && [ -x "$PROBE" ] || fail 'The native probe is missing.'
[ -d "$HOME/Desktop" ] || fail 'The Desktop folder is unavailable.'
[ -f "$PACKAGE_ROOT/SHA256SUMS" ] && [ ! -L "$PACKAGE_ROOT/SHA256SUMS" ] || fail 'The package checksum list is missing.'
(cd "$PACKAGE_ROOT" && /usr/bin/shasum -a 256 -c SHA256SUMS >/dev/null) || fail 'Package verification failed.'
"$PROBE" --self-test || fail 'The probe self-test failed.'

REPORT_ROOT=$(/usr/bin/mktemp -d "$HOME/Desktop/FUNCTION-KEY-EVENTS-XXXXXX") || fail 'A private report folder could not be created.'
/bin/chmod 700 "$REPORT_ROOT"
printf 'The probe may request Input Monitoring for Terminal or the probe.\n'
printf 'It does not request Accessibility, install a background service, or remap keys.\n\n'
set +e
if [ "$TARGETED" -eq 1 ]; then
  "$PROBE" --targeted --output "$REPORT_ROOT"
else
  "$PROBE" --output "$REPORT_ROOT"
fi
RESULT=$?
set -e
if [ "$RESULT" -eq 77 ]; then
  /bin/rmdir "$REPORT_ROOT" 2>/dev/null || true
  printf '\nGrant Input Monitoring through System Settings, reopen Terminal, and run the same command again.\n'
  exit 77
fi
[ "$RESULT" -eq 0 ] || fail 'Collection stopped. Any partial report folder has been preserved.'
[ -f "$REPORT_ROOT/events.json" ] && [ -f "$REPORT_ROOT/events.txt" ] || fail 'The report is incomplete.'
ZIP_PATH="$REPORT_ROOT.zip"
[ ! -e "$ZIP_PATH" ] || fail 'A report archive with this name already exists.'
(cd "$REPORT_ROOT" && /usr/bin/zip -q -X "$ZIP_PATH" events.json events.txt) || fail 'The report archive could not be created.'
/bin/chmod 600 "$ZIP_PATH"
printf '\nReport archive: %s\nAttach this ZIP to the conversation. The report folder is preserved.\n' "$ZIP_PATH"
