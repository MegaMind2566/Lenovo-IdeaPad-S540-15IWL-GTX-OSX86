#!/bin/bash
# SPDX-License-Identifier: MIT
set -eu
umask 077

fail() { printf 'Scan-code collection: %s\n' "$1" >&2; exit 1; }
PACKAGE_ROOT=$(cd "$(dirname "$0")" && pwd -P)
PROBE="$PACKAGE_ROOT/bin/function-key-scancodes"
[ "$(/usr/bin/uname -s)" = Darwin ] && [ "$(/usr/bin/uname -m)" = x86_64 ] || fail 'Run on Intel macOS.'
[ -f "$PACKAGE_ROOT/SHA256SUMS" ] && [ ! -L "$PACKAGE_ROOT/SHA256SUMS" ] || fail 'The package checksum list is missing.'
(cd "$PACKAGE_ROOT" && /usr/bin/shasum -a 256 -c SHA256SUMS >/dev/null) || fail 'Package verification failed.'
[ -f "$PROBE" ] && [ ! -L "$PROBE" ] && [ -x "$PROBE" ] || fail 'The native helper is missing.'
"$PROBE" --self-test || fail 'The native fixture checks failed.'
printf '\nThis diagnostic temporarily enables keyboard driver scan-code traces for ten 3-second windows.\n'
printf 'Those numeric key transitions also enter the macOS unified system log.\n'
printf 'Press only the requested keys after NOW. No passwords or other typing during a window.\n'
printf 'Release Fn and Command before every window; press them only after NOW when requested.\n'
printf 'Close other keyboard diagnostics. No EFI or key mapping is changed.\n'
printf '\nThe administrator password is requested now, before logging starts.\n'
/usr/bin/sudo -v || fail 'Administrator authentication was cancelled. No keyboard logging started.'
[ -d "$HOME/Desktop" ] || fail 'The Desktop is unavailable.'
REPORT_ROOT=$(/usr/bin/mktemp -d "$HOME/Desktop/FUNCTION-KEY-SCANS-XXXXXX") || fail 'A private report folder could not be created.'
/bin/chmod 700 "$REPORT_ROOT"
set +e
"$PROBE" --output "$REPORT_ROOT"
RESULT=$?
set -e
if [ ! -f "$REPORT_ROOT/scancodes.json" ]; then
    /bin/rmdir "$REPORT_ROOT" 2>/dev/null || true
    fail 'No report was created. Keep the previous Terminal message.'
fi
ZIP_PATH="$REPORT_ROOT.zip"
[ ! -e "$ZIP_PATH" ] && [ ! -L "$ZIP_PATH" ] || fail 'The report archive destination already exists.'
(cd "$REPORT_ROOT" && /usr/bin/zip -q -X "$ZIP_PATH" scancodes.json) || fail 'The report archive could not be created.'
/bin/chmod 600 "$ZIP_PATH"
printf '\nReport archive: %s\nAttach this ZIP.\n' "$ZIP_PATH"
if [ "$RESULT" -ne 0 ]; then
    printf 'Collection was interrupted. Read the restoration status above before using the keyboard again.\n'
    exit "$RESULT"
fi
