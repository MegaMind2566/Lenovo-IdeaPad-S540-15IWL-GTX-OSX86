#!/bin/sh
# SPDX-License-Identifier: MIT. Shared idle complete-image check functions.
fail() { printf '%s\n' "$*" >&2; exit 1; }
init() {
    [ "$(/usr/bin/uname -s)" = Darwin ] || fail 'This check requires the exact Intel macOS target.'
    [ "$(/usr/bin/uname -m)" = x86_64 ] || fail 'Intel x86_64 is required.'
    [ "$(/usr/bin/id -u)" = 0 ] || fail 'Run this explicit idle loader check as administrator.'
    PKG=$(CDPATH= cd "$(dirname "$0")" && pwd -P)
    PIN= OUTPUT= ACK=0
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --attestation-sha256) [ "$#" -ge 2 ] || fail 'Missing attestation hash.'; PIN=$2; shift 2 ;;
            --output) [ "$#" -ge 2 ] || fail 'Missing report directory.'; OUTPUT=$2; shift 2 ;;
            --ack-idle-loader-only) ACK=1; shift ;;
            *) fail 'Unknown argument. Use --attestation-sha256 HASH [--output NEWDIR].' ;;
        esac
    done
    [ "${#PIN}" = 64 ] || fail 'Supply the independently published packaging-attestation SHA256.'
    case "$PIN" in *[!0-9a-f]*) fail 'Invalid SHA256.' ;; esac
    verify_package
    [ "$(/usr/bin/sw_vers -productVersion)" = 26.7.1 ] || fail 'Required product version: 26.7.1.'
    [ "$(/usr/bin/sw_vers -buildVersion)" = 25G241 ] || fail 'Required target build: 25G241.'
    [ "$(/usr/bin/uname -r)" = 25.6.0 ] || fail 'Required Darwin release: 25.6.0.'
    EXPECTED_UUID=$(/usr/bin/plutil -extract signed_image.uuid raw -o - "$PKG/packaging-attestation.json")
    BUNDLE_ID=org.osx86.S540ProspectiveLoader
}
hash() { /usr/bin/shasum -a 256 "$1" | /usr/bin/awk '{print $1}'; }
verify_package() {
    [ "$(hash "$PKG/packaging-attestation.json")" = "$PIN" ] || fail 'Attestation hash mismatch.'
    expected=$(/usr/bin/plutil -extract package_manifest_sha256 raw -o - "$PKG/packaging-attestation.json")
    [ "$(hash "$PKG/SHA256SUMS")" = "$expected" ] || fail 'Package inventory hash mismatch.'
    [ -z "$(/usr/bin/find "$PKG" -type l -print)" ] || fail 'Package symlinks are refused.'
    (cd "$PKG" && /usr/bin/shasum -a 256 -c SHA256SUMS) >/dev/null || fail 'Package file integrity failed.'
    listed=$(/usr/bin/awk 'END{print NR}' "$PKG/SHA256SUMS")
    actual=$(/usr/bin/find "$PKG" -type f -print | /usr/bin/awk 'END{print NR}')
    [ "$actual" -eq "$((listed + 2))" ] || fail 'Unexpected files were added to the package.'
    /usr/bin/codesign --verify --strict "$PKG/S540IdleCompleteImage.kext" || fail 'Bundle signature verification failed.'
    /usr/bin/codesign --verify --strict "$PKG/s540-idle-image-ctl" || fail 'Controller signature verification failed.'
}
new_report() {
    if [ -n "$OUTPUT" ]; then
        [ ! -e "$OUTPUT" ] || fail 'Report output must be a new directory.'
        /bin/mkdir -m 755 "$OUTPUT"; SESSION=$(CDPATH= cd "$OUTPUT" && pwd -P)
    else
        SESSION=$(/usr/bin/mktemp -d /private/tmp/S540IdleABI.XXXXXX)
        /bin/chmod 755 "$SESSION"
    fi
    case "$SESSION/" in "$PKG/"*) fail 'Report output must be outside the package.' ;; esac
}
has_identifier() {
    /usr/bin/awk -v name="$BUNDLE_ID" \
        '{for(i=1;i<=NF;i++)if($i==name){seen=1;break}} END{exit seen?0:1}' "$1"
}
has_expected_uuid() {
    /usr/bin/awk -v name="$BUNDLE_ID" -v uuid="$EXPECTED_UUID" \
        '{for(i=1;i<=NF;i++)if($i==name){rows++;for(j=1;j<=NF;j++){token=$j;gsub(/[<>()]/,"",token);if(toupper(token)==toupper(uuid))matches++}break}} END{exit rows==1 && matches==1?0:1}' "$1"
}
collect_system() {
    /usr/bin/sw_vers >"$SESSION/sw_vers.txt"
    /usr/bin/uname -a >"$SESSION/uname.txt"
    /usr/sbin/sysctl -n hw.model >"$SESSION/hw-model.txt"
    /usr/bin/kmutil showloaded >"$SESSION/loaded.txt" 2>"$SESSION/loaded.stderr"
}
