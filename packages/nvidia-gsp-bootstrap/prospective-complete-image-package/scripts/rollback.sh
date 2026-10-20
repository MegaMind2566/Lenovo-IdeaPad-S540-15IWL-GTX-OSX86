#!/bin/sh
# SPDX-License-Identifier: MIT. Normal unload of the exact idle image only.
set -eu
. "$(dirname "$0")/common.sh"
init "$@"
new_report
collect_system
if ! has_identifier "$SESSION/loaded.txt"; then
    printf '%s\n' '{"format":1,"status":"already-absent","hardware_admission":false}' >"$SESSION/rollback.json"
    printf 'Idle image is absent. Report: %s\n' "$SESSION"; exit 0
fi
has_expected_uuid "$SESSION/loaded.txt" || fail 'Loaded identifier has a different or ambiguous UUID; refusing to unload another image.'
if /usr/bin/kmutil unload --bundle-identifier "$BUNDLE_ID" >"$SESSION/unload.stdout" 2>"$SESSION/unload.stderr"; then status=0; else status=$?; fi
/usr/bin/kmutil showloaded >"$SESSION/loaded-after.txt" 2>"$SESSION/loaded-after.stderr"
absent=true
if has_identifier "$SESSION/loaded-after.txt"; then absent=false; fi
printf '{"format":1,"scope":"normal-idle-image-unload","unload_command_status":%s,"identifier_absent":%s,"force_used":false,"system_security_changed":false,"hardware_admission":false}\n' "$status" "$absent" >"$SESSION/rollback.json"
printf 'Idle image rollback report: %s\n' "$SESSION"
[ "$status" = 0 ] && [ "$absent" = true ] || fail 'Normal unload did not complete. Keep the report; no force, reboot or security change was attempted.'
