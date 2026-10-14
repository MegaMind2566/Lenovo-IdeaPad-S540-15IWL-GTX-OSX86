#!/bin/bash
set -euo pipefail
umask 077

stop() { printf 'NVIDIA visibility preparation stopped: %s\n' "$*" >&2; exit 1; }
if [ "$#" -eq 1 ] && [ "$1" = --help ]; then
    printf 'Usage: PREPARE-NVIDIA.command [MOUNTED_CURRENT_SAMSUNG_EFI_DIRECTORY]\n'
    exit 0
fi
[ "$#" -le 1 ] || stop 'Provide at most one source EFI directory.'
[ "$(/usr/bin/uname -s)" = Darwin ] && [ "$(/usr/bin/uname -m)" = x86_64 ] || stop 'Intel macOS is required.'
PACKAGE=$(cd -P "$(/usr/bin/dirname "${BASH_SOURCE[0]}")" && pwd)
LOCATOR="$PACKAGE/bin/locate-efi"
STAGER="$PACKAGE/bin/prepare-nvidia-visibility"
VALIDATOR="$PACKAGE/bin/ocvalidate"
check_binary() {
    local file=$1 expected=$2 actual
    [ -f "$file" ] && [ ! -L "$file" ] && [ -x "$file" ] || stop 'A compiled tool is missing. Use the complete built ZIP.'
    actual=$(/usr/bin/shasum -a 256 "$file" | /usr/bin/awk '{print $1}')
    [ "$actual" = "$expected" ] || stop 'A packaged executable has changed.'
    /usr/bin/codesign --verify --strict "$file" || stop 'An executable signature could not be verified.'
}
check_binary "$LOCATOR" 'NVIDIA_LOCATOR_SHA_PENDING'
check_binary "$STAGER" 'NVIDIA_STAGER_SHA_PENDING'
check_binary "$VALIDATOR" 'NVIDIA_OCVALIDATE_SHA_PENDING'

if [ "$#" -eq 1 ]; then
    SOURCE=$1
else
    PREFLIGHT=$(/usr/bin/mktemp -d /tmp/s540-nvidia-source.XXXXXX)
    cleanup() { case "$PREFLIGHT" in /tmp/s540-nvidia-source.*) /bin/rm -rf "$PREFLIGHT";; esac; }
    trap cleanup EXIT
    if ! "$LOCATOR" --locate-json > "$PREFLIGHT/before.json"; then
        /bin/cat "$PREFLIGHT/before.json" >&2
        stop 'Automatic source selection is unavailable. Mount the current Samsung EFI and pass its EFI folder as the sole argument.'
    fi
    partition=$(/usr/bin/plutil -extract efiPartition raw -o - "$PREFLIGHT/before.json")
    mounted=$(/usr/bin/plutil -extract mounted raw -o - "$PREFLIGHT/before.json")
    [[ "$partition" =~ ^disk[0-9]+s[0-9]+$ ]] || stop 'The selected EFI partition is invalid.'
    if [ "$mounted" != true ]; then
        printf 'The administrator password is needed only to mount the Samsung EFI read-only.\n'
        /usr/bin/sudo /usr/sbin/diskutil mount readOnly "$partition" || stop 'The source EFI could not be mounted.'
        "$LOCATOR" --locate-json > "$PREFLIGHT/after.json" || stop 'The source mapping changed after mounting.'
        for key in efiPartition efiPartitionUUID physicalStore wholeDisk container; do
            before=$(/usr/bin/plutil -extract "$key" raw -o - "$PREFLIGHT/before.json")
            after=$(/usr/bin/plutil -extract "$key" raw -o - "$PREFLIGHT/after.json")
            [ "$before" = "$after" ] || stop 'The source identity changed after mounting.'
        done
    else
        /bin/cp "$PREFLIGHT/before.json" "$PREFLIGHT/after.json"
    fi
    mount_point=$(/usr/bin/plutil -extract mountPoint raw -o - "$PREFLIGHT/after.json")
    [ -d "$mount_point" ] || stop 'The source EFI has no mounted directory.'
    SOURCE="$mount_point/EFI"
fi
[ -d "$HOME/Desktop" ] && [ -w "$HOME/Desktop" ] || stop 'The Desktop is not writable.'
printf 'Source EFI: %s\n' "$SOURCE"
printf 'Preparing a separate private copy. The source EFI and NVRAM will not be changed by this command.\n'
"$STAGER" "$SOURCE" "$HOME/Desktop" "$VALIDATOR"
