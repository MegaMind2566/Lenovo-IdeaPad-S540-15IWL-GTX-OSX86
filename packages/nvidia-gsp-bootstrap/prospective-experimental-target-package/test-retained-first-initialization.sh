#!/bin/sh
# SPDX-License-Identifier: MIT
# One explicit temporary first-initialization attempt. Reboot ends retention.
set -eu
fail() { printf '%s\n' "$*" >&2; exit 1; }
hash() { /usr/bin/shasum -a 256 "$1" | /usr/bin/awk '{print $1}'; }
PKG=$(CDPATH= cd "$(dirname "$0")" && pwd -P)
PIN= OUTPUT= ACK=0
while [ "$#" -gt 0 ]; do
    case "$1" in
        --attestation-sha256) [ "$#" -ge 2 ] || fail 'Missing attestation SHA256.'; PIN=$2; shift 2 ;;
        --output) [ "$#" -ge 2 ] || fail 'Missing fresh report output.'; OUTPUT=$2; shift 2 ;;
        --ack-retained-first-initialization) ACK=1; shift ;;
        *) fail 'Use --attestation-sha256 HASH --ack-retained-first-initialization [--output NEWDIR].' ;;
    esac
done
[ "$ACK" = 1 ] || fail 'Add --ack-retained-first-initialization: one attempt, retained resources/module until reboot.'
[ "${#PIN}" = 64 ] || fail 'Supply the independently published packaging-attestation SHA256.'
case "$PIN" in *[!0-9a-f]*) fail 'Invalid attestation SHA256.' ;; esac
[ "$(/usr/bin/uname -s)" = Darwin ] || fail 'This test requires the Intel macOS Lenovo.'
[ "$(/usr/bin/uname -m)" = x86_64 ] || fail 'Intel x86_64 is required.'
[ "$(/usr/bin/id -u)" = 0 ] || fail 'Run the explicit test with sudo.'
[ "$(/usr/bin/sw_vers -buildVersion)" = 25G241 ] || fail 'Required macOS build: 25G241.'
[ "$(/usr/bin/uname -r)" = 25.6.0 ] || fail 'Required Darwin release: 25.6.0.'
verify_package() {
    [ "$(hash "$PKG/packaging-attestation.json")" = "$PIN" ] || fail 'Attestation SHA256 mismatch.'
    expected=$(/usr/bin/plutil -extract package_manifest_sha256 raw -o - "$PKG/packaging-attestation.json")
    [ "$(hash "$PKG/SHA256SUMS")" = "$expected" ] || fail 'Package manifest SHA256 mismatch.'
    [ -z "$(/usr/bin/find "$PKG" ! -type d ! -type f -print)" ] || fail 'Only ordinary package files/directories are permitted.'
    (cd "$PKG" && /usr/bin/shasum -a 256 -c SHA256SUMS) >/dev/null || fail 'Package file integrity failed.'
    listed=$(/usr/bin/awk 'END{print NR}' "$PKG/SHA256SUMS")
    actual=$(/usr/bin/find "$PKG" -type f -print | /usr/bin/awk 'END{print NR}')
    [ "$actual" -eq "$((listed + 2))" ] || fail 'Unexpected files were added to the package; extract a clean ZIP into a fresh temporary directory.'
    /usr/bin/codesign --verify --strict "$PKG/S540ExperimentalInit.kext" || fail 'Bundle signature verification failed.'
    /usr/bin/codesign --verify --strict "$PKG/experimental_ctl" || fail 'Client signature verification failed.'
}
verify_package
if [ -n "$OUTPUT" ]; then
    [ ! -e "$OUTPUT" ] || fail 'Report output must be a new directory.'
    /bin/mkdir -m 755 "$OUTPUT"; SESSION=$(CDPATH= cd "$OUTPUT" && pwd -P)
else
    SESSION=$(/usr/bin/mktemp -d /private/tmp/S540RetainedInit.XXXXXX)
    /bin/chmod 755 "$SESSION"
fi
case "$SESSION/" in "$PKG/"*) fail 'The report output must be outside the package.' ;; esac
/usr/bin/sw_vers >"$SESSION/sw-vers.txt"
/usr/bin/uname -a >"$SESSION/uname.txt"
/usr/sbin/sysctl kern.stack_size >"$SESSION/kernel-stack.txt"
/usr/bin/kmutil showloaded >"$SESSION/loaded-before.txt" 2>"$SESSION/loaded-before.stderr"
has_identifier() {
    /usr/bin/awk -v name="$1" '{for(i=1;i<=NF;i++)if($i==name){seen=1;break}} END{exit seen?0:1}' "$2"
}
if has_identifier org.osx86.S540ExperimentalInit "$SESSION/loaded-before.txt" ||
    has_identifier org.osx86.S540ProspectiveLoader "$SESSION/loaded-before.txt"; then
    fail 'An experimental/idle module is already loaded. Reboot before a fresh attempt.'
fi
"$PKG/experimental_ctl" --target >"$SESSION/target.json" 2>"$SESSION/target.stderr" ||
    fail 'The exact unique Lenovo GPU registry identity and target stack were not confirmed; no load was attempted.'
/bin/cp -R "$PKG" "$SESSION/payload"
PKG=$SESSION/payload
verify_package
/usr/sbin/chown -R 0:0 "$PKG"
[ -z "$(/usr/bin/find "$PKG" \( ! -uid 0 -o ! -gid 0 \) -print)" ] || fail 'Temporary payload must be root:wheel (0:0).'
[ -z "$(/usr/bin/find "$PKG" \( -perm -020 -o -perm -002 \) -print)" ] || fail 'Temporary payload is writable by another user/group.'
load_status=-1; controller_status=-1; load_attempted=false; run_attempted=false; observed=false; control_ready=false; reboot_required=false
finish() {
    result=$?
    trap - 0 1 2 15
    # A return/error/interrupt cannot establish that no original call began.
    # Never issue kmutil unload after the run command has been attempted.
    if /usr/bin/kmutil showloaded >"$SESSION/loaded-after.txt" 2>"$SESSION/loaded-after.stderr"; then
        if has_identifier org.osx86.S540ExperimentalInit "$SESSION/loaded-after.txt"; then reboot_required=true; fi
    elif [ "$load_attempted" = true ]; then reboot_required=true; fi
    if [ "$load_attempted" = true ] && [ "$load_status" = -1 ]; then reboot_required=true; fi
    printf '{"format":1,"scope":"retained-first-initialization-target-test","build":"25G241","darwin_release":"25.6.0","load_attempted":%s,"load_command_status":%s,"external_loader_abi_observed":%s,"control_ready":%s,"run_command_attempted":%s,"controller_command_status":%s,"controller_report":"controller.json","normal_unload_attempted":false,"reboot_required_by_test_policy":%s,"attestation_sha256":"%s","system_security_changed":false,"acceleration_test":false}\n' \
        "$load_attempted" "$load_status" "$observed" "$control_ready" "$run_attempted" "$controller_status" "$reboot_required" "$PIN" >"$SESSION/result.json"
    printf 'Retained first-initialization report: %s\n' "$SESSION"
    if [ "$reboot_required" = true ]; then printf '%s\n' 'Save the report, then reboot before another test. No module unload was attempted.'; fi
    exit "$result"
}
trap finish 0
trap 'exit 129' 1
trap 'exit 130' 2
trap 'exit 143' 15
load_attempted=true
if /usr/bin/kmutil load --bundle-path "$PKG/S540ExperimentalInit.kext" >"$SESSION/load.stdout" 2>"$SESSION/load.stderr"; then load_status=0; else load_status=$?; fi
[ "$load_status" = 0 ] || fail 'The target loader rejected the experimental image; see load.stderr.'
reboot_required=true
/usr/bin/kmutil showloaded >"$SESSION/loaded-current.txt" 2>"$SESSION/loaded-current.stderr"
UUID=$(/usr/bin/plutil -extract signed_image.uuid raw -o - "$PKG/packaging-attestation.json")
/usr/bin/awk -v name=org.osx86.S540ExperimentalInit -v uuid="$UUID" \
    '{for(i=1;i<=NF;i++)if($i==name){rows++;for(j=1;j<=NF;j++){token=$j;gsub(/[<>()]/,"",token);if(toupper(token)==toupper(uuid))matches++}break}} END{exit rows==1 && matches==1?0:1}' \
    "$SESSION/loaded-current.txt" || fail 'The exact signed image UUID was not observed in the loaded module inventory.'
observed=true
ready=0
for attempt in 1 2 3 4 5; do
    if "$PKG/experimental_ctl" --snapshot >"$SESSION/before-run.json" 2>"$SESSION/before-run.stderr"; then ready=1; break; fi
    /bin/sleep 1
done
[ "$ready" = 1 ] || fail 'Exact source/policy/native-profile control state was not observed. Reboot before retrying.'
control_ready=true
run_attempted=true
if "$PKG/experimental_ctl" --run-once --ack-retained-first-initialization >"$SESSION/controller.json" 2>"$SESSION/controller.stderr"; then controller_status=0; else controller_status=$?; fi
[ "$controller_status" = 0 ] || fail 'The initialization/control call returned an error. Its real stop attempt and retained observations are in controller.json.'
