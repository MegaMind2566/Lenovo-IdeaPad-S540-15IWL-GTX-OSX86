#!/bin/sh
# SPDX-License-Identifier: MIT. Explicit temporary idle complete-image ABI check.
set -eu
. "$(dirname "$0")/common.sh"
init "$@"
[ "$ACK" = 1 ] || fail 'Add --ack-idle-loader-only to run the idle loader ABI check. This does not test RM/GSP initialization.'
new_report
collect_system
if has_identifier "$SESSION/loaded.txt"; then fail 'This bundle identifier is already loaded; no load or unload was attempted.'; fi
"$PKG/s540-idle-image-ctl" --target >"$SESSION/target.json" 2>"$SESSION/target.stderr" || fail 'Exact Lenovo GPU registry identity was not observed; no load was attempted.'
# Only a temporary root-owned copy is loaded; there is no OS installation.
/bin/cp -R "$PKG" "$SESSION/payload"
PKG=$SESSION/payload
verify_package
[ -z "$(/usr/bin/find "$PKG" ! -user root -print)" ] || fail 'Temporary payload ownership is not root.'
[ -z "$(/usr/bin/find "$PKG" \( -perm -020 -o -perm -002 \) -print)" ] || fail 'Temporary payload is writable by another user/group.'
attempted=0; load_status=-1; observed=false
cleanup() {
    result=$?
    trap - 0 1 2 15
    rollback_status=0
    if [ "$attempted" = 1 ]; then
        if "$PKG/rollback.sh" --attestation-sha256 "$PIN" --output "$SESSION/rollback" >"$SESSION/rollback.stdout" 2>"$SESSION/rollback.stderr"; then :; else rollback_status=$?; fi
    fi
    printf '{"format":1,"scope":"idle-complete-image-target-loader-abi-check","build":"25G241","darwin_release":"25.6.0","load_command_status":%s,"external_loader_abi_observed":%s,"rollback_status":%s,"attestation_sha256":"%s","hardware_admission":false,"original_entry_admission":false,"rm_initialization_test":false,"gsp_initialization_test":false,"acceleration_test":false,"system_security_changed":false}\n' \
        "$load_status" "$observed" "$rollback_status" "$PIN" >"$SESSION/result.json"
    printf 'Idle complete-image ABI check and rollback report: %s\n' "$SESSION"
    [ "$result" = 0 ] && [ "$rollback_status" = 0 ] || exit 1
}
trap cleanup 0
trap 'exit 129' 1
trap 'exit 130' 2
trap 'exit 143' 15
attempted=1
if /usr/bin/kmutil load --bundle-path "$PKG/S540IdleCompleteImage.kext" >"$SESSION/load.stdout" 2>"$SESSION/load.stderr"; then load_status=0; else load_status=$?; fi
[ "$load_status" = 0 ] || fail 'The target loader rejected the idle complete image; failure and rollback will be reported.'
/usr/bin/kmutil showloaded >"$SESSION/loaded-after.txt" 2>"$SESSION/loaded-after.stderr"
has_expected_uuid "$SESSION/loaded-after.txt" || fail 'The exact image UUID was not observed in loaded modules.'
ready=0
for attempt in 1 2 3 4 5; do
    if "$PKG/s540-idle-image-ctl" --snapshot >"$SESSION/snapshot.json" 2>"$SESSION/snapshot.stderr"; then ready=1; break; fi
    /bin/sleep 1
done
[ "$ready" = 1 ] || fail 'The exact closed idle control state was not observed.'
observed=true
# The EXIT trap always attempts normal rollback and records its actual result.
