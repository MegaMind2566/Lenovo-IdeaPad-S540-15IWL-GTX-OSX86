#!/bin/bash
# Native macOS / Bash 3.2. Read-only device snapshots and explicit observations.
# No event tap, keystroke recorder, driver loading, registry writes or EFI writes.
set -euo pipefail
umask 077
export LC_ALL=C

EFI_CONFIG='/Volumes/240 GB/EFI/OC/config.plist'
OUTPUT_BASE="${HOME}/Desktop"
INTERACTIVE=1
REPORT=''

fail() { printf 'Function-key collection stopped: %s\n' "$*" >&2; exit 1; }
usage() {
    printf '%s\n' 'Usage: COLLECT-FUNCTION-KEYS.command [--efi-config /absolute/config.plist] [--output-dir /absolute/directory] [--snapshots-only]'
}
while [ "$#" -gt 0 ]; do
    case "$1" in
        --efi-config) [ "$#" -ge 2 ] || fail 'Missing EFI configuration path.'; EFI_CONFIG=$2; shift 2;;
        --output-dir) [ "$#" -ge 2 ] || fail 'Missing output directory.'; OUTPUT_BASE=$2; shift 2;;
        --snapshots-only) INTERACTIVE=0; shift;;
        --help|-h) usage; exit 0;;
        *) usage >&2; fail 'Unknown argument.';;
    esac
done
[ "$(/usr/bin/uname -s)" = Darwin ] || fail 'This collector requires macOS.'
case "$OUTPUT_BASE" in /*) ;; *) fail 'The output directory must be absolute.';; esac
case "$EFI_CONFIG" in /*) ;; *) fail 'The optional EFI configuration path must be absolute.';; esac
case "$OUTPUT_BASE$EFI_CONFIG" in *$'\n'*|*$'\r'*) fail 'Paths cannot contain line breaks.';; esac
[ -d "$OUTPUT_BASE" ] || fail 'The output directory does not exist.'
if [ "$INTERACTIVE" -eq 1 ]; then
    [ -t 0 ] || fail 'Interactive collection requires a Terminal window; use --snapshots-only otherwise.'
fi
REPORT=$(/usr/bin/mktemp -d "$OUTPUT_BASE/FUNCTION-KEYS-XXXXXX") || fail 'Cannot create a private report directory.'
ERRORS="$REPORT/ERRORS.txt"
: > "$ERRORS"

capture() {
    local file=$1
    shift
    if ! "$@" > "$REPORT/$file" 2>> "$ERRORS"; then
        printf 'Unavailable snapshot: %s\n' "$file" >> "$ERRORS"
    fi
    /bin/chmod 600 "$REPORT/$file"
}
capture_registry() {
    local name=$1
    /bin/mkdir "$REPORT/$name"
    capture "$name/PANEL-BRIGHTNESS.plist" /usr/sbin/ioreg -a -r -c AppleBacklightDisplay -l -w 0
    capture "$name/PANEL-BRIGHTNESS.txt" /usr/sbin/ioreg -r -c AppleBacklightDisplay -l -w 0
    capture "$name/BRIGHTNESS-KEYS.txt" /usr/sbin/ioreg -r -c BrightnessKeys -l -w 0
}
brightness_value() {
    local file=$1 value
    value=$(/usr/bin/plutil -extract 0.IODisplayParameters.brightness.value raw -o - "$file" 2>/dev/null) || value=unavailable
    case "$value" in ''|*[!0-9]*) printf '%s' unavailable;; *) printf '%s' "$value";; esac
}
ask_observation() {
    local answer=''
    while :; do
        printf '%s [y/n/u]: ' "$1" >&2
        IFS= read -r answer || fail 'Input ended before the observation was recorded.'
        case "$answer" in
            y|Y) printf '%s' yes; return;;
            n|N) printf '%s' no; return;;
            u|U|'') printf '%s' unknown; return;;
        esac
        printf 'Enter y, n or u (unknown).\n' >&2
    done
}

{
    printf 'Private Lenovo S540 function-key report\n'
    printf 'Collection time UTC: '
    /bin/date -u '+%Y-%m-%dT%H:%M:%SZ'
    /usr/bin/sw_vers
    printf 'Kernel release: '
    /usr/bin/uname -r
    printf 'Architecture: '
    /usr/bin/uname -m
    printf '\nThis collector reads device metadata and records only explicit y/n/u observations.\n'
    printf 'It does not listen to keyboard events, record typed keys, enable LogScanCodes, or change EFI, NVRAM, SIP, drivers or registry properties.\n'
    printf 'Manual brightness-key presses can change brightness through the normal operating-system controls.\n'
    printf 'IORegistry snapshots do not prove that a firmware ACPI Notify event was emitted.\n'
    printf 'Do not commit this report or publish it in a repository.\n'
} > "$REPORT/SUMMARY.txt"
capture DEVICE-TREE-GFX0.txt /usr/sbin/ioreg -p IODeviceTree -r -n GFX0 -l -w 0
capture DEVICE-TREE-IGPU.txt /usr/sbin/ioreg -p IODeviceTree -r -n IGPU -l -w 0
capture DEVICE-TREE-DD1F.txt /usr/sbin/ioreg -p IODeviceTree -r -n DD1F -l -w 0
capture DEVICE-TREE-DD02.txt /usr/sbin/ioreg -p IODeviceTree -r -n DD02 -l -w 0
capture DEVICE-TREE-PNLF.txt /usr/sbin/ioreg -p IODeviceTree -r -n PNLF -l -w 0
capture KEYBOARD.txt /usr/sbin/ioreg -r -c ApplePS2Keyboard -l -w 0
capture KEXTS.txt /usr/bin/kmutil showloaded
capture_registry initial

# Copy only the ACPI and enabled-component metadata, never the whole config or
# its PlatformInfo/NVRAM identity and network settings.
if [ -f "$EFI_CONFIG" ] && [ ! -L "$EFI_CONFIG" ]; then
    if /usr/bin/plutil -lint "$EFI_CONFIG" > /dev/null 2>> "$ERRORS"; then
        capture EFI-ACPI-ADD.plist /usr/bin/plutil -extract ACPI.Add xml1 -o - "$EFI_CONFIG"
        capture EFI-ACPI-PATCH.plist /usr/bin/plutil -extract ACPI.Patch xml1 -o - "$EFI_CONFIG"
        capture EFI-KERNEL-ADD.plist /usr/bin/plutil -extract Kernel.Add xml1 -o - "$EFI_CONFIG"
        capture EFI-UEFI-DRIVERS.plist /usr/bin/plutil -extract UEFI.Drivers xml1 -o - "$EFI_CONFIG"
        printf 'Optional mounted EFI metadata: included; the full config was not copied.\n' >> "$REPORT/SUMMARY.txt"
    else
        printf 'Optional EFI configuration: unreadable or invalid; no configuration data included.\n' >> "$REPORT/SUMMARY.txt"
    fi
else
    printf 'Optional mounted EFI configuration: unavailable; device snapshots still collected.\n' >> "$REPORT/SUMMARY.txt"
fi

printf '%s\n' 'This collector preserves the working EFI and does not monitor typed keys.'
printf '%s\n' 'Keep the report private; do not commit it or upload it to a public repository.'
printf 'test,key,brightness_before,brightness_after,brightness_HUD_reported,brightness_change_reported\n' > "$REPORT/OBSERVATIONS.csv"
if [ "$INTERACTIVE" -eq 1 ]; then
    printf '\nRecord the present keyboard behaviour. Do not change BIOS Hotkey Mode, Fn Lock, macOS keyboard settings or the brightness slider during these four observations.\n'
    printf 'Click an empty area of the desktop before each key press, so Terminal does not handle the function key.\n'
    keys=('F11' 'F12' 'Fn+F11' 'Fn+F12')
    index=0
    for key in "${keys[@]}"; do
        index=$((index + 1))
        label="test-$index"
        capture_registry "$label-before"
        before=$(brightness_value "$REPORT/$label-before/PANEL-BRIGHTNESS.plist")
        printf '\nTest %s: click the desktop, press %s exactly once, then click Terminal and press Enter.\n' "$index" "$key"
        IFS= read -r reply || fail 'Input ended before the test snapshot.'
        capture_registry "$label-after"
        after=$(brightness_value "$REPORT/$label-after/PANEL-BRIGHTNESS.plist")
        hud=$(ask_observation 'Did the macOS brightness indicator appear?')
        change=$(ask_observation 'Did the panel brightness change?')
        printf '%s,%s,%s,%s,%s,%s\n' "$index" "$key" "$before" "$after" "$hud" "$change" >> "$REPORT/OBSERVATIONS.csv"
    done
    printf '\nF1-F3 were previously reported working. '
    volume=$(ask_observation 'Are mute and volume keys still working in normal use?')
    printf 'Previously working F1-F3 reported still working: %s\n' "$volume" >> "$REPORT/SUMMARY.txt"
    printf 'Manual observation completed for F11/F12 with and without Fn.\n' >> "$REPORT/SUMMARY.txt"
else
    printf 'Snapshots-only mode: no manual key observations were performed.\n' >> "$REPORT/SUMMARY.txt"
fi
capture_registry final
/usr/bin/find "$REPORT" -type f -exec /bin/chmod 600 {} \;
BASE=$(/usr/bin/dirname "$REPORT")
NAME=$(/usr/bin/basename "$REPORT")
ARCHIVE="$REPORT.zip"
if (cd "$BASE" && /usr/bin/zip -q -r "$ARCHIVE" "$NAME"); then
    /bin/chmod 600 "$ARCHIVE"
    printf '\nPrivate report saved: %s\n' "$ARCHIVE"
    printf 'The uncompressed report is retained: %s\n' "$REPORT"
else
    printf '\nZIP creation failed. The private report is retained: %s\n' "$REPORT" >&2
    exit 1
fi
