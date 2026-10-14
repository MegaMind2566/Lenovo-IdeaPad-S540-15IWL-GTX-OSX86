#!/bin/bash
# Native macOS / Bash 3.2. Guarded offline-on-reboot driver test.
# No config.plist, SIP, NVRAM, AMFI or live driver loading changes.
set -euo pipefail
umask 077
export LC_ALL=C

PAYLOAD_MANIFEST_SHA='VOLUME_MANIFEST_SHA_PENDING'
TEST_VERSION='3.6.10'
KEY='IOKitPersonalities.VoodooHDA.VoodooHDAEnableVolumeChangeFix'
SOURCE_BACKUP_REL='/Library/Application Support/S540-microfono'
BACKUP_REL='/Library/Application Support/S540-volume-fine'
TEMP=''
ROOT_DATA=''
RECOVERY=0
SYSTEM_ROOT=''
RECOVERY_GROUP_MATCH=0
MODE=${1:-}
cleanup() { [ -z "$TEMP" ] || /bin/rm -rf "$TEMP"; }
trap cleanup EXIT
fail() { printf 'Volume correction: %s\n' "$*" >&2; exit 1; }
hash() {
    if [ -x /usr/bin/shasum ]; then /usr/bin/shasum -a 256 "$1" | /usr/bin/awk '{print $1}';
    elif [ -x /usr/bin/openssl ]; then /usr/bin/openssl dgst -sha256 "$1" | /usr/bin/awk '{print $NF}';
    else fail 'No native SHA256 reader is available.'; fi
}
ordinary_file() { [ -f "$1" ] && [ ! -L "$1" ]; }
readkey() { /usr/bin/plutil -extract "$2" raw -o - "$1" 2>/dev/null; }
safe_path() {
    local path=$1
    case "$path" in /*) ;; *) fail 'An absolute path is required.';; esac
    case "$path" in *$'\n'*|*/../*|*/./*|*/..|*/.) fail 'The path contains unsupported components.';; esac
    while [ "$path" != / ]; do
        [ ! -L "$path" ] || fail 'The path contains a symbolic link.'
        path=${path%/*}; [ -n "$path" ] || path=/
    done
}
validate_shape() {
    local bundle=$1 path count
    safe_path "$bundle"
    [ -d "$bundle" ] || fail "Missing bundle: $bundle"
    [ -z "$(/usr/bin/find "$bundle" ! -type f ! -type d -print)" ] || fail 'The bundle contains links or special files.'
    count=$(/usr/bin/find "$bundle" -type f -print | /usr/bin/wc -l | /usr/bin/tr -d '[:space:]')
    [ "$count" = 3 ] || fail 'The bundle must contain only the three expected files.'
    for path in Contents/Info.plist Contents/MacOS/VoodooHDA Contents/_CodeSignature/CodeResources; do
        ordinary_file "$bundle/$path" || fail 'An expected bundle file is missing or is not a regular file.'
    done
}
check_manifest() {
    local manifest=$1 index=0 line expected wanted
    ordinary_file "$manifest" || fail 'The driver manifest is missing.'
    : > "$TEMP/manifest-canonical"
    while IFS= read -r line || [ -n "$line" ]; do
        index=$((index + 1))
        case "$index" in
            1) wanted=Contents/Info.plist;;
            2) wanted=Contents/MacOS/VoodooHDA;;
            3) wanted=Contents/_CodeSignature/CodeResources;;
            *) fail 'The manifest contains extra files.';;
        esac
        expected=${line%% *}
        case "$expected" in ''|*[!0-9a-f]*) fail 'Invalid manifest hash.';; esac
        [ "${#expected}" -eq 64 ] || fail 'Incomplete manifest hash.'
        [ "$line" = "$expected  $wanted" ] || fail 'Invalid manifest paths or format.'
        printf '%s  %s\n' "$expected" "$wanted" >> "$TEMP/manifest-canonical"
    done < "$manifest"
    [ "$index" -eq 3 ] && /usr/bin/cmp -s "$manifest" "$TEMP/manifest-canonical" || fail 'The manifest is not in canonical format.'
}
bundle_matches() {
    local bundle=$1 manifest=$2 expected path
    validate_shape "$bundle"
    check_manifest "$manifest"
    while IFS=' ' read -r expected path; do
        path=${path# }
        [ "$(hash "$bundle/$path")" = "$expected" ] || return 1
    done < "$manifest"
}
save_manifest() {
    local bundle=$1 destination=$2 path
    : > "$destination"
    for path in Contents/Info.plist Contents/MacOS/VoodooHDA Contents/_CodeSignature/CodeResources; do
        printf '%s  %s\n' "$(hash "$bundle/$path")" "$path" >> "$destination"
    done
}
verify_signature() {
    if [ ! -x /usr/bin/codesign ] && [ "$RECOVERY" -eq 1 ]; then
        printf 'Recovery: codesign is unavailable; the signature was not rechecked. Exact file hashes from the private backup remain mandatory.\n' >&2
        return 0
    fi
    /usr/bin/codesign --verify --strict "$1" || fail 'Invalid driver signature.'
}
check_owned_directory() {
    local path=$1 mode
    safe_path "$path"
    [ -d "$path" ] || fail "Missing directory: $path"
    [ "$(/usr/bin/stat -f %u "$path")" = 0 ] || fail 'The driver/backup directory is not owned by root.'
    mode=$(/usr/bin/stat -f %Lp "$path")
    [ "$((8#$mode & 022))" -eq 0 ] || fail 'The driver/backup directory is writable by other users.'
}
check_owned_backup() {
    local path mode
    check_owned_directory "$BACKUP"
    [ "$(/usr/bin/stat -f %Lp "$BACKUP")" = 700 ] || fail 'The backup must remain private (permissions 700).'
    while IFS= read -r path; do
        [ ! -L "$path" ] && [ "$(/usr/bin/stat -f %u "$path")" = 0 ] || fail 'A backup entry is not owned by root or is a link.'
        mode=$(/usr/bin/stat -f %Lp "$path")
        [ "$((8#$mode & 022))" -eq 0 ] || fail 'A backup entry is writable by other users.'
    done < <(/usr/bin/find "$BACKUP" -print)
}
verify_macho_header() {
    # Byte inspection uses a macOS system utility, without developer-tool shims.
    # Require a complete little-endian, thin x86_64 MH_KEXT_BUNDLE header.
    /usr/bin/od -An -N16 -v -tx1 "$1" | /usr/bin/awk '
        { for (i = 1; i <= NF; i++) {
            bytes[++count] = $i
            if (length($i) != 2 || $i ~ /[^0-9a-f]/) invalid = 1
        } }
        END { exit !(count == 16 && !invalid &&
            bytes[1] == "cf" && bytes[2] == "fa" && bytes[3] == "ed" && bytes[4] == "fe" &&
            bytes[5] == "07" && bytes[6] == "00" && bytes[7] == "00" && bytes[8] == "01" &&
            bytes[13] == "0b" && bytes[14] == "00" && bytes[15] == "00" && bytes[16] == "00") }
    '
}
verify_payload() {
    case "$PAYLOAD_MANIFEST_SHA" in ''|*[!0-9a-f]*) fail 'This package does not yet contain the compiled driver with locked hashes.';; esac
    [ "${#PAYLOAD_MANIFEST_SHA}" -eq 64 ] || fail 'Incomplete payload hash.'
    [ "$(hash "$PAYLOAD_SUMS")" = "$PAYLOAD_MANIFEST_SHA" ] || fail 'The new driver manifest does not match the package.'
    bundle_matches "$PAYLOAD" "$PAYLOAD_SUMS" || fail 'The new driver does not match the manifest.'
    [ "$(readkey "$PAYLOAD/Contents/Info.plist" CFBundleIdentifier)" = org.voodoo.driver.VoodooHDA ] || fail 'Unexpected driver identifier.'
    [ "$(readkey "$PAYLOAD/Contents/Info.plist" CFBundleVersion)" = "$TEST_VERSION" ] || fail 'Unexpected new driver version.'
    [ "$(readkey "$PAYLOAD/Contents/Info.plist" "$KEY")" = true ] || fail 'The volume correction must remain enabled.'
    [ "$(readkey "$PAYLOAD/Contents/Info.plist" IOKitPersonalities.VoodooHDA.S540InputGainFix)" = true ] || fail 'The expected microphone correction is not enabled in the payload.'
    [ "$(readkey "$PAYLOAD/Contents/Info.plist" IOKitPersonalities.VoodooHDA.S540OutputRangeFix)" = true ] || fail 'The expected output-range correction is not enabled in the payload.'
    if [ "$RECOVERY" -ne 1 ]; then
        verify_macho_header "$PAYLOAD/Contents/MacOS/VoodooHDA" || fail 'The payload is not an Intel x86_64 kernel bundle with a complete header.'
    fi
    verify_signature "$PAYLOAD"
}
volume_uuid() {
    local role
    /usr/sbin/diskutil info -plist "$ROOT_DATA" > "$TEMP/data-volume.plist" || fail 'Cannot identify the Data volume.'
    [ "$(readkey "$TEMP/data-volume.plist" FilesystemType)" = apfs ] || fail 'The Data volume must use APFS.'
    [ "$(readkey "$TEMP/data-volume.plist" MountPoint)" = "$ROOT_DATA" ] || fail 'The Data path must be the volume mount point, not a subdirectory.'
    role=$(readkey "$TEMP/data-volume.plist" APFSVolumeRole.0) || role=$(readkey "$TEMP/data-volume.plist" APFSVolumeRole) || role=''
    [ -z "$role" ] || [ "$role" = Data ] || fail 'The volume has an APFS role other than Data.'
    VOLUME_UUID=$(readkey "$TEMP/data-volume.plist" VolumeUUID) || fail 'The Data volume UUID is missing.'
    case "$VOLUME_UUID" in ''|*[!A-Fa-f0-9-]*) fail 'Invalid Data volume UUID.';; esac
    [ "${#VOLUME_UUID}" -eq 36 ] || fail 'Incomplete Data volume UUID.'
}
recovery_system() {
    local data_group system_group role
    [ -n "$SYSTEM_ROOT" ] || return 0
    safe_path "$SYSTEM_ROOT"
    ordinary_file "$SYSTEM_ROOT/System/Library/CoreServices/SystemVersion.plist" || fail 'The System path does not contain a macOS system.'
    /usr/sbin/diskutil info -plist "$SYSTEM_ROOT" > "$TEMP/system-volume.plist" || fail 'Cannot identify the System volume.'
    [ "$(readkey "$TEMP/system-volume.plist" FilesystemType)" = apfs ] || fail 'The System volume must use APFS.'
    [ "$(readkey "$TEMP/system-volume.plist" MountPoint)" = "$SYSTEM_ROOT" ] || fail 'The System path must be the volume mount point.'
    role=$(readkey "$TEMP/system-volume.plist" APFSVolumeRole.0) || role=$(readkey "$TEMP/system-volume.plist" APFSVolumeRole) || role=''
    [ -z "$role" ] || [ "$role" = System ] || fail 'The volume has an APFS role other than System.'
    data_group=$(readkey "$TEMP/data-volume.plist" APFSVolumeGroupUUID) || data_group=''
    system_group=$(readkey "$TEMP/system-volume.plist" APFSVolumeGroupUUID) || system_group=''
    if [ -n "$data_group" ] && [ -n "$system_group" ]; then
        [ "$data_group" = "$system_group" ] || fail 'System and Data belong to different APFS volume groups.'
        RECOVERY_GROUP_MATCH=1
    fi
}
runtime_sip() {
    /usr/sbin/nvram -x csr-active-config > "$TEMP/sip.plist" || fail 'Cannot read the active SIP configuration.'
    [ "$(readkey "$TEMP/sip.plist" csr-active-config)" = AwAAAA== ] || fail 'Active SIP must match the audio test configuration (03000000).'
}
write_phase() {
    local phase=$1 next="$BACKUP/state-next.plist"
    if [ -e "$next" ] || [ -L "$next" ]; then
        ordinary_file "$next" && [ "$(/usr/bin/stat -f %u "$next")" = 0 ] || fail 'The temporary state is not a regular file owned by root.'
        /usr/bin/plutil -lint "$next" > /dev/null || fail 'The temporary state is invalid.'
        /bin/cp "$next" "$TEMP/state-draft-check.plist"
        /usr/bin/plutil -replace Phase -string "$(readkey "$STATE" Phase)" "$TEMP/state-draft-check.plist"
        /usr/bin/plutil -convert xml1 "$TEMP/state-draft-check.plist"
        /usr/bin/plutil -convert xml1 -o "$TEMP/state-live-check.plist" "$STATE"
        /usr/bin/cmp -s "$TEMP/state-draft-check.plist" "$TEMP/state-live-check.plist" || fail 'The temporary state contains changes beyond the phase; the test has stopped.'
        # An interrupted atomic write never became the committed state. Its
        # phase is discarded; actual driver fingerprints decide the next step.
        /bin/rm "$next"
    fi
    /bin/cp "$STATE" "$next"
    /usr/bin/plutil -replace Phase -string "$phase" "$next"
    /usr/bin/plutil -lint "$next" > /dev/null
    /bin/chmod 600 "$next"
    /bin/mv -f "$next" "$STATE"
    PHASE=$phase
}
load_state() {
    local item
    check_owned_backup
    ordinary_file "$STATE" || fail 'The test state is missing.'
    [ "$(/usr/bin/stat -f %u "$STATE")" = 0 ] || fail 'The test state is not owned by root.'
    /usr/bin/plutil -lint "$STATE" > /dev/null
    [ "$(readkey "$STATE" Format)" = 1 ] || fail 'Unrecognized state format.'
    [ "$(readkey "$STATE" VolumeUUID)" = "$VOLUME_UUID" ] || fail 'This backup belongs to another Data volume.'
    [ "$(readkey "$STATE" PayloadManifestHash)" = "$PAYLOAD_MANIFEST_SHA" ] || fail 'The backup belongs to another test package.'
    [ "$(readkey "$STATE" OriginalManifestHash)" = "$(hash "$ORIGINAL_SUMS")" ] || fail 'The backup manifest has changed.'
    bundle_matches "$ORIGINAL" "$ORIGINAL_SUMS" || fail 'The saved working audio driver has changed.'
    verify_signature "$ORIGINAL"
    PHASE=$(readkey "$STATE" Phase)
    case "$PHASE" in staging|swapping|swapped|rebuildpending|approvalpending|rebootrequired|verified|restoring|restoreswapped|restorepending|restoreapprovalpending|restorerebootrequired|restored) ;; *) fail 'Unrecognized test phase.';; esac
    for item in OriginalBootSessionUUID; do
        [ -n "$(readkey "$STATE" "$item")" ] || fail 'The test state is incomplete.'
    done
}
backup_paths() {
    BACKUP=$1
    STATE="$BACKUP/state.plist"
    ORIGINAL="$BACKUP/original.kext"
    ORIGINAL_SUMS="$BACKUP/original-SHA256SUMS"
}
copy_driver() {
    local from=$1 to=$2 sums=$3
    [ ! -e "$to" ] && [ ! -L "$to" ] || fail 'An unexpected staging directory already exists.'
    /usr/bin/ditto --norsrc --noextattr --noacl --noqtn "$from" "$to" || fail 'The driver copy did not complete.'
    /usr/sbin/chown -R root:wheel "$to"
    /bin/chmod -R go-w "$to"
    bundle_matches "$to" "$sums" || fail 'The staging copy is not identical to the expected driver.'
    verify_signature "$to"
}
remove_known() {
    local target=$1 sums=$2
    [ -e "$target" ] || { [ ! -L "$target" ] || fail 'Unexpected link in the staging path.'; return 0; }
    bundle_matches "$target" "$sums" || fail 'A temporary directory contains an unknown driver; it will not be deleted.'
    /bin/rm -rf "$target"
}
rebuild() {
    local status volume_root=/
    if [ "$RECOVERY" -eq 1 ]; then
        write_phase restorepending
        if [ "$RECOVERY_GROUP_MATCH" -ne 1 ]; then
            printf '\nThe original driver has been restored on the Data volume.\n'
            printf 'Rebuild the kernel collection on the matching System volume before restarting.\n'
            if [ -n "$SYSTEM_ROOT" ]; then
                printf 'A shared APFS group could not be verified. Run this command only after confirming the System volume:\n'
                printf 'kmutil rebuild --volume-root "%s"\n' "$SYSTEM_ROOT"
            else
                printf 'Run RESTORE-VOLUME.command again with --recovery-data and --recovery-system after mounting both volumes.\n'
            fi
            printf 'The state remains restorepending; restoration is not complete or verified.\n'
            return 0
        fi
        volume_root=$SYSTEM_ROOT
    fi
    set +e
    if [ "$RECOVERY" -eq 1 ]; then
        /usr/bin/kmutil rebuild --volume-root "$volume_root" > "$BACKUP/kmutil-last.txt" 2>&1
    else
        /usr/bin/kmutil rebuild > "$BACKUP/kmutil-last.txt" 2>&1
    fi
    status=$?
    set -e
    /bin/cat "$BACKUP/kmutil-last.txt"
    case "$status" in
        0) ;;
        27|28)
            if [ "$RECOVERY" -eq 1 ]; then
                write_phase restorepending
                printf '\nThe original driver has been restored. Rebuilding in Recovery requires approval unavailable here (code %s).\n' "$status"
                printf 'The kernel collection is unconfirmed; keep restorepending and the details in kmutil-last.txt.\n'
            else
                if [ "$MODE" = install ]; then write_phase approvalpending; else write_phase restoreapprovalpending; fi
                printf '\nRebuild awaiting approval (code %s). Open System Settings > Privacy & Security.\n' "$status"
                printf 'Approve the driver if prompted, then run this same command again before restarting.\n'
            fi
            return 0;;
        *) fail "Kernel rebuild did not complete (code $status). The driver is saved; run the same command again to resume.";;
    esac
    if [ "$MODE" = install ]; then write_phase rebootrequired; else write_phase restorerebootrequired; fi
    printf '\nRebuild completed. Restart manually, then run VERIFY-VOLUME.command.\n'
}
verify_source_driver() {
    local bundle=$1 source_backup="$ROOT_DATA$SOURCE_BACKUP_REL" source_state source_hash expected phase
    source_state="$source_backup/state.plist"
    ( BACKUP="$source_backup"; check_owned_backup )
    ordinary_file "$source_state" || fail 'The private microphone-install state is missing.'
    /usr/bin/plutil -lint "$source_state" > /dev/null || fail 'The microphone-install state is invalid.'
    source_hash=$(hash "$source_state")
    [ "$(readkey "$source_state" Format)" = 1 ] || fail 'Unrecognized microphone-install state.'
    [ "$(readkey "$source_state" VolumeUUID)" = "$VOLUME_UUID" ] || fail 'The microphone backup belongs to another Data volume.'
    phase=$(readkey "$source_state" Phase)
    case "$phase" in rebootrequired|verified) ;; *) fail 'The microphone correction is not in an installed state.';; esac
    expected=$(readkey "$source_state" PayloadManifestHash) || fail 'The microphone payload reference is missing.'
    case "$expected" in ''|*[!0-9a-f]*) fail 'Invalid microphone payload reference.';; esac
    [ "${#expected}" -eq 64 ] || fail 'Incomplete microphone payload reference.'
    validate_shape "$bundle"
    check_owned_directory "$bundle"
    local entry entry_mode
    while IFS= read -r entry; do
        [ "$(/usr/bin/stat -f %u "$entry")" = 0 ] || fail 'A source driver entry is not owned by root.'
        entry_mode=$(/usr/bin/stat -f %Lp "$entry")
        [ "$((8#$entry_mode & 022))" -eq 0 ] || fail 'A source driver entry is writable by other users.'
    done < <(/usr/bin/find "$bundle" -print)
    [ "$(readkey "$bundle/Contents/Info.plist" CFBundleIdentifier)" = org.voodoo.driver.VoodooHDA ] || fail 'Unexpected source driver identifier.'
    [ "$(readkey "$bundle/Contents/Info.plist" CFBundleVersion)" = 3.6.9 ] || fail 'The installed driver is not the S540 3.6.9 microphone variant.'
    [ "$(readkey "$bundle/Contents/Info.plist" "$KEY")" = true ] || fail 'The existing PCM volume routing is not enabled.'
    [ "$(readkey "$bundle/Contents/Info.plist" IOKitPersonalities.VoodooHDA.S540InputGainFix)" = true ] || fail 'The source microphone correction is not enabled.'
    save_manifest "$bundle" "$TEMP/source-SHA256SUMS"
    [ "$(hash "$TEMP/source-SHA256SUMS")" = "$expected" ] || fail 'The installed driver does not match the private microphone payload reference.'
    verify_macho_header "$bundle/Contents/MacOS/VoodooHDA" || fail 'The source is not an Intel kernel bundle.'
    verify_signature "$bundle"
    bundle_matches "$bundle" "$TEMP/source-SHA256SUMS" || fail 'The source driver changed during verification.'
    [ "$(hash "$source_state")" = "$source_hash" ] || fail 'The microphone state changed during verification.'
}
source_runtime_ok() {
    /usr/bin/kmutil showloaded > "$TEMP/source-loaded.txt"
    /usr/bin/grep -Eq 'org\.voodoo\.driver\.VoodooHDA[[:space:]]+\(3\.6\.9\)' "$TEMP/source-loaded.txt" || fail 'VoodooHDA 3.6.9 is not loaded; use the working desktop after restarting.'
    /usr/sbin/ioreg -r -c VoodooHDADevice -l -w 0 > "$TEMP/source-ioreg.txt"
    /usr/bin/grep -Eq '"S540InputGainFixActive" = (Yes|true)' "$TEMP/source-ioreg.txt" || fail 'The current microphone correction is not active for this codec.'
}

check_kernel_symbols() {
    if ! /usr/bin/kmutil libraries --bundle-path "$PAYLOAD" --xml > "$TEMP/kernel-libraries.xml" 2> "$TEMP/kernel-libraries-errors.txt"; then
        /bin/cat "$TEMP/kernel-libraries-errors.txt" >&2
        /bin/cat "$TEMP/kernel-libraries.xml" >&2
        fail 'The new driver cannot resolve every symbol in the current Tahoe kernel. The working driver will not be replaced.'
    fi
}

install_driver() {
    local path final_backup prepare_backup
    runtime_sip
    if [ ! -e "$BACKUP" ]; then
        check_kernel_symbols
        verify_source_driver "$DRIVER"
        source_runtime_ok
        for path in "$STAGE" "$PREVIOUS"; do [ ! -e "$path" ] && [ ! -L "$path" ] || fail 'An unrecognized incomplete driver test already exists.'; done
        final_backup=$BACKUP
        prepare_backup="$ROOT_DATA/Library/Application Support/.S540-volume-fine-prepare"
        [ ! -e "$prepare_backup" ] && [ ! -L "$prepare_backup" ] || fail 'An interrupted backup preparation already exists. The current driver was not replaced; keep the directory for inspection.'
        backup_paths "$prepare_backup"
        /bin/mkdir "$BACKUP"
        /bin/chmod 700 "$BACKUP"
        /bin/chmod -RN "$BACKUP"
        save_manifest "$DRIVER" "$ORIGINAL_SUMS"
        copy_driver "$DRIVER" "$ORIGINAL" "$ORIGINAL_SUMS"
        verify_source_driver "$ORIGINAL"
        /usr/bin/plutil -create xml1 "$STATE"
        /usr/bin/plutil -insert Format -integer 1 "$STATE"
        /usr/bin/plutil -insert Phase -string staging "$STATE"
        /usr/bin/plutil -insert VolumeUUID -string "$VOLUME_UUID" "$STATE"
        /usr/bin/plutil -insert OriginalManifestHash -string "$(hash "$ORIGINAL_SUMS")" "$STATE"
        /usr/bin/plutil -insert PayloadManifestHash -string "$PAYLOAD_MANIFEST_SHA" "$STATE"
        /usr/bin/plutil -insert OriginalBootSessionUUID -string "$BOOT_UUID" "$STATE"
        /usr/bin/plutil -insert RuntimeSipData -string 03000000 "$STATE"
        /bin/chmod 600 "$STATE"
        /usr/bin/plutil -lint "$STATE" > /dev/null
        bundle_matches "$ORIGINAL" "$ORIGINAL_SUMS" || fail 'The original copy changed during preparation.'
        /bin/mv "$BACKUP" "$final_backup"
        backup_paths "$final_backup"
    fi
    load_state
    case "$PHASE" in
        staging|swapping)
            if [ -e "$DRIVER" ] && bundle_matches "$DRIVER" "$PAYLOAD_SUMS"; then
                write_phase swapped
            else
                if [ -e "$DRIVER" ]; then
                    bundle_matches "$DRIVER" "$ORIGINAL_SUMS" || fail 'The installed driver does not match the original.'
                    [ ! -e "$PREVIOUS" ] && [ ! -L "$PREVIOUS" ] || fail 'The previous temporary copy already exists.'
                else
                    bundle_matches "$PREVIOUS" "$ORIGINAL_SUMS" || fail 'The original driver is not in the expected temporary path.'
                fi
                if [ -e "$STAGE" ]; then bundle_matches "$STAGE" "$PAYLOAD_SUMS" || fail 'Unrecognized staging content.'; else copy_driver "$PAYLOAD" "$STAGE" "$PAYLOAD_SUMS"; fi
                write_phase swapping
                if [ -e "$DRIVER" ]; then /bin/mv "$DRIVER" "$PREVIOUS"; fi
                /bin/mv "$STAGE" "$DRIVER"
                bundle_matches "$DRIVER" "$PAYLOAD_SUMS" || fail 'The replacement driver does not match the payload.'
                write_phase swapped
            fi
            ;;
        swapped|rebuildpending|approvalpending) bundle_matches "$DRIVER" "$PAYLOAD_SUMS" || fail 'The test driver has changed.';;
        rebootrequired|verified) printf 'The test is already installed. Restart if necessary and run VERIFY-VOLUME.command.\n'; return 0;;
        *) fail 'The test is being restored or has already been reversed. It will not be reinstalled automatically.';;
    esac
    remove_known "$PREVIOUS" "$ORIGINAL_SUMS"
    write_phase rebuildpending
    rebuild
    printf 'To reverse the test, use only RESTORE-VOLUME.command from this package.\n'
}
restore_driver() {
    load_state
    case "$PHASE" in restored|restorerebootrequired) printf 'The original driver is already restored. Restart if necessary and verify.\n'; return 0;; esac
    if [ -e "$DRIVER" ] && bundle_matches "$DRIVER" "$ORIGINAL_SUMS"; then
        :
    else
        if [ -e "$DRIVER" ]; then bundle_matches "$DRIVER" "$PAYLOAD_SUMS" || fail 'The installed driver is unknown; restoration has stopped.'; fi
        remove_known "$STAGE" "$PAYLOAD_SUMS"
        remove_known "$PREVIOUS" "$ORIGINAL_SUMS"
        copy_driver "$ORIGINAL" "$PREVIOUS" "$ORIGINAL_SUMS"
        write_phase restoring
        if [ -e "$DRIVER" ]; then /bin/mv "$DRIVER" "$STAGE"; fi
        /bin/mv "$PREVIOUS" "$DRIVER"
    fi
    bundle_matches "$DRIVER" "$ORIGINAL_SUMS" || fail 'The original driver was not restored exactly.'
    verify_signature "$DRIVER"
    remove_known "$STAGE" "$PAYLOAD_SUMS"
    remove_known "$PREVIOUS" "$ORIGINAL_SUMS"
    write_phase restoreswapped
    rebuild
}
verify_driver() {
    local target_version expected_sums
    load_state
    runtime_sip
    case "$PHASE" in
        rebootrequired|verified) target_version=$TEST_VERSION; expected_sums=$PAYLOAD_SUMS;;
        restorerebootrequired|restored) target_version=3.6.9; expected_sums=$ORIGINAL_SUMS;;
        *) fail 'Replacement or rebuilding is incomplete. Run INSTALL-VOLUME.command or RESTORE-VOLUME.command again according to the operation started.';;
    esac
    bundle_matches "$DRIVER" "$expected_sums" || fail 'The installed driver does not match the expected version.'
    [ "$BOOT_UUID" != "$(readkey "$STATE" OriginalBootSessionUUID)" ] || fail 'Restart after replacing the driver.'
    /usr/bin/kmutil showloaded > "$TEMP/loaded.txt"
    /usr/bin/grep -Eq "org\\.voodoo\\.driver\\.VoodooHDA[[:space:]]+\\(${target_version//./\\.}\\)" "$TEMP/loaded.txt" || fail 'The expected driver version is not loaded.'
    if [ "$target_version" = "$TEST_VERSION" ]; then
        /usr/sbin/ioreg -r -c VoodooHDADevice -l -w 0 > "$TEMP/driver-ioreg.txt"
        /usr/bin/grep -Eq '"S540InputGainFixActive" = (Yes|true)' "$TEMP/driver-ioreg.txt" || fail 'The driver is loaded, but the input correction is not active for this codec.'
        /usr/bin/grep -Eq '"S540OutputRangeFixActive" = (Yes|true)' "$TEMP/driver-ioreg.txt" || fail 'The driver is loaded, but the output graph did not enable the range correction.'
        # This device's subtree excludes Bluetooth/USB audio control services.
        /bin/cp "$TEMP/driver-ioreg.txt" "$TEMP/controls.txt"
        /usr/bin/awk '
            /\+-o IOAudioLevelControl[[:space:]]/ { usage=""; low=""; high="" }
            /"IOAudioLevelControlMinDB" =/ {low=$NF}
            /"IOAudioLevelControlMaxDB" =/ {high=$NF}
            /"IOAudioControlUsage" =/ {usage=$NF}
            /\}/ {if(usage=="1768845428") {count++; if(low!="-1130496" && low!="18446744073708421120") bad=1; if(high!="1966080") bad=1; usage=""}}
            END {exit (count!=2 || bad)}' "$TEMP/controls.txt" || fail 'The two input controls do not expose the expected range (-17.25/+30 dB).'
        /usr/bin/awk '
            /\+-o IOAudioLevelControl[[:space:]]/ { usage=""; low=""; high="" }
            /"IOAudioLevelControlMinDB" =/ {low=$NF}
            /"IOAudioLevelControlMaxDB" =/ {high=$NF}
            /"IOAudioControlUsage" =/ {usage=$NF}
            /\}/ {if(usage=="1869968496") {count++; if(low!="-4276224" && low!="18446744073705275392") bad=1; if(high!="0") bad=1; usage=""}}
            END {exit (count!=2 || bad)}' "$TEMP/controls.txt" || fail 'The two output controls do not expose the expected range (-65.25/0 dB).'
        write_phase verified
        printf 'Driver 3.6.10 loaded; microphone correction and full output range active; input/output ranges verified.\n'
        printf 'Start playback quietly and check the first volume steps, mute/unmute and headphones. Keep the working microphone input setting.\n'
    else
        write_phase restored
        printf 'Restoration verified: the exact previous VoodooHDA 3.6.9 microphone driver is loaded.\n'
    fi
}

case "$MODE" in install|restore|verify|payload-check) ;; *) fail 'Usage: install | restore [--recovery-data PATH --recovery-system PATH] | verify';; esac
shift
[ "$(/usr/bin/uname -s)" = Darwin ] && [ "$(/usr/bin/uname -m)" = x86_64 ] || fail 'Intel macOS is required.'
PACKAGE=$(cd -P "$(/usr/bin/dirname "${BASH_SOURCE[0]}")/.." && pwd)
safe_path "$PACKAGE"
PAYLOAD="$PACKAGE/assets/volume/VoodooHDA.kext"
PAYLOAD_SUMS="$PACKAGE/assets/volume/SHA256SUMS"
if [ "$MODE" = payload-check ]; then
    [ "$#" -eq 0 ] || fail 'The payload check takes no arguments.'
    TEMP=$(/usr/bin/mktemp -d /tmp/s540-volume-payload.XXXXXX)
    verify_payload
    printf 'Intel 3.6.10 payload: manifest, three files, signature and kernel format verified.\n'
    exit 0
fi
case "$(/usr/bin/uname -r)" in 25.*) ;; *) fail 'This package targets macOS Tahoe.';; esac
if [ "$#" -gt 0 ]; then
    [ "$MODE" = restore ] || fail 'An explicit Data volume is allowed only for restoration in Recovery.'
    [ "$(/usr/bin/id -u)" -eq 0 ] || fail 'Use the root Terminal in Recovery.'
    [ ! -d /System/Volumes/Data ] || fail 'On the desktop, run RESTORE-VOLUME.command without arguments.'
    if [ "$#" -eq 1 ]; then
        ROOT_DATA=${1%/}
    else
        while [ "$#" -gt 0 ]; do
            [ "$#" -ge 2 ] || fail 'A Recovery volume path is missing.'
            case "$1" in
                --recovery-data) [ -z "$ROOT_DATA" ] || fail 'The Data volume was specified more than once.'; ROOT_DATA=${2%/};;
                --recovery-system) [ -z "$SYSTEM_ROOT" ] || fail 'The System volume was specified more than once.'; SYSTEM_ROOT=${2%/};;
                *) fail 'Unrecognized Recovery argument.';;
            esac
            shift 2
        done
    fi
    [ -n "$ROOT_DATA" ] || fail 'Specify the Data volume with --recovery-data.'
    RECOVERY=1
    safe_path "$ROOT_DATA"
    [ -d "$ROOT_DATA/Users" ] && [ -d "$ROOT_DATA/private/var" ] && [ -d "$ROOT_DATA/Library/Extensions" ] || fail 'The path does not contain the expected macOS Data volume directories.'
else
    [ -d /System/Volumes/Data ] && [ -d /Users ] || fail 'In Recovery, specify the Data volume explicitly for restoration.'
    ROOT_DATA='/System/Volumes/Data'
fi
if [ "$(/usr/bin/id -u)" -ne 0 ]; then
    printf 'The administrator password is required to copy the driver and rebuild the kernel collection.\n'
    exec /usr/bin/sudo /bin/bash "$PACKAGE/tools/volume_driver_test.sh" "$MODE"
fi
for utility in /usr/bin/awk /usr/bin/plutil /usr/bin/cmp /usr/bin/find /usr/bin/stat /usr/bin/ditto /usr/bin/kmutil /usr/sbin/diskutil; do
    [ -x "$utility" ] || fail "Required utility missing: $utility. No driver will be replaced."
done
if [ "$RECOVERY" -ne 1 ]; then
    for utility in /usr/bin/codesign /usr/bin/od; do
        [ -x "$utility" ] || fail "Required utility missing: $utility. No driver will be replaced."
    done
fi
TEMP=$(/usr/bin/mktemp -d /tmp/s540-volume-driver.XXXXXX) || fail 'Cannot create the temporary directory.'
if [ "$RECOVERY" -eq 1 ]; then DRIVER_PARENT="$ROOT_DATA/Library/Extensions"; else DRIVER_PARENT='/Library/Extensions'; fi
DRIVER="$DRIVER_PARENT/VoodooHDA.kext"
STAGE="$DRIVER_PARENT/.VoodooHDA-s540-volume-stage.kext"
PREVIOUS="$DRIVER_PARENT/.VoodooHDA-s540-volume-previous.kext"
backup_paths "$ROOT_DATA$BACKUP_REL"
check_owned_directory "$DRIVER_PARENT"
check_owned_directory "$ROOT_DATA/Library/Application Support"
volume_uuid
if [ "$RECOVERY" -eq 1 ]; then recovery_system; fi
BOOT_UUID=$(/usr/sbin/sysctl -n kern.bootsessionuuid) || fail 'Cannot identify this boot session.'
verify_payload
case "$MODE" in install) install_driver;; restore) restore_driver;; verify) verify_driver;; esac
