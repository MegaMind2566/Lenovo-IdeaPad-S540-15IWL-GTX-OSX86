#!/bin/bash
# Native macOS, Bash 3.2. No changes to the sealed system volume.
set -euo pipefail
export LC_ALL=C
GUID=7C436110-AB2A-4BBB-A880-FE41995C9F82
GPU='DeviceProperties.Add.PciRoot(0x0)/Pci(0x2,0x0)'
SIP="NVRAM.Add.$GUID.csr-active-config"
ARGS="NVRAM.Add.$GUID.boot-args"
DELETE="NVRAM.Delete.$GUID"
PAYLOAD_MANIFEST_SHA='774e27e9997fe5b7c84366f2222f3244b589196158fe5542bf49e1bf659ad7fe'
HERE=$(cd "$(dirname "$0")/.." && pwd -P)
ASSETS="$HERE/assets/audio-tahoe"
MODE=${1:-verify}
[ "$#" -eq 0 ] || shift
[ "$#" -le 1 ] || { echo 'Specify at most the boot disk path.'; exit 1; }
BOOTROOT=${1:-'/Volumes/240 GB'}
OC="$BOOTROOT/EFI/OC"
CONFIG="$OC/config.plist"
BACKUP="$OC/backup-audio-tahoe"
DRIVER=/Library/Extensions/VoodooHDA.kext
TEMP=''
DRAFT=''
STAGING=''
cleanup() {
    if [ -n "$STAGING" ] && [ -d "$STAGING" ]; then
        if [ ! -e "$DRIVER" ] && [ ! -L "$DRIVER" ] && [ -d "$STAGING/previous.kext" ]; then
            /usr/bin/sudo -n /bin/mv "$STAGING/previous.kext" "$DRIVER" || true
        fi
        /usr/bin/sudo -n /bin/rm -rf "$STAGING" || true
    fi
    if [ -n "$DRAFT" ] && [ -d "$DRAFT" ]; then /bin/rm -rf "$DRAFT"; fi
    if [ -n "$TEMP" ] && [ -d "$TEMP" ]; then /bin/rm -rf "$TEMP"; fi
}
trap cleanup EXIT
trap 'echo "Operation did not complete. Do not restart during an incomplete copy; keep the audio backup." >&2' ERR
fail() { echo "Operation cancelled: $*" >&2; exit 1; }
readkey() { /usr/bin/plutil -extract "$2" raw -o - "$1" 2>/dev/null; }
hash() { /usr/bin/shasum -a 256 "$1" | /usr/bin/awk '{print $1}'; }
ordinary() { [ -e "$1" ] && [ ! -L "$1" ] || fail "Missing path or symbolic link: $1"; }
no_links() { [ -z "$(/usr/bin/find "$1" -type l -print)" ] || fail 'The directory contains symbolic links.'; }
native() {
    [ "$(/usr/bin/uname -s)" = Darwin ] && [ "$(/usr/bin/uname -m)" = x86_64 ] || fail 'Intel macOS is required.'
    case "$(/usr/bin/uname -r)" in 25.*) ;; *) fail 'This test requires macOS Tahoe (Darwin 25).';; esac
    [ -d /System/Volumes/Data ] && [ -d /Users ] || fail 'Run the command from the Tahoe desktop, not Recovery.'
    [ "$(/usr/bin/id -u)" -ne 0 ] || fail 'Open the command from your own account. The password is requested only when needed.'
    for command in plutil shasum ditto codesign kmutil sudo base64; do
        [ -x "/usr/bin/$command" ] || fail "Required macOS command missing: $command."
    done
    for path in "$BOOTROOT" "$BOOTROOT/EFI" "$OC" "$OC/Kexts" "$CONFIG"; do ordinary "$path"; done
    [ -x /usr/sbin/nvram ] && [ -x /usr/sbin/ioreg ] && [ -x /usr/sbin/sysctl ] || fail 'Required nvram or ioreg utilities are missing.'
    /usr/bin/plutil -lint "$CONFIG" >/dev/null
}
kext_tree_hash() {
    no_links "$OC/Kexts"
    ( cd "$OC/Kexts"; /usr/bin/find . -type f -print | /usr/bin/sort | while IFS= read -r file; do
        [ -f "$file" ] || exit 1
        /usr/bin/shasum -a 256 "$file"
    done ) | /usr/bin/shasum -a 256 | /usr/bin/awk '{print $1}'
}
find_kext() {
    local i=0 entry
    while entry=$(readkey "$1" "Kernel.Add.$i.BundlePath"); do
        if [ "$entry" = "$2" ]; then printf '%s\n' "$i"; return 0; fi
        i=$((i+1))
    done
    return 1
}
append_csr_delete() {
    local file=$1 i=0 value found=0
    /usr/bin/plutil -extract "$DELETE" xml1 -o - "$file" | /usr/bin/grep -q '<array>' || fail 'NVRAM/Delete does not contain the expected array.'
    while value=$(readkey "$file" "$DELETE.$i"); do
        [ "$value" != csr-active-config ] || found=$((found+1))
        i=$((i+1))
    done
    [ "$found" -le 1 ] || fail 'csr-active-config appears more than once in NVRAM/Delete.'
    [ "$found" -ne 0 ] || /usr/bin/plutil -insert "$DELETE.$i" -string csr-active-config "$file"
}
validate_baseline() {
    local file=$1 args lilu
    [ "$(readkey "$file" "$SIP")" = AAAAAA== ] || fail 'Initial SIP is not Data 00000000.'
    /usr/bin/plutil -extract "$SIP" xml1 -o - "$file" | /usr/bin/grep -q '<data>' || fail 'csr-active-config must be Data.'
    [ "$(readkey "$file" Misc.Security.SecureBootModel)" = Disabled ] || fail 'SecureBootModel does not match the verified EFI.'
    [ "$(readkey "$file" "$GPU.AAPL,ig-platform-id")" = CQClPg== ] || fail 'The Intel platform is not 0900A53E.'
    [ "$(readkey "$file" "$GPU.device-id")" = pT4AAA== ] || fail 'The Intel device-id is not A53E0000.'
    [ "$(readkey "$file" "$GPU.framebuffer-patch-enable")" = AQAAAA== ] || fail 'The Intel memory correction is missing.'
    [ "$(readkey "$file" "$GPU.framebuffer-stolenmem")" = AAAwAQ== ] || fail 'framebuffer-stolenmem does not match.'
    [ "$(readkey "$file" "$GPU.framebuffer-fbmem")" = AACQAA== ] || fail 'framebuffer-fbmem does not match.'
    args=$(readkey "$file" "$ARGS")
    case " $args " in *' -igfxvesa '*|*' -x '*) fail 'Start from the desktop with Intel acceleration enabled.';; esac
    case " $args " in *' voodoo-layout-id='*) fail 'A VoodooHDA layout already exists. No changes made.';; esac
    ALC=$(find_kext "$file" AppleALC.kext) || fail 'AppleALC is missing from the configuration.'
    [ "$(readkey "$file" "Kernel.Add.$ALC.MaxKernel")" = 24.99.99 ] || fail 'The AppleALC Darwin limit does not match.'
    [ "$(readkey "$file" "Kernel.Add.$ALC.Enabled")" = true ] || fail 'AppleALC is not in the expected initial state.'
    lilu=$(find_kext "$file" Lilu.kext) || fail 'Lilu is missing from the configuration.'
    [ "$(readkey "$file" "Kernel.Add.$lilu.Enabled")" = true ] || fail 'Lilu must be enabled.'
    [ "$(readkey "$OC/Kexts/Lilu.kext/Contents/Info.plist" CFBundleVersion)" = 1.7.2 ] || fail 'The Lilu version does not match.'
}
accepted_original_sip() {
    case "$1" in AAAAAA==|ZwIAAA==) return 0;; *) fail 'Initial SIP is not one of the two verified states (00000000 or 67020000).';; esac
}
derive_states() {
    local before=$1 prepared=$2 restored=$3 original_sip=$4 args i=0 value
    accepted_original_sip "$original_sip"
    validate_baseline "$before"
    if [ "$original_sip" != AAAAAA== ]; then
        [ "$(readkey "$before" NVRAM.WriteFlash)" = true ] || fail 'WriteFlash must be enabled to preserve original SIP after restoration.'
        [ "$(readkey "$before" NVRAM.LegacyOverwrite)" = false ] || fail 'Legacy NVRAM could overwrite original SIP; no changes made.'
        while value=$(readkey "$before" "$DELETE.$i"); do
            [ "$value" != csr-active-config ] || fail 'The original config deletes SIP at every boot; preserving original active SIP requires changing that config.'
            i=$((i+1))
        done
    fi
    /bin/cp -p "$before" "$prepared"
    /bin/cp -p "$before" "$restored"
    /usr/bin/plutil -replace "$SIP" -data AwAAAA== "$prepared"
    /usr/bin/plutil -replace "$SIP" -data "$original_sip" "$restored"
    /usr/bin/plutil -replace "Kernel.Add.$ALC.Enabled" -bool false "$prepared"
    args=$(readkey "$before" "$ARGS")
    /usr/bin/plutil -replace "$ARGS" -string "$args voodoo-layout-id=11" "$prepared"
    append_csr_delete "$prepared"
    append_csr_delete "$restored"
    /usr/bin/plutil -lint "$prepared" "$restored" >/dev/null
}
atomic_config() {
    local wanted=$1 expected=$2 temp expected_wanted
    [ "$(hash "$CONFIG")" = "$expected" ] || fail 'The config changed during validation.'
    expected_wanted=$(hash "$wanted")
    temp=$(/usr/bin/mktemp "$OC/.audio-config.XXXXXX")
    /bin/cp -p "$wanted" "$temp"
    /usr/bin/plutil -lint "$temp" >/dev/null
    [ "$(hash "$temp")" = "$expected_wanted" ] || { /bin/rm -f "$temp"; fail 'Incomplete config copy.'; }
    [ "$(hash "$CONFIG")" = "$expected" ] || { /bin/rm -f "$temp"; fail 'The config changed during copying.'; }
    /bin/mv -f "$temp" "$CONFIG"
    if [ "$(hash "$CONFIG")" != "$expected_wanted" ]; then
        /bin/cp -p "$BACKUP/before.plist" "$CONFIG"
        fail 'Write verification failed; the original config was recovered.'
    fi
}
state_set() {
    local key=$1 value=$2 temp
    temp=$(/usr/bin/mktemp "$BACKUP/.state.XXXXXX")
    /bin/cp -p "$BACKUP/state.plist" "$temp"
    if readkey "$temp" "$key" >/dev/null; then
        /usr/bin/plutil -replace "$key" -string "$value" "$temp"
    else
        /usr/bin/plutil -insert "$key" -string "$value" "$temp"
    fi
    /usr/bin/plutil -lint "$temp" >/dev/null
    /bin/mv -f "$temp" "$BACKUP/state.plist"
}
load_backup() {
    local f
    ordinary "$BACKUP"; no_links "$BACKUP"
    for f in before prepared restore-sip state; do ordinary "$BACKUP/$f.plist"; /usr/bin/plutil -lint "$BACKUP/$f.plist" >/dev/null; done
    case "$(readkey "$BACKUP/state.plist" Format)" in
        2) ;;
        1) fail 'Audio backup version 1: no changes made. Use the original package to restore that test.';;
        *) fail 'Unknown backup format.';;
    esac
    ORIGINAL_SIP=$(readkey "$BACKUP/state.plist" OriginalSip) || fail 'The backup does not contain original SIP.'
    accepted_original_sip "$ORIGINAL_SIP"
    /usr/bin/plutil -extract OriginalSip xml1 -o - "$BACKUP/state.plist" | /usr/bin/grep -q '<data>' || fail 'Saved original SIP must be Data.'
    case "$(readkey "$BACKUP/state.plist" Phase)" in prepared|copying|installed|removal-pending|removal-requested|sip-pending|complete) ;; *) fail 'Unknown backup phase.';; esac
    for f in before prepared restore-sip; do
        [ "$(hash "$BACKUP/$f.plist")" = "$(readkey "$BACKUP/state.plist" "$f")" ] || fail 'The audio backup was modified.'
    done
    [ "$(kext_tree_hash)" = "$(readkey "$BACKUP/state.plist" EFI-Kexts)" ] || fail 'EFI kexts changed after the test.'
    /bin/mkdir -p "$TEMP/derived"
    derive_states "$BACKUP/before.plist" "$TEMP/derived/prepared.plist" "$TEMP/derived/restore-sip.plist" "$ORIGINAL_SIP"
    /usr/bin/cmp -s "$TEMP/derived/prepared.plist" "$BACKUP/prepared.plist" || fail 'The prepared snapshot is not the expected change.'
    /usr/bin/cmp -s "$TEMP/derived/restore-sip.plist" "$BACKUP/restore-sip.plist" || fail 'The SIP snapshot is not the expected change.'
    PHASE=$(readkey "$BACKUP/state.plist" Phase)
    BEFORE=$(hash "$BACKUP/before.plist")
    PREPARED=$(hash "$BACKUP/prepared.plist")
    RESTORE_SIP=$(hash "$BACKUP/restore-sip.plist")
    CURRENT=$(hash "$CONFIG")
    case "$CURRENT" in "$BEFORE"|"$PREPARED"|"$RESTORE_SIP") ;; *) fail 'The config changed after the test. It will not be overwritten.';; esac
}
active_sip() {
    local value normalized length
    /usr/sbin/nvram -x csr-active-config > "$TEMP/nvram.plist" || fail 'Cannot read csr-active-config from NVRAM.'
    /usr/bin/plutil -lint "$TEMP/nvram.plist" >/dev/null || fail 'The NVRAM output is not a valid plist.'
    /usr/bin/plutil -extract csr-active-config xml1 -o - "$TEMP/nvram.plist" | /usr/bin/grep -q '<data>' || fail 'Active csr-active-config is not Data.'
    value=$(readkey "$TEMP/nvram.plist" csr-active-config | /usr/bin/tr -d '[:space:]') || fail 'Cannot extract active SIP.'
    printf '%s' "$value" | /usr/bin/base64 -D > "$TEMP/sip.bin" || fail 'Active SIP is not valid Base64.'
    length=$(/usr/bin/wc -c < "$TEMP/sip.bin" | /usr/bin/tr -d '[:space:]')
    [ "$length" = 4 ] || fail 'Active csr-active-config must contain exactly four bytes.'
    normalized=$(/usr/bin/base64 < "$TEMP/sip.bin" | /usr/bin/tr -d '[:space:]') || fail 'Cannot normalize active SIP.'
    printf '%s\n' "$normalized"
}
require_sip3() {
    [ "$(active_sip)" = AwAAAA== ] || fail 'Restart with the prepared EFI; active SIP must be 03000000.'
}
runtime_bootargs() {
    local args
    args=$(/usr/sbin/sysctl -n kern.bootargs | /usr/bin/tr '[:space:]' ' ') || fail 'Cannot read the current session boot-args.'
    case " $args " in *' voodoo-layout-id=11 '*) ;; *) fail 'Restart from the prepared EFI; the audio layout is missing from active boot-args.';; esac
    case " $args " in *' -igfxvesa '*|*' -x '*) fail 'The current session uses VESA or safe boot.';; esac
}
boot_session() {
    local session
    session=$(/usr/sbin/sysctl -n kern.bootsessionuuid) || fail 'Cannot identify the boot session.'
    printf '%s' "$session" | /usr/bin/grep -Eq '^[A-Fa-f0-9]{8}(-[A-Fa-f0-9]{4}){3}-[A-Fa-f0-9]{12}$' || fail 'Unrecognized session identifier.'
    printf '%s\n' "$session"
}
audio_controller() {
    /usr/sbin/ioreg -r -n HDAS -l -w 0 > "$TEMP/controller.txt"
    /usr/bin/grep -qi 'HDAS@1F,3' "$TEMP/controller.txt" || fail 'The HDAS controller is not at the verified PCI path.'
    /usr/bin/grep -Eq '"vendor-id" = <86800000>|pci8086,' "$TEMP/controller.txt" || fail 'The Intel HDAS audio controller was not detected.'
}
validate_payload() {
    ordinary "$ASSETS/SHA256SUMS"
    [ "$PAYLOAD_MANIFEST_SHA" != MANIFEST_SHA_PENDING ] || fail 'The audio package is incomplete.'
    [ "$(hash "$ASSETS/SHA256SUMS")" = "$PAYLOAD_MANIFEST_SHA" ] || fail 'The audio manifest is unverified.'
    ordinary "$ASSETS/VoodooHDA.kext"; no_links "$ASSETS/VoodooHDA.kext"
    [ "$(/usr/bin/find "$ASSETS/VoodooHDA.kext" -type f | /usr/bin/wc -l | /usr/bin/tr -d ' ')" = 3 ] || fail 'The audio payload contains unexpected files.'
    (cd "$ASSETS"; /usr/bin/shasum -a 256 -c SHA256SUMS) >/dev/null || fail 'The audio driver failed SHA256 verification.'
    /usr/bin/codesign --verify --strict "$ASSETS/VoodooHDA.kext" || fail 'The audio driver signature is invalid.'
}
original_driver_matches() {
    local destination=$1 path expected actual
    ordinary "$destination"; no_links "$destination"
    [ "$(/usr/bin/find "$destination" -type f | /usr/bin/wc -l | /usr/bin/tr -d ' ')" = 3 ] || return 1
    while IFS=' ' read -r expected path; do
        path=${path# }; path=${path#VoodooHDA.kext/}
        [ -f "$destination/$path" ] || return 1
        actual=$(hash "$destination/$path")
        [ "$actual" = "$expected" ] || return 1
    done < "$ASSETS/SHA256SUMS"
}
VOLUME_KEY=IOKitPersonalities.VoodooHDA.VoodooHDAEnableVolumeChangeFix
VOLUME="$BACKUP/volume-test"
bundle_manifest_matches() {
    local destination=$1 manifest=$2 expected path actual
    ordinary "$destination"; no_links "$destination"
    [ "$(/usr/bin/find "$destination" -type f | /usr/bin/wc -l | /usr/bin/tr -d ' ')" = 3 ] || return 1
    while IFS=' ' read -r expected path; do
        path=${path# }
        case "$path" in Contents/Info.plist|Contents/MacOS/VoodooHDA|Contents/_CodeSignature/CodeResources) ;; *) return 1;; esac
        [ -f "$destination/$path" ] || return 1
        actual=$(hash "$destination/$path")
        [ "$actual" = "$expected" ] || return 1
    done < "$manifest"
}
validate_volume_backup() {
    local manifest_hash draft
    manifest_hash=$(readkey "$BACKUP/state.plist" VolumeManifestHash) || fail 'The volume backup reference is missing.'
    if [ ! -e "$VOLUME" ] && [ ! -L "$VOLUME" ]; then
        draft=$(readkey "$BACKUP/state.plist" VolumeDraftPath) || fail 'The volume backup is incomplete.'
        case "$draft" in "$BACKUP"/.volume-draft.*) ;; *) fail 'Invalid temporary volume path.';; esac
        ordinary "$draft"; no_links "$draft"
        ordinary "$draft/SHA256SUMS"
        [ "$(hash "$draft/SHA256SUMS")" = "$manifest_hash" ] || fail 'The temporary volume manifest does not match.'
        original_driver_matches "$draft/original/VoodooHDA.kext" || fail 'The original driver backup does not match.'
        bundle_manifest_matches "$draft/modified/VoodooHDA.kext" "$draft/SHA256SUMS" || fail 'The temporary volume driver does not match.'
        /bin/mv "$draft" "$VOLUME"
    fi
    ordinary "$VOLUME"; no_links "$VOLUME"
    ordinary "$VOLUME/SHA256SUMS"
    [ "$(hash "$VOLUME/SHA256SUMS")" = "$manifest_hash" ] || fail 'The volume manifest was modified.'
    [ "$(/usr/bin/wc -l < "$VOLUME/SHA256SUMS" | /usr/bin/tr -d ' ')" = 3 ] || fail 'The volume manifest does not contain three files.'
    original_driver_matches "$VOLUME/original/VoodooHDA.kext" || fail 'The original driver backup was modified.'
    bundle_manifest_matches "$VOLUME/modified/VoodooHDA.kext" "$VOLUME/SHA256SUMS" || fail 'The volume driver backup was modified.'
    /bin/cp "$VOLUME/original/VoodooHDA.kext/Contents/Info.plist" "$TEMP/expected-volume.plist"
    [ "$(readkey "$TEMP/expected-volume.plist" "$VOLUME_KEY")" = false ] || fail 'The original volume value does not match.'
    /usr/bin/plutil -replace "$VOLUME_KEY" -bool true "$TEMP/expected-volume.plist"
    /usr/bin/plutil -convert xml1 "$TEMP/expected-volume.plist"
    /usr/bin/plutil -convert xml1 -o "$TEMP/actual-volume.plist" "$VOLUME/modified/VoodooHDA.kext/Contents/Info.plist"
    /usr/bin/cmp -s "$TEMP/expected-volume.plist" "$TEMP/actual-volume.plist" || fail 'The volume plist contains additional changes.'
    /usr/bin/codesign --verify --strict "$VOLUME/modified/VoodooHDA.kext" || fail 'The volume backup signature is invalid.'
}
driver_matches() {
    if original_driver_matches "$1"; then return 0; fi
    if readkey "$BACKUP/state.plist" VolumeManifestHash >/dev/null; then
        validate_volume_backup
        bundle_manifest_matches "$1" "$VOLUME/SHA256SUMS"
    else
        return 1
    fi
}
make_volume_backup() {
    local draft manifest_hash state_temp path
    if readkey "$BACKUP/state.plist" VolumeManifestHash >/dev/null; then
        validate_volume_backup; return
    fi
    [ ! -e "$VOLUME" ] && [ ! -L "$VOLUME" ] || fail 'A volume backup exists without a verified reference.'
    original_driver_matches "$DRIVER" || fail 'The initial volume driver is not the verified original payload.'
    DRAFT=$(/usr/bin/mktemp -d "$BACKUP/.volume-draft.XXXXXX")
    draft=$DRAFT
    /bin/mkdir "$draft/original" "$draft/modified"
    /usr/bin/ditto --norsrc --noextattr --noacl --noqtn "$DRIVER" "$draft/original/VoodooHDA.kext"
    original_driver_matches "$draft/original/VoodooHDA.kext" || fail 'Incomplete original driver backup.'
    # Sign on the running macOS volume; the EFI backup volume can be FAT/exFAT.
    /bin/mkdir -p "$TEMP/volume-build"
    /usr/bin/ditto --norsrc --noextattr --noacl --noqtn "$draft/original/VoodooHDA.kext" "$TEMP/volume-build/VoodooHDA.kext"
    [ "$(readkey "$TEMP/volume-build/VoodooHDA.kext/Contents/Info.plist" "$VOLUME_KEY")" = false ] || fail 'The initial volume flag is not false.'
    /usr/bin/plutil -replace "$VOLUME_KEY" -bool true "$TEMP/volume-build/VoodooHDA.kext/Contents/Info.plist"
    /usr/bin/codesign --force --sign - "$TEMP/volume-build/VoodooHDA.kext"
    /usr/bin/codesign --verify --strict "$TEMP/volume-build/VoodooHDA.kext"
    /usr/bin/ditto --norsrc --noextattr --noacl --noqtn "$TEMP/volume-build/VoodooHDA.kext" "$draft/modified/VoodooHDA.kext"
    : > "$draft/SHA256SUMS"
    for path in Contents/Info.plist Contents/MacOS/VoodooHDA Contents/_CodeSignature/CodeResources; do
        printf '%s  %s\n' "$(hash "$draft/modified/VoodooHDA.kext/$path")" "$path" >> "$draft/SHA256SUMS"
    done
    manifest_hash=$(hash "$draft/SHA256SUMS")
    state_temp=$(/usr/bin/mktemp "$BACKUP/.state.XXXXXX")
    /bin/cp -p "$BACKUP/state.plist" "$state_temp"
    /usr/bin/plutil -insert VolumeManifestHash -string "$manifest_hash" "$state_temp"
    /usr/bin/plutil -insert VolumeDraftPath -string "$draft" "$state_temp"
    /usr/bin/plutil -insert VolumePhase -string ready "$state_temp"
    /usr/bin/plutil -insert VolumePrevious -string original "$state_temp"
    /usr/bin/plutil -insert VolumeTarget -string original "$state_temp"
    /usr/bin/plutil -lint "$state_temp" >/dev/null
    /bin/mv -f "$state_temp" "$BACKUP/state.plist"
    DRAFT=
    /bin/mv "$draft" "$VOLUME"
    validate_volume_backup
}
volume_source() {
    case "$1" in original|modified) printf '%s/%s/VoodooHDA.kext\n' "$VOLUME" "$1";; *) fail 'Unknown volume driver state.';; esac
}
stage_volume_driver() {
    local source=$1
    STAGING=$(/usr/bin/sudo /usr/bin/mktemp -d /Library/Extensions/.s540-audio.XXXXXX)
    /usr/bin/sudo /bin/chmod 755 "$STAGING"
    /usr/bin/sudo /usr/bin/ditto --norsrc --noextattr --noacl --noqtn "$source" "$STAGING/VoodooHDA.kext"
    /usr/bin/sudo /usr/sbin/chown -R root:wheel "$STAGING/VoodooHDA.kext"
    /usr/bin/sudo /usr/bin/find "$STAGING/VoodooHDA.kext" -type d -exec /bin/chmod 755 {} +
    /usr/bin/sudo /usr/bin/find "$STAGING/VoodooHDA.kext" -type f -exec /bin/chmod 644 {} +
    /usr/bin/sudo /bin/chmod 755 "$STAGING/VoodooHDA.kext/Contents/MacOS/VoodooHDA"
    driver_matches "$STAGING/VoodooHDA.kext" || fail 'The temporary volume copy is unverified.'
    /usr/bin/codesign --verify --strict "$STAGING/VoodooHDA.kext"
}
resume_volume_swap() {
    local phase previous source
    if ! phase=$(readkey "$BACKUP/state.plist" VolumePhase); then return; fi
    case "$phase" in ready) return;; swapping) ;; *) fail 'Unknown volume phase.';; esac
    validate_volume_backup
    if [ -e "$DRIVER" ] || [ -L "$DRIVER" ]; then
        driver_matches "$DRIVER" || fail 'The driver changed during volume replacement.'
    else
        previous=$(readkey "$BACKUP/state.plist" VolumePrevious)
        source=$(volume_source "$previous")
        /usr/bin/sudo -v
        stage_volume_driver "$source"
        /usr/bin/sudo /bin/mv "$STAGING/VoodooHDA.kext" "$DRIVER"
        /usr/bin/sudo /bin/rmdir "$STAGING"
        STAGING=
    fi
    state_set VolumePhase ready
}
volume_driver() {
    local wanted=$1 source previous result=0
    load_backup; validate_payload
    [ "$PHASE" = installed ] && [ "$CURRENT" = "$PREPARED" ] || fail 'The audio test is not in the expected installed state.'
    require_sip3; runtime_bootargs
    if [ "$wanted" = modified ]; then
        make_volume_backup
    else
        validate_volume_backup
    fi
    resume_volume_swap
    driver_matches "$DRIVER" || fail 'The installed driver does not belong to this test.'
    source=$(volume_source "$wanted")
    if original_driver_matches "$DRIVER"; then previous=original; else previous=modified; fi
    if [ "$previous" != "$wanted" ]; then
        /usr/bin/sudo -v
        stage_volume_driver "$source"
        state_set VolumePrevious "$previous"
        state_set VolumeTarget "$wanted"
        state_set VolumePhase swapping
        /usr/bin/sudo /bin/mv "$DRIVER" "$STAGING/previous.kext"
        /usr/bin/sudo /bin/mv "$STAGING/VoodooHDA.kext" "$DRIVER"
        driver_matches "$DRIVER" || fail 'Volume replacement is unverified.'
        state_set VolumePhase ready
        /usr/bin/sudo /bin/rm -rf "$STAGING"
        STAGING=
    fi
    /usr/bin/sudo /usr/bin/kmutil rebuild || result=$?
    case "$result" in 0|27|28) ;; *) fail "AuxKC rebuild did not complete: code $result. The test driver and SIP are preserved.";; esac
    if [ "$wanted" = modified ]; then
        echo 'Volume correction prepared: only VoodooHDAEnableVolumeChangeFix=true.'
    else
        echo 'The original audio driver was restored byte for byte. The test config and SIP are unchanged.'
    fi
    echo 'Approve rebuilding in Privacy & Security if prompted. Restart, then test volume and mute and open VERIFICA-AUDIO.command.'
}
loaded_voodoo() {
    /usr/bin/kmutil showloaded > "$TEMP/runtime-kexts.txt" || fail 'Cannot verify loaded drivers. Test SIP is preserved.'
    /usr/bin/grep -qi 'org.voodoo.driver.VoodooHDA' "$TEMP/runtime-kexts.txt"
}
aux_without_voodoo() {
    /usr/bin/kmutil showloaded --collection aux --show all > "$TEMP/aux-kexts.txt" || fail 'Cannot verify the AuxKC collection. Test SIP is preserved.'
    /usr/bin/grep -qi 'org.voodoo.driver.VoodooHDA' "$TEMP/aux-kexts.txt" && fail 'VoodooHDA remains in the AuxKC collection. Complete approval and restart.'
    return 0
}
prepare() {
    validate_payload
    audio_controller
    if [ -e "$BACKUP" ] || [ -L "$BACKUP" ]; then
        load_backup
        [ "$PHASE" = prepared ] || fail 'An audio test already exists in another phase.'
        if [ "$CURRENT" = "$BEFORE" ]; then
            [ "$(active_sip)" = "$ORIGINAL_SIP" ] || fail 'The SIP state does not match the state saved before the test.'
            atomic_config "$BACKUP/prepared.plist" "$CURRENT"
        elif [ "$CURRENT" != "$PREPARED" ]; then
            fail 'A SIP restoration state already exists.'
        fi
        echo 'Preparation already exists. Restart, then open INSTALLA-AUDIO.command.'; return
    fi
    validate_baseline "$CONFIG"
    ORIGINAL_SIP=$(active_sip)
    accepted_original_sip "$ORIGINAL_SIP"
    derive_states "$CONFIG" "$TEMP/prepared.plist" "$TEMP/restore-sip.plist" "$ORIGINAL_SIP"
    CURRENT=$(hash "$CONFIG")
    local final_backup=$BACKUP
    DRAFT=$(/usr/bin/mktemp -d "$OC/.backup-audio.XXXXXX")
    BACKUP=$DRAFT
    /bin/cp -p "$CONFIG" "$BACKUP/before.plist"
    /bin/cp -p "$TEMP/prepared.plist" "$BACKUP/prepared.plist"
    /bin/cp -p "$TEMP/restore-sip.plist" "$BACKUP/restore-sip.plist"
    cat > "$BACKUP/state.plist" <<STATE
<?xml version="1.0" encoding="UTF-8"?><!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd"><plist version="1.0"><dict>
<key>Format</key><string>2</string><key>Phase</key><string>prepared</string>
<key>OriginalSip</key><data>$ORIGINAL_SIP</data>
<key>before</key><string>$(hash "$BACKUP/before.plist")</string>
<key>prepared</key><string>$(hash "$BACKUP/prepared.plist")</string>
<key>restore-sip</key><string>$(hash "$BACKUP/restore-sip.plist")</string>
<key>EFI-Kexts</key><string>$(kext_tree_hash)</string>
</dict></plist>
STATE
    /usr/bin/plutil -lint "$BACKUP/state.plist" >/dev/null
    load_backup
    [ "$(hash "$CONFIG")" = "$CURRENT" ] || fail 'The config changed during preparation.'
    [ "$(active_sip)" = "$ORIGINAL_SIP" ] || fail 'Active SIP changed during preparation.'
    /bin/mv "$DRAFT" "$final_backup"
    DRAFT=
    BACKUP=$final_backup
    atomic_config "$BACKUP/prepared.plist" "$CURRENT"
    echo 'Preparation complete. Restart with this EFI, then open INSTALLA-AUDIO.command.'
    echo 'Only SIP, NVRAM/Delete csr-active-config, AppleALC Enabled and the VoodooHDA layout changed.'
}
install_driver() {
    load_backup; validate_payload
    [ "$CURRENT" = "$PREPARED" ] || fail 'The prepared EFI is not active on the boot disk.'
    case "$PHASE" in prepared|copying|installed) ;; *) fail 'The test is being restored.';; esac
    require_sip3; runtime_bootargs; audio_controller
    /usr/bin/kmutil showloaded > "$TEMP/loaded.txt" || fail 'Cannot verify already loaded drivers.' 
    /usr/bin/grep -Eq 'com\.apple\.driver\.AppleHDA|as\.vit9696\.AppleALC' "$TEMP/loaded.txt" && fail 'An incompatible AppleHDA/AppleALC driver is active.'
    [ ! -e /Library/Extensions/AppleHDA.kext ] && [ ! -L /Library/Extensions/AppleHDA.kext ] || fail 'AppleHDA is already installed in Library/Extensions.'
    if [ -e "$DRIVER" ] || [ -L "$DRIVER" ]; then
        [ "$PHASE" != prepared ] && driver_matches "$DRIVER" || fail 'A VoodooHDA driver outside this test is present.'
    else
        case "$PHASE" in prepared|copying) ;; *) fail 'The test driver was removed outside the restoration process.';; esac
        /usr/bin/sudo -v
        STAGING=$(/usr/bin/sudo /usr/bin/mktemp -d /Library/Extensions/.s540-audio.XXXXXX)
        /usr/bin/sudo /bin/chmod 755 "$STAGING"
        /usr/bin/sudo /usr/bin/ditto "$ASSETS/VoodooHDA.kext" "$STAGING/VoodooHDA.kext"
        /usr/bin/sudo /usr/sbin/chown -R root:wheel "$STAGING/VoodooHDA.kext"
        /usr/bin/sudo /usr/bin/find "$STAGING/VoodooHDA.kext" -type d -exec /bin/chmod 755 {} +
        /usr/bin/sudo /usr/bin/find "$STAGING/VoodooHDA.kext" -type f -exec /bin/chmod 644 {} +
        /usr/bin/sudo /bin/chmod 755 "$STAGING/VoodooHDA.kext/Contents/MacOS/VoodooHDA"
        driver_matches "$STAGING/VoodooHDA.kext" || fail 'Incomplete driver copy. The temporary copy will be removed.'
        /usr/bin/codesign --verify --strict "$STAGING/VoodooHDA.kext"
        state_set Phase copying
        /usr/bin/sudo /bin/mv "$STAGING/VoodooHDA.kext" "$DRIVER"
        /usr/bin/sudo /bin/rmdir "$STAGING"
        STAGING=
    fi
    state_set Phase installed
    local result=0
    /usr/bin/sudo /usr/bin/kmutil load -p "$DRIVER" || result=$?
    case "$result" in 0) echo 'Load request completed.';; 27|28) echo 'macOS requires driver approval or a restart.';; *) fail "kmutil returned $result. Do not change SIP further.";; esac
    echo 'Open System Settings > Privacy & Security and approve the driver if prompted. Then restart and open VERIFICA-AUDIO.command.'
}
verify() {
    /usr/sbin/system_profiler SPAudioDataType
    /usr/sbin/ioreg -r -c VoodooHDADevice -l -w 0 | /usr/bin/grep 'VoodooHDAEnableVolumeChangeFix' || true
    /usr/bin/kmutil showloaded 2>/dev/null | /usr/bin/grep -E 'AppleHDA|AppleALC|Lilu|VoodooHDA' || true
    echo 'Check speakers, headphones and microphone in Sound settings. No changes made.'
}
restore() {
    load_backup; validate_payload
    case "$PHASE" in
        prepared)
            if [ "$CURRENT" = "$RESTORE_SIP" ] && [ "$RESTORE_SIP" != "$BEFORE" ]; then
                state_set Phase sip-pending
                restore; return
            fi
            if [ "$CURRENT" = "$BEFORE" ]; then
                [ "$(active_sip)" = "$ORIGINAL_SIP" ] || fail 'Restart before completing; SIP must match the saved original state.'
                [ ! -e "$DRIVER" ] && [ ! -L "$DRIVER" ] || fail 'An untracked driver is present.'
                loaded_voodoo && fail 'VoodooHDA is still loaded.'
                state_set Phase complete
                echo 'The original config is already present; restoration complete.'; return
            fi
            [ "$CURRENT" = "$PREPARED" ] || fail 'The prepared state does not match.'
            [ ! -e "$DRIVER" ] && [ ! -L "$DRIVER" ] || fail 'An untracked driver is present; it will not be removed.'
            atomic_config "$BACKUP/restore-sip.plist" "$CURRENT"
            state_set Phase sip-pending
            echo 'Original SIP prepared. Restart, then reopen RIPRISTINA-AUDIO.command for byte-for-byte restoration.'
            ;;
        copying)
            [ "$CURRENT" = "$PREPARED" ] || fail 'The prepared state does not match.'
            if [ -e "$DRIVER" ] || [ -L "$DRIVER" ]; then
                driver_matches "$DRIVER" || fail 'The driver being copied does not match.'
                state_set Phase installed
                restore
            else
                state_set Phase prepared
                restore
            fi
            ;;
        installed|removal-pending)
            [ "$CURRENT" = "$PREPARED" ] || fail 'Keep the test EFI until the driver is removed.'
            require_sip3
            resume_volume_swap
            if [ "$PHASE" = installed ]; then
                driver_matches "$DRIVER" || fail 'The installed driver was modified; it will not be removed.'
                [ ! -e "$BACKUP/removed-VoodooHDA.kext" ] && [ ! -L "$BACKUP/removed-VoodooHDA.kext" ] || fail 'A driver already exists in the backup.'
                state_set Phase removal-pending
                /usr/bin/sudo /bin/mv "$DRIVER" "$BACKUP/removed-VoodooHDA.kext"
            elif [ -e "$DRIVER" ] || [ -L "$DRIVER" ]; then
                driver_matches "$DRIVER" || fail 'The driver being removed does not match.'
                [ ! -e "$BACKUP/removed-VoodooHDA.kext" ] || fail 'Two copies of the driver being removed are present.'
                /usr/bin/sudo /bin/mv "$DRIVER" "$BACKUP/removed-VoodooHDA.kext"
            fi
            driver_matches "$BACKUP/removed-VoodooHDA.kext" || fail 'The driver moved into the backup does not match.'
            state_set RemovalBoot "$(boot_session)"
            if loaded_voodoo; then
                local result=0
                /usr/bin/sudo /usr/bin/kmutil rebuild || result=$?
                case "$result" in 0|27|28) ;; *) fail "AuxKC rebuild did not complete: code $result. Test SIP remains active.";; esac
                state_set Phase removal-requested
                echo 'Removal requested. Approve rebuilding in Privacy & Security if prompted, then restart and reopen RIPRISTINA-AUDIO.command.'
            else
                # A reboot/approval is still required to prove the rebuilt collection no longer includes the driver.
                local result=0
                /usr/bin/sudo /usr/bin/kmutil rebuild || result=$?
                case "$result" in 0|27|28) ;; *) fail "AuxKC rebuild did not complete: code $result. Test SIP remains active.";; esac
                state_set Phase removal-requested
                echo 'Restart, then reopen RIPRISTINA-AUDIO.command. The test EFI remains active until verification.'
            fi
            ;;
        removal-requested)
            if [ "$CURRENT" = "$RESTORE_SIP" ] && [ "$RESTORE_SIP" != "$BEFORE" ]; then
                state_set Phase sip-pending
                restore; return
            fi
            [ "$CURRENT" = "$PREPARED" ] || fail 'The config changed during removal.'
            [ "$(boot_session)" != "$(readkey "$BACKUP/state.plist" RemovalBoot)" ] || fail 'Restart before continuing; removal must be verified in a new session.'
            [ ! -e "$DRIVER" ] && [ ! -L "$DRIVER" ] || fail 'The driver is still installed.'
            loaded_voodoo && fail 'VoodooHDA is still loaded. Complete approval and restart before restoring SIP.'
            aux_without_voodoo
            atomic_config "$BACKUP/restore-sip.plist" "$CURRENT"
            state_set Phase sip-pending
            echo 'Driver absent. Original SIP prepared. Restart and reopen RIPRISTINA-AUDIO.command to finish.'
            ;;
        sip-pending)
            if [ "$CURRENT" = "$BEFORE" ]; then
                [ "$(active_sip)" = "$ORIGINAL_SIP" ] || fail 'Saved original SIP is not active yet.'
                loaded_voodoo && fail 'VoodooHDA is still loaded.'
                state_set Phase complete
                echo 'The original config was already restored byte for byte.'; return
            fi
            [ "$CURRENT" = "$RESTORE_SIP" ] || fail 'The SIP restoration config does not match.'
            [ "$(active_sip)" = "$ORIGINAL_SIP" ] || fail 'Restart before finishing; active SIP must match saved original SIP.'
            loaded_voodoo && fail 'VoodooHDA is still loaded.'
            atomic_config "$BACKUP/before.plist" "$CURRENT"
            state_set Phase complete
            echo 'The original config was restored byte for byte. The audio backup is preserved.'
            ;;
        complete)
            [ "$CURRENT" = "$BEFORE" ] || fail 'The config changed after restoration.'
            [ "$(active_sip)" = "$ORIGINAL_SIP" ] || fail 'Active SIP changed after restoration.'
            echo 'Restoration already complete. No changes made.'
            ;;
        *) fail 'Unknown backup phase.';;
    esac
}
native
TEMP=$(/usr/bin/mktemp -d /tmp/s540-audio.XXXXXX)
case "$MODE" in prepare) prepare;; install) install_driver;; verify) verify;; restore) restore;; volume) volume_driver modified;; volume-restore) volume_driver original;; *) fail 'Unknown operation.';; esac
