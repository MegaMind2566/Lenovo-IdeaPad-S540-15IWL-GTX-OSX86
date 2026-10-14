#!/bin/bash
# Copy the current private OpenCore installation to the running external SSD.
# macOS Bash 3.2; no formatting, configuration edits or NVRAM writes.
set -u
set -o pipefail
export LC_ALL=C
export LANG=C
umask 077

fail() { printf 'SSD boot setup stopped: %s\n' "$*" >&2; exit 1; }
plist() { /usr/libexec/PlistBuddy -c "Print :$2" "$1" 2>/dev/null; }
disk_id() { [[ "$1" =~ ^disk[0-9]+$ ]]; }
partition_id() { disk_id "$1" && [[ "$2" =~ ^${1}s[0-9]+$ ]]; }
uuid() { [[ "$1" =~ ^[A-Fa-f0-9]{8}-[A-Fa-f0-9]{4}-[A-Fa-f0-9]{4}-[A-Fa-f0-9]{4}-[A-Fa-f0-9]{12}$ ]]; }
size_between() { [[ "$1" =~ ^[0-9]{1,12}$ ]] && (( 10#$1 >= $2 && 10#$1 <= $3 )); }
as_admin() { /usr/bin/sudo -n "$@"; }
copy_tree() { /usr/bin/ditto --noextattr --norsrc "$1" "$2"; }

tree_manifest() {
    local directory="$1" output="$2" paths="$2.paths" special="$2.special"
    [[ -d "$directory" && ! -L "$directory" ]] || return 1
    (cd -P -- "$directory" && /usr/bin/find . ! -type d ! -type f -print) > "$special" || return 1
    [[ ! -s "$special" ]] || return 1
    (cd -P -- "$directory" && /usr/bin/find . -name '*
*' -print) > "$special" || return 1
    [[ ! -s "$special" ]] || return 1
    (cd -P -- "$directory" && /usr/bin/find . \( -type f \( -name .DS_Store -o -name '._*' \) \) -prune -o -print) > "$paths" || return 1
    # EFI paths must be portable ASCII. Reject aliases on case-insensitive FAT.
    /usr/bin/awk '/[^ -~]|[\\:*?"<>|]/ { exit 1 } { print tolower($0) }' "$paths" |
        /usr/bin/sort | /usr/bin/uniq -d > "$special" || return 1
    [[ ! -s "$special" ]] || return 1
    (
        cd -P -- "$directory" || exit 1
        /usr/bin/find . -type d -print | /usr/bin/sort | /usr/bin/awk '{print "D\t" $0}' || exit 1
        /usr/bin/find . -type f ! -name .DS_Store ! -name '._*' -exec /usr/bin/shasum -a 256 {} + |
            /usr/bin/sort | /usr/bin/awk '{print "F\t" $0}'
    ) > "$output"
}

same_tree() {
    tree_manifest "$1" "$work/compare-a.txt" && tree_manifest "$2" "$work/compare-b.txt" &&
        /usr/bin/cmp -s "$work/compare-a.txt" "$work/compare-b.txt"
}

preserved_manifest() {
    /usr/bin/awk '
      { line=tolower($0) }
      line ~ /^d\t[.]\/(boot|oc)(\/|$)/ {next}
      line ~ /^f\t[^ ]+  [.]\/(boot|oc)\// {next}
      {print}
    ' "$1" > "$2"
}

valid_source() {
    local directory="$1"
    [[ -d "$directory/BOOT" && ! -L "$directory/BOOT" && -d "$directory/OC" && ! -L "$directory/OC" ]] || return 1
    [[ -f "$directory/BOOT/BOOTx64.efi" && -s "$directory/BOOT/BOOTx64.efi" &&
       -f "$directory/OC/OpenCore.efi" && -s "$directory/OC/OpenCore.efi" &&
       -f "$directory/OC/config.plist" && -s "$directory/OC/config.plist" ]] || return 1
    /usr/bin/plutil -lint -- "$directory/OC/config.plist" >/dev/null 2>&1
}

external_index() {
    local wanted="$1" index=0 found='' item
    while (( index < 64 )); do
        item=$(plist "$work/external.plist" "AllDisksAndPartitions:$index:DeviceIdentifier") || break
        if [[ "$item" == "$wanted" ]]; then [[ -z "$found" ]] || return 1; found="$index"; fi
        index=$((index+1))
    done
    [[ -n "$found" && $index -lt 64 ]] || return 1
    printf '%s\n' "$found"
}

check_whole() {
    local identifier="$1" low="$2" high="$3" file="$work/whole-$1.plist" bytes alternate
    disk_id "$identifier" || return 1
    /usr/sbin/diskutil info -plist "$identifier" > "$file" || return 1
    [[ "$(plist "$file" DeviceIdentifier)" == "$identifier" &&
       "$(plist "$file" Internal)" == false && "$(plist "$file" WholeDisk)" == true &&
       "$(plist "$file" Content)" == GUID_partition_scheme &&
       "$(plist "$file" VirtualOrPhysical)" != Virtual ]] || return 1
    bytes=$(plist "$file" Size) || return 1
    alternate=$(plist "$file" TotalSize) || alternate="$bytes"
    [[ "$alternate" == "$bytes" ]] && size_between "$bytes" "$low" "$high"
}

target_identity() {
    local file="$work/target-now.plist" mounted_file="$work/mount-now.plist"
    /usr/sbin/diskutil info -plist "$target_partition" > "$file" || return 1
    [[ "$(plist "$file" DeviceIdentifier)" == "$target_partition" &&
       "$(plist "$file" ParentWholeDisk)" == "$target_whole" &&
       "$(plist "$file" DiskUUID)" == "$target_uuid" &&
       "$(plist "$file" Internal)" == false && "$(plist "$file" Content)" == EFI &&
       "$(plist "$file" FilesystemType)" == msdos &&
       "$(plist "$file" Mounted)" == true && "$(plist "$file" MountPoint)" == "$target_mount" &&
       "$(plist "$file" WritableMedia)" == true && "$(plist "$file" WritableVolume)" == true ]] || return 1
    [[ -d "$target_mount" && ! -L "$target_mount" && "$target_mount" == /Volumes/* &&
       "$(cd -P -- "$target_mount" && pwd)" == "$target_mount" ]] || return 1
    /usr/sbin/diskutil info -plist "$target_mount" > "$mounted_file" || return 1
    [[ "$(plist "$mounted_file" DeviceIdentifier)" == "$target_partition" &&
       "$(plist "$mounted_file" DiskUUID)" == "$target_uuid" ]] || return 1
    check_whole "$target_whole" 250000000000 251000000000
}

rollback() {
    [[ "$committed" == 0 ]] || return 0
    [[ "$transaction_started" == 1 ]] || return 0
    # Reconcile actual rename results even if a signal preceded flag assignment.
    if [[ "$had_target" == 1 ]]; then
        [[ -d "$previous_tree" && ! -L "$previous_tree" ]] || return 0
        old_moved=1
    else
        [[ ! -d "$stage" && -d "$target_mount/EFI" ]] || return 0
        promoted=1
    fi
    if [[ "$old_moved" == 1 || "$promoted" == 1 ]]; then
        target_identity || { printf 'Automatic rollback could not verify the SSD. Boot from the HDD and keep the Desktop backup.\n' >&2; return 1; }
        # Keep a failed promoted tree rather than delete an unverified tree.
        if [[ -e "$target_mount/EFI" || -L "$target_mount/EFI" ]]; then
            as_admin /bin/mv "$target_mount/EFI" "$failed_tree" || return 1
        fi
        if [[ "$old_moved" == 1 ]]; then
            as_admin /bin/mv "$previous_tree" "$target_mount/EFI" || return 1
        fi
        printf 'The previous SSD boot state was restored. The HDD is unchanged.\n' >&2
    fi
}

promote_stage() {
    target_identity || return 1
    if [[ "$had_target" == 1 ]]; then
        same_tree "$target_mount/EFI" "$backup/previous-target-EFI" || return 1
        transaction_started=1
        as_admin /bin/mv "$target_mount/EFI" "$previous_tree" || return 1
        old_moved=1
    else
        [[ ! -e "$target_mount/EFI" && ! -L "$target_mount/EFI" ]] || return 1
        transaction_started=1
    fi
    as_admin /bin/mv "$stage" "$target_mount/EFI" || return 1
    promoted=1
    tree_manifest "$target_mount/EFI" "$work/installed.txt" || return 1
    /usr/bin/cmp -s "$work/staged.txt" "$work/installed.txt" || return 1
    /bin/sync || return 1
    committed=1
}

if [[ "${1-}" == --self-test && $# == 1 ]]; then
    disk_id disk12 && ! disk_id disk12s1 && partition_id disk12 disk12s1 && ! partition_id disk1 disk12s1 || exit 1
    uuid 12345678-ABCD-abcd-1234-1234567890AB && ! uuid '../bad' || exit 1
    size_between 250059350016 250000000000 251000000000 && ! size_between 240057409536 250000000000 251000000000 || exit 1
    work=$(/usr/bin/mktemp -d "${TMPDIR:-/tmp}/ssd-boot-selftest-XXXXXX") || exit 1
    trap '/bin/rm -rf -- "$work"' EXIT
    /bin/mkdir -p "$work/a/BOOT" "$work/a/OC" "$work/a/APPLE" "$work/b" || exit 1
    printf 'boot\n' > "$work/a/BOOT/test.efi"
    printf 'private\n' > "$work/a/OC/config.plist"
    printf 'preserved\n' > "$work/a/APPLE/file"
    /bin/cp -R "$work/a/." "$work/b/" || exit 1
    same_tree "$work/a" "$work/b" || exit 1
    printf 'changed\n' > "$work/b/BOOT/test.efi"
    if same_tree "$work/a" "$work/b"; then exit 1; fi
    tree_manifest "$work/a" "$work/a.txt" && tree_manifest "$work/b" "$work/b.txt" || exit 1
    preserved_manifest "$work/a.txt" "$work/pa.txt"
    preserved_manifest "$work/b.txt" "$work/pb.txt"
    /usr/bin/cmp -s "$work/pa.txt" "$work/pb.txt" || exit 1
    /bin/ln -s "$work/a" "$work/b/alias" || exit 1
    if tree_manifest "$work/b" "$work/rejected.txt"; then exit 1; fi
    printf 'SSD boot guard fixtures passed.\n'
    exit 0
fi

(( $# == 0 )) || fail 'unexpected arguments.'
[[ "$(/usr/bin/uname -s)" == Darwin && "$(/usr/bin/uname -m)" == x86_64 && $EUID != 0 ]] || fail 'run as your normal user on the Intel macOS laptop.'
package=$(cd -P -- "$(dirname -- "$0")" && pwd) || exit 1
[[ -r "$package/SHA256SUMS" ]] || fail 'package checksums are missing.'
(cd "$package" && /usr/bin/shasum -a 256 -c SHA256SUMS >/dev/null) || fail 'package verification failed.'
[[ -d "$HOME/Desktop" && ! -L "$HOME/Desktop" ]] || fail 'the Desktop folder is unavailable.'
source_volume='/Volumes/240 GB'
source_efi="$source_volume/EFI"
[[ -d "$source_volume" && ! -L "$source_volume" ]] || fail 'the current 240 GB boot volume is not mounted.'
work=$(/usr/bin/mktemp -d "${TMPDIR:-/tmp}/S540-SSD-BOOT-XXXXXX") || exit 1
stage='' previous_tree='' failed_tree='' target_mount='' target_partition='' target_whole='' target_uuid='' backup=''
old_moved=0 promoted=0 committed=0 had_target=0 mounted_here=0 transaction_started=0
cleanup() {
    local result=$?
    trap - EXIT INT TERM HUP
    if [[ "$committed" == 0 ]]; then rollback || :; fi
    if [[ -n "$stage" && -d "$stage" && ! -L "$stage" ]] && target_identity; then as_admin /bin/rm -rf -- "$stage" || :; fi
    if [[ "$mounted_here" == 1 ]] && target_identity; then as_admin /usr/sbin/diskutil unmount "$target_partition" >/dev/null 2>&1 || :; fi
    /bin/rm -rf -- "$work"
    exit "$result"
}
trap cleanup EXIT
trap 'printf "\nSSD boot setup interrupted.\n" >&2; exit 130' INT TERM HUP

/usr/sbin/diskutil list -plist external physical > "$work/external.plist" || fail 'external disk discovery failed.'
/usr/sbin/diskutil info -plist "$source_volume" > "$work/source.plist" || fail 'the current boot volume cannot be identified.'
source_partition=$(plist "$work/source.plist" DeviceIdentifier) || exit 1
source_whole=$(plist "$work/source.plist" ParentWholeDisk) || exit 1
partition_id "$source_whole" "$source_partition" && check_whole "$source_whole" 240000000000 241000000000 || fail 'the source is not the expected external 240 GB GPT disk.'
[[ "$(plist "$work/source.plist" MountPoint)" == "$source_volume" && "$(plist "$work/source.plist" VolumeName)" == '240 GB' ]] || fail 'the source mount does not match the working boot volume.'
source_index=$(external_index "$source_whole") || fail 'the source is not a unique external physical disk.'
prefix="AllDisksAndPartitions:$source_index:Partitions"
[[ "$(plist "$work/external.plist" "$prefix:0:DeviceIdentifier")" == "$source_partition" &&
   "$(plist "$work/external.plist" "$prefix:0:Content")" == 'Microsoft Basic Data' ]] || fail 'the source partition layout changed.'
if plist "$work/external.plist" "$prefix:1:DeviceIdentifier" >/dev/null; then fail 'the source has an unexpected extra partition.'; fi

/usr/sbin/diskutil info -plist / > "$work/root.plist" || fail 'the running macOS volume cannot be identified.'
container=$(plist "$work/root.plist" APFSContainerReference) || fail 'the running system has no APFS container reference.'
disk_id "$container" || fail 'the APFS container reference is invalid.'
/usr/sbin/diskutil apfs list -plist "$container" > "$work/apfs.plist" || fail 'the running APFS container cannot be inspected.'
[[ "$(plist "$work/apfs.plist" Containers:0:ContainerReference)" == "$container" ]] || fail 'the running APFS container changed.'
if plist "$work/apfs.plist" Containers:1:ContainerReference >/dev/null; then fail 'the APFS lookup is ambiguous.'; fi
store=$(plist "$work/apfs.plist" Containers:0:PhysicalStores:0:DeviceIdentifier) || fail 'the APFS physical store is unavailable.'
if plist "$work/apfs.plist" Containers:0:PhysicalStores:1:DeviceIdentifier >/dev/null; then fail 'the running APFS container has multiple physical stores.'; fi
/usr/sbin/diskutil info -plist "$store" > "$work/store.plist" || fail 'the running physical store cannot be inspected.'
target_whole=$(plist "$work/store.plist" ParentWholeDisk) || exit 1
partition_id "$target_whole" "$store" && check_whole "$target_whole" 250000000000 251000000000 || fail 'the running system is not on the expected external 250 GB GPT SSD.'
[[ "$target_whole" != "$source_whole" && "$(plist "$work/store.plist" APFSContainerReference)" == "$container" ]] || fail 'the source and target mapping is invalid.'
target_index=$(external_index "$target_whole") || fail 'the SSD is not a unique external physical disk.'
prefix="AllDisksAndPartitions:$target_index:Partitions"
target_partition=$(plist "$work/external.plist" "$prefix:0:DeviceIdentifier") || exit 1
partition_id "$target_whole" "$target_partition" || fail 'the EFI partition identifier is invalid.'
[[ "$(plist "$work/external.plist" "$prefix:0:Content")" == EFI &&
   "$(plist "$work/external.plist" "$prefix:1:Content")" == Apple_APFS &&
   "$(plist "$work/external.plist" "$prefix:1:DeviceIdentifier")" == "$store" ]] || fail 'the SSD does not match the observed EFI + APFS layout.'
size_between "$(plist "$work/external.plist" "$prefix:0:Size")" 200000000 220000000 || fail 'the SSD EFI partition has an unexpected size.'
if plist "$work/external.plist" "$prefix:2:DeviceIdentifier" >/dev/null; then fail 'the SSD has an unexpected extra partition.'; fi
/usr/sbin/diskutil info -plist "$target_partition" > "$work/target-initial.plist" || exit 1
target_uuid=$(plist "$work/target-initial.plist" DiskUUID) || exit 1
uuid "$target_uuid" || fail 'the SSD EFI partition has no valid stable UUID.'
valid_source "$source_efi" && tree_manifest "$source_efi" "$work/source-initial.txt" || fail 'the current EFI is incomplete, invalid or contains unsafe paths.'

printf 'Source: current EFI on the external 240 GB boot disk (%s).\n' "$source_partition"
printf 'Target: EFI on the running external 250 GB macOS SSD (%s).\n' "$target_partition"
printf 'A private backup will be kept on the Desktop. No disk will be formatted.\n'
/usr/bin/sudo -v || exit 1
if [[ "$(plist "$work/target-initial.plist" Mounted)" != true ]]; then
    as_admin /usr/sbin/diskutil mount "$target_partition" >/dev/null || fail 'the SSD EFI partition could not be mounted.'
    mounted_here=1
fi
/usr/sbin/diskutil info -plist "$target_partition" > "$work/target-mounted.plist" || exit 1
target_mount=$(plist "$work/target-mounted.plist" MountPoint) || fail 'the mounted SSD EFI has no mount point.'
target_identity || fail 'the SSD identity or writable mount changed.'
backup=$(/usr/bin/mktemp -d "$HOME/Desktop/S540-SSD-BOOT-BACKUP-XXXXXX") || fail 'the private backup folder could not be created.'
copy_tree "$source_efi" "$backup/source-EFI" && same_tree "$source_efi" "$backup/source-EFI" || fail 'the source backup could not be verified.'
if [[ -e "$target_mount/EFI" || -L "$target_mount/EFI" ]]; then
    tree_manifest "$target_mount/EFI" "$work/target-before.txt" || fail 'the existing SSD EFI contains unsafe paths.'
    had_target=1
    copy_tree "$target_mount/EFI" "$backup/previous-target-EFI" && same_tree "$target_mount/EFI" "$backup/previous-target-EFI" || fail 'the previous SSD EFI backup could not be verified.'
else
    printf 'The SSD had no EFI directory before installation.\n' > "$backup/NO-PREVIOUS-EFI.txt"
fi
printf 'Private backup of the working source EFI and previous SSD EFI.\nOnly BOOT and OC are replaced on the SSD; other EFI folders are preserved.\nThe original 240 GB boot disk is unchanged.\n' > "$backup/README.txt"
target_identity || fail 'the SSD changed before staging.'
stage=$(as_admin /usr/bin/mktemp -d "$target_mount/.S540-SSD-STAGE-XXXXXX") || fail 'the SSD has no room for a staging directory.'
as_admin /bin/chmod 755 "$stage" || fail 'the staging directory is not readable for verification.'
previous_tree="$target_mount/.S540-SSD-PREVIOUS-${stage##*-}"
failed_tree="$target_mount/.S540-SSD-FAILED-${stage##*-}"
[[ ! -e "$previous_tree" && ! -L "$previous_tree" && ! -e "$failed_tree" && ! -L "$failed_tree" ]] || fail 'a transaction path is already present.'
if [[ "$had_target" == 1 ]]; then as_admin /usr/bin/ditto --noextattr --norsrc "$backup/previous-target-EFI" "$stage" || fail 'the preserved SSD EFI could not be staged.'; fi
as_admin /bin/rm -rf -- "$stage/BOOT" "$stage/OC" || fail 'the staging directory could not be prepared.'
as_admin /usr/bin/ditto --noextattr --norsrc "$backup/source-EFI/BOOT" "$stage/BOOT" &&
    as_admin /usr/bin/ditto --noextattr --norsrc "$backup/source-EFI/OC" "$stage/OC" || fail 'the SSD has insufficient space or the working EFI could not be copied.'
same_tree "$backup/source-EFI/BOOT" "$stage/BOOT" && same_tree "$backup/source-EFI/OC" "$stage/OC" || fail 'the staged boot files do not match the source.'
tree_manifest "$stage" "$work/staged.txt" || fail 'the staged EFI cannot be verified.'
if [[ "$had_target" == 1 ]]; then
    preserved_manifest "$work/target-before.txt" "$work/preserved-before.txt"
    preserved_manifest "$work/staged.txt" "$work/preserved-after.txt"
    /usr/bin/cmp -s "$work/preserved-before.txt" "$work/preserved-after.txt" || fail 'unrelated SSD EFI files would change.'
fi
same_tree "$source_efi" "$backup/source-EFI" || fail 'the working source EFI changed during the copy.'
promote_stage || fail 'the final SSD copy failed verification; automatic rollback will run.'
if [[ "$old_moved" == 1 ]]; then
    target_identity && as_admin /bin/rm -rf -- "$previous_tree" || printf 'The verified SSD copy is ready; an extra previous tree remains on its EFI partition.\n' >&2
fi
printf '\nSSD boot files verified.\nPrivate backup: %s\n' "$backup"
printf 'Shut down. Disconnect the 240 GB boot HDD, keep the Samsung connected, and select its UEFI entry in the firmware boot menu.\n'
printf 'If it does not boot, reconnect the HDD and start from its existing OpenCore. Keep the backup folder.\n'
