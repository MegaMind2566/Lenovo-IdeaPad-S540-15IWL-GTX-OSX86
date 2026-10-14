#!/bin/bash
# Native macOS / Bash 3.2. Read-only ownership check for the audio diagnostic.
# stdout contains only the verified installed Mach-O SHA256.
set -euo pipefail
umask 077
export LC_ALL=C

TEMP=''
cleanup() { [ -z "$TEMP" ] || /bin/rm -rf "$TEMP"; }
trap cleanup EXIT
fail() { printf 'Microphone driver verification: %s\n' "$*" >&2; exit 1; }

[ "$#" -eq 2 ] || fail 'The bundle and audio backup paths are required.'
DRIVER=$1
BACKUP=$2
VOLUME="$BACKUP/volume-test"
STATE="$BACKUP/state.plist"
KEY=IOKitPersonalities.VoodooHDA.VoodooHDAEnableVolumeChangeFix
ORIGINAL_INFO='21b886b5449b9a0739422b6720ea2bc04fdcc477f79e1e3cece021033a51bf1a'
ORIGINAL_MACHO='932a7c9e46a65fdab7c8729f599c1094b568ae4fc7f17dad9818c83e833a0973'
ORIGINAL_RESOURCES='6686de10a28a2fe11b36cbb86dcbacc827cfc4ea116b4dabf1845e5aee629e9b'

hash() { /usr/bin/shasum -a 256 "$1" | /usr/bin/awk '{print $1}'; }
ordinary_file() { [ -f "$1" ] && [ ! -L "$1" ]; }
readkey() { /usr/bin/plutil -extract "$2" raw -o - "$1" 2>/dev/null; }
safe_path() {
    local path=$1
    case "$path" in /*) ;; *) fail 'Paths must be absolute.';; esac
    case "$path" in */../*|*/./*|*/..|*/.) fail 'The path contains relative components.';; esac
    while [ "$path" != / ]; do
        [ ! -L "$path" ] || fail 'The path contains a symbolic link.'
        path=${path%/*}
        [ -n "$path" ] || path=/
    done
}
validate_bundle_shape() {
    local bundle=$1 links special count path
    safe_path "$bundle"
    [ -d "$bundle" ] && [ ! -L "$bundle" ] || fail 'The bundle is not a regular directory.'
    links=$(/usr/bin/find "$bundle" -type l -print) || fail 'Cannot inspect bundle links.'
    [ -z "$links" ] || fail 'The bundle contains symbolic links.'
    special=$(/usr/bin/find "$bundle" ! -type f ! -type d -print) || fail 'Cannot inspect bundle files.'
    [ -z "$special" ] || fail 'The bundle contains special files.'
    count=$(/usr/bin/find "$bundle" -type f -print | /usr/bin/wc -l | /usr/bin/tr -d '[:space:]') || fail 'Cannot count bundle files.'
    [ "$count" = 3 ] || fail 'The bundle must contain exactly the three expected files.'
    for path in Contents/Info.plist Contents/MacOS/VoodooHDA Contents/_CodeSignature/CodeResources; do
        ordinary_file "$bundle/$path" || fail 'A regular bundle file is missing.'
    done
}
original_matches() {
    [ "$(hash "$1/Contents/Info.plist")" = "$ORIGINAL_INFO" ] &&
    [ "$(hash "$1/Contents/MacOS/VoodooHDA")" = "$ORIGINAL_MACHO" ] &&
    [ "$(hash "$1/Contents/_CodeSignature/CodeResources")" = "$ORIGINAL_RESOURCES" ]
}
verify_signature() {
    if ! /usr/bin/codesign --verify --strict "$1" > /dev/null 2> "$TEMP/codesign-errors.txt"; then
        /bin/cat "$TEMP/codesign-errors.txt" >&2
        fail 'The bundle signature is invalid.'
    fi
}
manifest_matches() {
    local bundle=$1 expected path
    while IFS=' ' read -r expected path; do
        path=${path# }
        [ "$(hash "$bundle/$path")" = "$expected" ] || return 1
    done < "$TEMP/manifest-checked.txt"
}

validate_bundle_shape "$DRIVER"
TEMP=$(/usr/bin/mktemp -d /tmp/s540-microphone-verify.XXXXXX) || fail 'Cannot create the private temporary directory.'
if original_matches "$DRIVER"; then
    verify_signature "$DRIVER"
    original_matches "$DRIVER" || fail 'The driver changed during verification.'
    printf '%s\n' "$ORIGINAL_MACHO"
    exit 0
fi

# This route reads only the V3 ownership metadata and driver copies. It neither
# reads config.plist nor uses the audio installer's state/draft recovery logic.
safe_path "$BACKUP"
safe_path "$STATE"
safe_path "$VOLUME"
[ -d "$BACKUP" ] && [ ! -L "$BACKUP" ] || fail 'The V3 audio backup is unavailable.'
[ -d "$VOLUME" ] && [ ! -L "$VOLUME" ] || fail 'The complete V3 volume backup is unavailable.'
ordinary_file "$STATE" || fail 'The regular audio backup state file is missing.'
/usr/bin/plutil -lint "$STATE" > /dev/null || fail 'The backup state is not a valid plist.'
STATE_HASH=$(hash "$STATE")
[ "$(readkey "$STATE" Format)" = 2 ] || fail 'The audio backup format is not 2.'
[ "$(readkey "$STATE" Phase)" = installed ] || fail 'The audio test is not in the installed state.'
[ "$(readkey "$STATE" VolumePhase)" = ready ] || fail 'The volume driver replacement is incomplete.'
[ "$(readkey "$STATE" VolumeTarget)" = modified ] || fail 'The state does not identify the V3 volume variant.'
MANIFEST_HASH=$(readkey "$STATE" VolumeManifestHash) || fail 'The volume manifest reference is missing.'
case "$MANIFEST_HASH" in ''|*[!0-9a-f]*) fail 'The volume manifest reference is invalid.';; esac
[ "${#MANIFEST_HASH}" -eq 64 ] || fail 'The volume manifest reference does not contain 64 characters.'
MANIFEST="$VOLUME/SHA256SUMS"
ordinary_file "$MANIFEST" || fail 'The regular volume variant manifest is missing.'
[ "$(hash "$MANIFEST")" = "$MANIFEST_HASH" ] || fail 'The volume manifest does not match the saved state.'

# Require exactly the canonical three ordered, unique entries, with lowercase
# 64-character SHA256 values and a final newline. Never evaluate manifest text.
index=0
: > "$TEMP/manifest-checked.txt"
while IFS= read -r line || [ -n "$line" ]; do
    index=$((index + 1))
    case "$index" in
        1) wanted=Contents/Info.plist;;
        2) wanted=Contents/MacOS/VoodooHDA;;
        3) wanted=Contents/_CodeSignature/CodeResources;;
        *) fail 'The manifest contains extra files.';;
    esac
    expected=${line%% *}
    case "$expected" in ''|*[!0-9a-f]*) fail 'A manifest hash is invalid.';; esac
    [ "${#expected}" -eq 64 ] || fail 'A manifest hash does not contain 64 characters.'
    [ "$line" = "$expected  $wanted" ] || fail 'The manifest does not contain the three expected paths in the correct format.'
    printf '%s  %s\n' "$expected" "$wanted" >> "$TEMP/manifest-checked.txt"
    if [ "$index" -eq 2 ]; then VERIFIED_MACHO=$expected; fi
done < "$MANIFEST"
[ "$index" -eq 3 ] || fail 'The manifest does not contain all three files.'
/usr/bin/cmp -s "$MANIFEST" "$TEMP/manifest-checked.txt" || fail 'The manifest is not in canonical format.'

ORIGINAL="$VOLUME/original/VoodooHDA.kext"
MODIFIED="$VOLUME/modified/VoodooHDA.kext"
validate_bundle_shape "$ORIGINAL"
validate_bundle_shape "$MODIFIED"
original_matches "$ORIGINAL" || fail 'The original copy does not match the verified VoodooHDA 3.6.8 payload.'
manifest_matches "$MODIFIED" || fail 'The saved V3 variant does not match the manifest.'
manifest_matches "$DRIVER" || fail 'The installed driver does not match the saved V3 variant.'

[ "$(readkey "$ORIGINAL/Contents/Info.plist" "$KEY")" = false ] || fail 'The original volume value is not false.'
/bin/cp "$ORIGINAL/Contents/Info.plist" "$TEMP/expected.plist" || fail 'Cannot copy the plist to the temporary directory.'
/usr/bin/plutil -replace "$KEY" -bool true "$TEMP/expected.plist" || fail 'Cannot derive the expected volume plist.'
/usr/bin/plutil -convert xml1 "$TEMP/expected.plist" || fail 'Cannot normalize the expected plist.'
/usr/bin/plutil -convert xml1 -o "$TEMP/actual.plist" "$MODIFIED/Contents/Info.plist" || fail 'The variant plist is invalid.'
/usr/bin/cmp -s "$TEMP/expected.plist" "$TEMP/actual.plist" || fail 'The variant plist contains changes beyond the volume correction.'
verify_signature "$ORIGINAL"
verify_signature "$MODIFIED"
verify_signature "$DRIVER"

# Catch changes made while validation was in progress. No writes occur outside
# our private /tmp directory, and no configuration or NVRAM data is read.
[ "$(hash "$STATE")" = "$STATE_HASH" ] || fail 'The state changed during verification.'
[ "$(hash "$MANIFEST")" = "$MANIFEST_HASH" ] || fail 'The manifest changed during verification.'
original_matches "$ORIGINAL" || fail 'The original copy changed during verification.'
manifest_matches "$MODIFIED" || fail 'The saved variant changed during verification.'
manifest_matches "$DRIVER" || fail 'The installed driver changed during verification.'
printf '%s\n' "$VERIFIED_MACHO"
