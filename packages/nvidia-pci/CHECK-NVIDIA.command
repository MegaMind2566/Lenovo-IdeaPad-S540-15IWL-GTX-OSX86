#!/bin/bash
set -euo pipefail
umask 077

stop() { printf 'NVIDIA PCI inventory stopped: %s\n' "$*" >&2; exit 1; }
if [ "$#" -eq 1 ] && [ "$1" = --help ]; then
    printf 'Usage: CHECK-NVIDIA.command [--output-dir EXISTING_DIRECTORY]\n'
    exit 0
fi
REPORT_PARENT="${HOME}/Desktop"
if [ "$#" -gt 0 ]; then
    [ "$#" -eq 2 ] && [ "$1" = --output-dir ] || stop 'Unrecognized arguments.'
    REPORT_PARENT=$2
fi
[ "$(/usr/bin/uname -s)" = Darwin ] && [ "$(/usr/bin/uname -m)" = x86_64 ] || stop 'Intel macOS is required.'
[ -d "$REPORT_PARENT" ] && [ -w "$REPORT_PARENT" ] || stop 'The report destination is not a writable directory.'
REPORT_PARENT=$(cd -P "$REPORT_PARENT" && pwd)
PACKAGE=$(cd -P "$(/usr/bin/dirname "${BASH_SOURCE[0]}")" && pwd)
BINARY="$PACKAGE/bin/nvidia-pci-inventory"
BINARY_SHA='NVIDIA_PCI_BINARY_SHA_PENDING'
[ -f "$BINARY" ] && [ ! -L "$BINARY" ] && [ -x "$BINARY" ] || stop 'The compiled executable is missing. Use the complete built ZIP.'
ACTUAL_SHA=$(/usr/bin/shasum -a 256 "$BINARY" | /usr/bin/awk '{print $1}')
[ "$ACTUAL_SHA" = "$BINARY_SHA" ] || stop 'The executable differs from this package.'
/usr/bin/codesign --verify --strict "$BINARY" || stop 'The executable signature could not be verified.'
REPORT_DIR=$(/usr/bin/mktemp -d "$REPORT_PARENT/NVIDIA-PCI.XXXXXX") || stop 'Cannot create a private report folder.'
REPORT="$REPORT_DIR/nvidia-pci.json"
printf 'Reading published GPU metadata. No administrator password is required.\n'
RESULT=0
"$BINARY" > "$REPORT" || RESULT=$?
/bin/chmod 600 "$REPORT"
/bin/cat "$REPORT"
printf '\nReport saved: %s\n' "$REPORT"
if [ "$RESULT" -ne 0 ]; then
    printf 'The inventory is incomplete. Keep the report for diagnosis.\n' >&2
    exit "$RESULT"
fi
printf 'Share nvidia-pci.json to select the next NVIDIA port milestone.\n'
