#!/bin/bash
# Read installed-system reports from Data; write only to the OpenCore HDD.
set -euo pipefail
umask 077

fail() { printf 'Collection not performed: %s\n' "$*" >&2; exit 1; }

unified=0
intel=0
data_root=''
while [ "$#" -gt 0 ]; do
    case "$1" in
        --unified) unified=1 ;;
        --intel) intel=1 ;;
        --help)
            printf 'Usage: bash collect_gui_logs.sh [--unified] [--intel] ["/Volumes/Machintosh SSD - Data"]\n'
            printf '%s\n' '--unified includes diagnostics and uuidtext from the installed system.'
            printf '%s\n' '--intel includes direct Lilu/WhateverGreen files and the trace configuration.'
            exit 0 ;;
        --*) fail "Unknown option: $1" ;;
        *)
            [ -z "$data_root" ] || fail 'Specify at most one Data volume path.'
            [ -n "$1" ] || fail 'The Data path cannot be empty.'
            data_root=$1 ;;
    esac
    shift
done
if [ "$(uname -s)" != 'Darwin' ]; then
    fail 'Run this program from macOS Recovery Terminal.'
fi

bundle_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
[ -d "$bundle_root/EFI/OC" ] || fail 'Extract the package to the OpenCore HDD root, alongside EFI.'

if [ -z "$data_root" ]; then
    for candidate in '/Volumes/Machintosh SSD - Data' '/Volumes/Machintosh SSD - Dati'; do
        if [ -d "$candidate/Library" ] && [ -d "$candidate/private/var" ] && [ -d "$candidate/Users" ]; then
            [ -z "$data_root" ] || fail 'Multiple candidate volumes: explicitly specify the Samsung Data path.'
            data_root=$candidate
        fi
    done
fi
if [ -z "$data_root" ] || [ ! -d "$data_root" ]; then
    printf 'Currently mounted volumes:\n' >&2
    ls -1 /Volumes >&2 || true
    fail 'Mount the Samsung Data volume in Disk Utility. If its name differs, pass it as an argument.'
fi
data_root=$(cd "$data_root" && pwd -P)
case "$data_root" in
    /Volumes/*) ;;
    *) fail 'Select the Data volume mounted under /Volumes, rather than the running Recovery system.' ;;
esac
[ -d "$data_root/Library" ] && [ -d "$data_root/private/var" ] && [ -d "$data_root/Users" ] || fail 'The path does not contain the expected Data volume structure.'
case "$bundle_root/" in
    "$data_root/"*) fail 'The destination must be on the OpenCore HDD, outside the Data volume.' ;;
esac
command -v ditto >/dev/null 2>&1 || fail 'ditto is unavailable in this Recovery environment.'

space_check='not requested'
if [ "$unified" -eq 1 ]; then
    missing_space_tools=''
    for utility in du df awk; do
        if ! command -v "$utility" >/dev/null 2>&1; then
            missing_space_tools="$missing_space_tools $utility"
        fi
    done
    if [ -z "$missing_space_tools" ]; then
    unified_kb=0
    for source in "$data_root/private/var/db/diagnostics" "$data_root/private/var/db/uuidtext"; do
        if [ -d "$source" ]; then
            source_kb=$(du -sk "$source" | awk '{print $1}') || fail 'Cannot estimate the unified log size.'
            case "$source_kb" in ''|*[!0-9]*) fail 'Invalid log size.' ;; esac
            unified_kb=$((unified_kb + source_kb))
        fi
    done
    free_kb=$(LC_ALL=C df -Pk "$bundle_root" | awk 'END {print $4}') || fail 'Cannot read free space on the HDD.'
    case "$free_kb" in ''|*[!0-9]*) fail 'Invalid free space value.' ;; esac
    # Retain the raw copy and ZIP; reserve additional room for reports.
    needed_kb=$((unified_kb * 2 + 65536))
    [ "$free_kb" -ge "$needed_kb" ] || fail 'Insufficient HDD space to retain the log folder and ZIP.'
    printf 'Unified logs: about %s MB; starting collection.\n' "$((unified_kb / 1024))"
        space_check='estimate available; sufficient space at the time of the check'
    else
        space_check="estimate unavailable; missing tools:$missing_space_tools"
        printf 'Space estimate unavailable (missing:%s). Proceeding with log copying.\n' "$missing_space_tools"
    fi
fi

work=$(mktemp -d "$bundle_root/DIAGNOSI-MACOS-XXXXXX")
summary="$work/RIEPILOGO.txt"
errors="$work/ERRORI-COPIA.txt"
: > "$errors"
copied=0
missing=0
copy_errors=0

{
    printf 'Offline collection of installed-system reports\n'
    printf 'Data source: %s\n' "$data_root"
    printf 'Destination: %s\n' "$work"
    printf 'The program reads Data and writes only this collection to the HDD.\n'
    printf 'Reports are not filtered by date: clocks may differ between attempts.\n'
    printf 'It does not run log show or sysdiagnose on the Recovery system.\n'
    printf 'Unified log collection requested: %s\n' "$unified"
    printf 'Space check: %s\n' "$space_check"
    if [ -e "$data_root/private/var/db/.AppleSetupDone" ]; then
        printf 'Initial setup marker: present\n'
    else
        printf 'Initial setup marker: absent\n'
    fi
} > "$summary"

copy_item() {
    local source=$1 label=$2
    if [ -e "$source" ]; then
        # Diagnostic data needs file contents, not macOS extended attributes.
        # FAT/exFAT destinations can reject those attributes despite copying data.
        if cp -RX "$source" "$work/$label" 2>> "$errors"; then
            printf 'Copied: %s\n' "$label" >> "$summary"
            copied=$((copied + 1))
        else
            printf 'Incomplete copy: %s\n' "$label" >> "$summary"
            copy_errors=$((copy_errors + 1))
        fi
    else
        printf 'Missing: %s\n' "$label" >> "$summary"
        missing=$((missing + 1))
    fi
}

copy_item "$data_root/Library/Logs/DiagnosticReports" 'DiagnosticReports-sistema'
shopt -s nullglob
user_index=0
for report_dir in "$data_root"/Users/*/Library/Logs/DiagnosticReports; do
    user_index=$((user_index + 1))
    copy_item "$report_dir" "DiagnosticReports-utente-$user_index"
done
printf 'User report folders found: %s\n' "$user_index" >> "$summary"
copy_item "$data_root/private/var/log/install.log" 'install.log'
copy_item "$data_root/private/var/log/system.log" 'system.log'

if [ "$intel" -eq 1 ]; then
    mkdir "$work/TracciaIntel"
    intel_found=0
    for trace in "$data_root"/private/var/log/Lilu_*.txt "$data_root"/private/var/log/AppleIntelFramebuffer_*; do
        copy_item "$trace" "TracciaIntel/${trace##*/}"
        intel_found=$((intel_found + 1))
    done
    printf 'Direct Intel files found: %s\n' "$intel_found" >> "$summary"
    if [ "$intel_found" -eq 0 ]; then
        printf 'No direct Intel files found; the summary also records this absence.\n'
    fi
    copy_item "$bundle_root/EFI/OC/backup-traccia-intel" 'TracciaIntel/backup-traccia-intel'
    copy_item "$bundle_root/EFI/OC/config.plist" 'TracciaIntel/config-recovery.plist'
    if [ -f "$bundle_root/EFI/OC/config.before-intel-memory.plist" ]; then
        mkdir "$work/TracciaIntel/Memoria"
        for name in config.before-intel-memory.plist config.before-intel-memory.json config.intel-memory.normal.plist config.intel-memory.recovery.plist; do
            copy_item "$bundle_root/EFI/OC/$name" "TracciaIntel/Memoria/$name"
        done
    fi
fi

# The dedicated Recovery preparation saves the exact normal-boot config.
# Keep it private in the report so runtime events can be matched to its values.
if [ -f "$bundle_root/EFI/OC/config.before-runtime-logs.plist" ]; then
    copy_item "$bundle_root/EFI/OC/config.before-runtime-logs.plist" 'config-avvio-normale.plist'
    copy_item "$bundle_root/EFI/OC/config.plist" 'config-recovery.plist'
fi

unified_complete=0
if [ "$unified" -eq 1 ]; then
    mkdir "$work/UnifiedLogs"
    copied_before=$copied
    printf 'Copying diagnostics from the Samsung Data volume...\n'
    copy_item "$data_root/private/var/db/diagnostics" 'UnifiedLogs/diagnostics'
    printf 'Copying uuidtext from the Samsung Data volume...\n'
    copy_item "$data_root/private/var/db/uuidtext" 'UnifiedLogs/uuidtext'
    if [ "$copied" -eq "$((copied_before + 2))" ] && [ -d "$work/UnifiedLogs/diagnostics" ] && [ -d "$work/UnifiedLogs/uuidtext" ]; then
        unified_complete=1
        printf 'Unified log pair: copied without reported errors\n' >> "$summary"
    else
        printf 'Unified log pair: incomplete or missing; check ERRORI-COPIA.txt\n' >> "$summary"
    fi
    printf 'diagnostics and uuidtext are separate offline data, rather than a converted logarchive.\n' >> "$summary"
fi

if command -v diskutil >/dev/null 2>&1; then
    diskutil apfs list > "$work/VOLUMI-APFS.txt" 2>> "$errors" || true
fi
find "$work" -type f -print > "$work/INVENTARIO.txt"
{
    printf 'Items copied: %s; missing: %s; incomplete copies: %s\n' "$copied" "$missing" "$copy_errors"
    printf 'The absence of a report does not prove that the process works.\n'
} >> "$summary"

archive="$work.zip"
printf 'Creating ZIP...\n'
ditto -c -k "$work" "$archive"
printf '\nCollection saved: %s\n' "$archive"
printf 'Attach that ZIP file to the chat. The collection folder is retained.\n'
if [ "$copy_errors" -gt 0 ]; then
    printf 'Some copies are incomplete: details are in the ZIP.\n'
fi
if [ "$unified" -eq 1 ] && [ "$unified_complete" -eq 0 ]; then
    printf 'Unified logs are incomplete or missing. Attach the ZIP with its summary anyway.\n'
fi
