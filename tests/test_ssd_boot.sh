#!/bin/bash
# Hardware-free guard and transaction fixtures; native schema reads are read-only.
set -eu
set -o pipefail
export LC_ALL=C
umask 077
source_file="${1:-packages/ssd-boot/INSTALL-SSD-BOOT.command}"
test_dir=$(cd -P -- "$(dirname -- "$0")" && pwd)
/bin/bash -n "$source_file"
[[ "$(/bin/bash "$source_file" --self-test)" == 'SSD boot guard fixtures passed.' ]]
test_root=$(/usr/bin/mktemp -d "${TMPDIR:-/tmp}/ssd-boot-tests-XXXXXX")
trap '/bin/rm -rf -- "$test_root"' EXIT
# Load function definitions only. Production paths and the entrypoint stay intact.
/usr/bin/awk '/^if \[\[ "\$\{1-\}" == --self-test/ {exit} {print}' "$source_file" > "$test_root/functions.sh"
. "$test_root/functions.sh"

for action in success rename-failure verify-failure stale-target no-previous no-previous-failure old-rename-signal new-rename-signal; do
    work="$test_root/$action/work"
    backup="$test_root/$action/backup"
    target_mount="$test_root/$action/target"
    stage="$target_mount/stage"
    previous_tree="$target_mount/previous"
    failed_tree="$target_mount/failed"
    old_moved=0 promoted=0 committed=0 had_target=1 transaction_started=0
    /bin/mkdir -p "$work" "$backup" "$stage/BOOT" "$stage/OC" "$stage/APPLE" "$stage/Microsoft"
    printf 'new boot\n' > "$stage/BOOT/BOOTx64.efi"
    printf 'new core\n' > "$stage/OC/OpenCore.efi"
    printf 'apple remains\n' > "$stage/APPLE/firmware"
    printf 'windows remains\n' > "$stage/Microsoft/bootmgfw.efi"
    tree_manifest "$stage" "$work/staged.txt"
    if [[ "$action" == no-previous || "$action" == no-previous-failure ]]; then
        had_target=0
    else
        /bin/mkdir -p "$target_mount/EFI/BOOT" "$target_mount/EFI/OC" "$target_mount/EFI/APPLE" "$target_mount/EFI/Microsoft"
        printf 'old boot\n' > "$target_mount/EFI/BOOT/BOOTx64.efi"
        printf 'old core\n' > "$target_mount/EFI/OC/OpenCore.efi"
        printf 'apple remains\n' > "$target_mount/EFI/APPLE/firmware"
        printf 'windows remains\n' > "$target_mount/EFI/Microsoft/bootmgfw.efi"
        /bin/cp -R "$target_mount/EFI" "$backup/previous-target-EFI"
    fi
    # Root execution is replaced only in these isolated fixture functions.
    as_admin() {
        if [[ "$action" == rename-failure && "$1" == /bin/mv && "$2" == "$stage" ]]; then return 1; fi
        "$@" || return 1
        # Returning failure here models interruption before the following flag assignment.
        if [[ "$action" == old-rename-signal && "$1" == /bin/mv && "$2" == "$target_mount/EFI" && "$3" == "$previous_tree" ]]; then return 1; fi
        if [[ "$action" == new-rename-signal && "$1" == /bin/mv && "$2" == "$stage" ]]; then return 1; fi
        if [[ ( "$action" == verify-failure || "$action" == no-previous-failure ) && "$1" == /bin/mv && "$2" == "$stage" ]]; then
            printf 'broken\n' > "$target_mount/EFI/OC/OpenCore.efi"
        fi
    }
    target_identity() { [[ "$action" != stale-target ]]; }
    result=0
    promote_stage || result=$?
    if [[ "$action" == success || "$action" == no-previous ]]; then
        [[ "$result" == 0 && "$committed" == 1 && "$promoted" == 1 ]]
        [[ "$(cat "$target_mount/EFI/BOOT/BOOTx64.efi")" == 'new boot' ]]
        [[ "$(cat "$target_mount/EFI/APPLE/firmware")" == 'apple remains' ]]
        [[ "$(cat "$target_mount/EFI/Microsoft/bootmgfw.efi")" == 'windows remains' ]]
        if [[ "$action" == success ]]; then same_tree "$previous_tree" "$backup/previous-target-EFI"; fi
    else
        [[ "$result" != 0 && "$committed" == 0 ]]
        rollback
        if [[ "$action" == no-previous-failure ]]; then
            [[ ! -e "$target_mount/EFI" && -f "$failed_tree/OC/OpenCore.efi" ]]
        else
            same_tree "$target_mount/EFI" "$backup/previous-target-EFI"
        fi
        [[ ! -e "$previous_tree" ]]
        if [[ "$action" == verify-failure ]]; then [[ -f "$failed_tree/OC/OpenCore.efi" ]]; fi
    fi
    printf 'SSD boot transaction fixture passed: %s\n' "$action"
done

if [[ "$(/usr/bin/uname -s)" == Darwin ]]; then
    /bin/bash "$test_dir/check_ssd_native_schema.sh"
fi
