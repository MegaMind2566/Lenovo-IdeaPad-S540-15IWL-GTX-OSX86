#!/bin/bash
# SPDX-License-Identifier: MIT
set -eu
umask 077

fail() { printf 'Function-key setup: %s\n' "$1" >&2; exit 1; }
PACKAGE_ROOT=$(cd "$(dirname "$0")" && pwd -P)
PREFERENCES="$PACKAGE_ROOT/bin/function-key-preferences"
OBSERVER="$PACKAGE_ROOT/bin/function-key-events"
[ "$(/usr/bin/uname -s)" = Darwin ] && [ "$(/usr/bin/uname -m)" = x86_64 ] || fail 'Run this package on Intel macOS.'
[ -f "$PACKAGE_ROOT/SHA256SUMS" ] && [ ! -L "$PACKAGE_ROOT/SHA256SUMS" ] || fail 'The package checksum list is missing.'
(cd "$PACKAGE_ROOT" && /usr/bin/shasum -a 256 -c SHA256SUMS >/dev/null) || fail 'Package verification failed.'
for PROGRAM in "$PREFERENCES" "$OBSERVER"; do
    [ -f "$PROGRAM" ] && [ ! -L "$PROGRAM" ] && [ -x "$PROGRAM" ] || fail 'A native helper is missing.'
    "$PROGRAM" --self-test || fail 'A native helper self-test failed.'
done
printf 'Close Keyboard Shortcuts settings while this operation runs.\n'
"$PREFERENCES" --apply || fail 'The shortcut change did not complete. Keep the private journal and read the previous message.'
printf '\nThe Fn shortcut settings have been prepared. Restart normally after this collection.\n'
[ -d "$HOME/Desktop" ] || fail 'The Desktop is unavailable. The shortcut settings are already saved.'
REPORT_ROOT=$(/usr/bin/mktemp -d "$HOME/Desktop/FUNCTION-KEY-TARGETS-XXXXXX") || fail 'A private report folder could not be created.'
/bin/chmod 700 "$REPORT_ROOT"
set +e
"$OBSERVER" --targeted --output "$REPORT_ROOT"
RESULT=$?
set -e
if [ "$RESULT" -eq 77 ]; then
    /bin/rmdir "$REPORT_ROOT" 2>/dev/null || true
    printf '\nThe shortcut settings are already saved. Allow Input Monitoring for the requested Terminal/probe entry, reopen Terminal and rerun this command.\n'
    exit 77
fi
[ "$RESULT" -eq 0 ] || fail 'Targeted collection stopped. Keep any report folder; the shortcut journal is preserved.'
[ -f "$REPORT_ROOT/events.json" ] && [ -f "$REPORT_ROOT/events.txt" ] || fail 'The targeted report is incomplete.'
"$PREFERENCES" --status > "$REPORT_ROOT/shortcut-status.txt" || fail 'The shortcut state could not be verified.'
/bin/chmod 600 "$REPORT_ROOT/shortcut-status.txt"
ZIP_PATH="$REPORT_ROOT.zip"
[ ! -e "$ZIP_PATH" ] && [ ! -L "$ZIP_PATH" ] || fail 'The report archive destination already exists.'
(cd "$REPORT_ROOT" && /usr/bin/zip -q -X "$ZIP_PATH" events.json events.txt shortcut-status.txt) || fail 'The report archive could not be created.'
/bin/chmod 600 "$ZIP_PATH"
printf '\nReport archive: %s\nAttach this ZIP, then restart normally to refresh macOS shortcuts.\n' "$ZIP_PATH"
