#!/bin/bash
# Native macOS / Bash 3.2. Read diagnostics; write only a private report.
set -uo pipefail
umask 077
export LC_ALL=C

fail() { printf 'Collection not performed: %s\n' "$*" >&2; exit 1; }
[ "$#" -eq 0 ] || fail 'This command takes no arguments.'
[ "$(/usr/bin/uname -s)" = Darwin ] || fail 'Run the command from the macOS Tahoe desktop.'
case "$(/usr/bin/uname -r)" in 25.*) ;; *) fail 'This collection requires macOS Tahoe (Darwin 25).';; esac
[ -d /System/Volumes/Data ] && [ -d /Users ] || fail 'Run from the desktop, not Recovery.'
[ "$(/usr/bin/id -u)" -ne 0 ] || fail 'Run from your own account, without sudo.'
[ -n "${HOME:-}" ] && [ -d "$HOME/Desktop" ] || fail 'The Desktop directory is unavailable.'

WORK=$(/usr/bin/mktemp -d "$HOME/Desktop/DIAGNOSI-AVVIO-RETE-XXXXXX") || fail 'Cannot create the collection on the Desktop.'
SUMMARY="$WORK/RIEPILOGO.txt"
ERRORS="$WORK/ERRORI.txt"
PARTIAL=0
OPTIONAL_STEP=0
ACTIVE_PID=''
WATCH_PID=''
: > "$ERRORS"

stop_children() {
    if [ -n "$WATCH_PID" ]; then /bin/kill "$WATCH_PID" 2>/dev/null || true; fi
    if [ -n "$ACTIVE_PID" ]; then /bin/kill "$ACTIVE_PID" 2>/dev/null || true; fi
}
trap stop_children EXIT
trap 'printf "Collection interrupted. The partial directory remains on the Desktop.\n" >&2; exit 130' INT TERM

note_error() {
    printf '%s\n' "$*" >> "$ERRORS"
    if [ "$OPTIONAL_STEP" -eq 1 ]; then
        printf 'Optional snapshot unavailable: %s\n' "$*" >> "$SUMMARY"
    else
        PARTIAL=$((PARTIAL + 1))
        printf 'Incomplete: %s\n' "$*" >> "$SUMMARY"
    fi
}

# A watchdog bounds each external read, including commands without native timeout.
# No timeout(1), Python, GNU utilities or Bash 4 features are required.
capture() {
    local outfile=$1 seconds=$2 label=$3 marker rc
    shift 3
    marker="$WORK/.timeout-marker"
    /bin/rm -f "$marker"
    "$@" > "$outfile" 2>> "$ERRORS" &
    ACTIVE_PID=$!
    (
        remaining=$seconds
        while [ "$remaining" -gt 0 ]; do
            /bin/kill -0 "$ACTIVE_PID" 2>/dev/null || exit 0
            /bin/sleep 1
            remaining=$((remaining - 1))
        done
        if /bin/kill -0 "$ACTIVE_PID" 2>/dev/null; then
            printf 'timeout\n' > "$marker"
            /bin/kill -TERM "$ACTIVE_PID" 2>/dev/null || true
            /bin/sleep 2
            /bin/kill -KILL "$ACTIVE_PID" 2>/dev/null || true
        fi
    ) &
    WATCH_PID=$!
    wait "$ACTIVE_PID"
    rc=$?
    /bin/kill "$WATCH_PID" 2>/dev/null || true
    wait "$WATCH_PID" 2>/dev/null || true
    ACTIVE_PID=''
    WATCH_PID=''
    if [ -f "$marker" ]; then
        /bin/rm -f "$marker"
        note_error "$label: ${seconds}s time limit exceeded."
        return 1
    fi
    if [ "$rc" -ne 0 ]; then
        note_error "$label: command exited with code $rc."
        return 1
    fi
    printf 'Read: %s\n' "$label" >> "$SUMMARY"
    return 0
}

capture_optional() {
    local rc
    OPTIONAL_STEP=1
    capture "$@"
    rc=$?
    OPTIONAL_STEP=0
    return "$rc"
}

{
    printf 'Startup, Bluetooth and network diagnostics — Tahoe desktop\n'
    printf 'Private collection. It may contain hardware addresses and messages from the selected processes.\n'
    printf 'Do not publish this ZIP in the repository.\n'
    printf 'No changes to EFI, NVRAM, drivers, settings or the log archive.\n'
    printf 'Does not copy EFI, the complete config, Wi-Fi credentials or the itlwm Info.plist.\n'
    printf 'Requests the log interval covering the first five minutes of the current boot.\n'
    printf 'The reader may return events outside that interval or from other boots; verify the session and sequence.\n'
    printf 'Messages not retained by the system cannot be recovered.\n'
    printf 'Current device snapshots were taken after boot.\n'
} > "$SUMMARY"

printf 'Collecting startup, Bluetooth, USB, graphics and network interface data...\n'
capture "$WORK/VERSIONE-MACOS.txt" 10 'macOS version' /usr/bin/sw_vers || true
capture "$WORK/BOOT-TIME.txt" 10 'boot time' /usr/sbin/sysctl kern.boottime || true
capture "$WORK/BOOT-ARGS.txt" 10 'active boot arguments' /usr/sbin/sysctl -n kern.bootargs || true
capture "$WORK/BOOT-SESSION.txt" 10 'boot session' /usr/sbin/sysctl -n kern.bootsessionuuid || true

boot_epoch=$(/usr/bin/sed -n 's/.*sec = \([0-9][0-9]*\),.*/\1/p' "$WORK/BOOT-TIME.txt")
now_epoch=$(/bin/date +%s)
window_valid=1
case "$boot_epoch" in ''|*[!0-9]*) window_valid=0;; esac
case "$now_epoch" in ''|*[!0-9]*) window_valid=0;; esac
if [ "$window_valid" -eq 1 ] && [ "$boot_epoch" -le "$now_epoch" ]; then
    end_epoch=$((boot_epoch + 300))
    [ "$end_epoch" -le "$now_epoch" ] || end_epoch=$now_epoch
    start_date=$(/bin/date -r "$boot_epoch" '+%Y-%m-%d %H:%M:%S%z') || window_valid=0
    end_date=$(/bin/date -r "$end_epoch" '+%Y-%m-%d %H:%M:%S%z') || window_valid=0
else
    window_valid=0
fi
if [ "$window_valid" -eq 1 ]; then
    {
        printf 'Boot epoch: %s\nEnd epoch: %s\n' "$boot_epoch" "$end_epoch"
        printf 'From: %s\nTo: %s\n' "$start_date" "$end_date"
        printf 'Available duration: %ss (maximum 300s).\n' "$((end_epoch - boot_epoch))"
    } > "$WORK/FINESTRA-AVVIO.txt"
    predicate='process IN {"kernel", "WindowServer", "loginwindow", "bluetoothd", "BlueTool", "configd", "corebrightnessd", "diskarbitrationd"}'
    printf 'Your account password may be requested to read boot logs.\n'
    if /usr/bin/sudo -v; then
        capture "$WORK/AVVIO-PRIMI-5-MINUTI.log" 60 'current boot log' \
            /usr/bin/sudo -n /usr/bin/log show --style compact --color none --info --no-debug --no-pager \
            --start "$start_date" --end "$end_date" --predicate "$predicate" || true
    else
        note_error 'Authentication cancelled or unavailable; boot logs were not collected.'
    fi
else
    note_error 'Invalid boot time; no generic historical log was used as a substitute.'
fi

capture "$WORK/DISPOSITIVI.txt" 45 'Bluetooth, USB and graphics' \
    /usr/sbin/system_profiler -detailLevel mini -timeout 30 SPBluetoothDataType SPUSBDataType SPDisplaysDataType || true
capture "$WORK/PORTE-RETE.txt" 15 'network hardware ports' /usr/sbin/networksetup -listallhardwareports || true
capture "$WORK/SERVIZI-RETE.txt" 15 'network services' /usr/sbin/networksetup -listallnetworkservices || true

capture "$WORK/.kexts-tmp" 30 'loaded drivers' /usr/bin/kmutil showloaded || true
# Keep relevant rows only. No raw copy of all loaded drivers remains in the ZIP.
/usr/bin/grep -Ei 'Lilu|WhateverGreen|RestrictEvents|IntelBluetooth|IntelBTPatcher|BlueToolFixup|BrcmPatchRAM|itlwm|AirportItlwm|USBToolBox|UTBMap|IOUSBHostFamily|IOBluetooth|AppleIntel.*Graphics|AppleIntel.*Framebuffer|IntelAccelerator|VoodooHDA|AppleALC|VirtualSMC|SMCBatteryManager' \
    "$WORK/.kexts-tmp" > "$WORK/DRIVER-CARICATI.txt" || true
if [ ! -s "$WORK/DRIVER-CARICATI.txt" ]; then
    printf 'No relevant rows returned. See ERRORI.txt.\n' >> "$WORK/DRIVER-CARICATI.txt"
fi
/bin/rm -f "$WORK/.kexts-tmp"

FRAMEBUFFER_INFO='/System/Library/Extensions/AppleIntelCFLGraphicsFramebuffer.kext/Contents/Info.plist'
if [ -f "$FRAMEBUFFER_INFO" ]; then
    capture "$WORK/VERSIONE-FRAMEBUFFER.txt" 10 'installed CFL framebuffer version' \
        /usr/libexec/PlistBuddy -c 'Print :CFBundleVersion' "$FRAMEBUFFER_INFO" || true
else
    printf 'CFL framebuffer Info.plist is not at the expected path.\n' > "$WORK/VERSIONE-FRAMEBUFFER.txt"
fi

for class in IntelBluetoothFirmware IOBluetoothHCIController AppleIntelFramebuffer IntelAccelerator; do
    capture "$WORK/IOREG-$class.txt" 15 "IORegistry $class" /usr/sbin/ioreg -r -c "$class" -d 1 -l || true
    if [ ! -s "$WORK/IOREG-$class.txt" ]; then
        printf 'Class %s is absent from this snapshot.\n' "$class" >> "$WORK/IOREG-$class.txt"
    fi
done

capture "$WORK/.usb-tmp" 15 'USB device firmware state' /usr/sbin/ioreg -p IOUSB -l -w 0 || true
/usr/bin/grep -B 8 -A 16 'FirmwareLoaded' "$WORK/.usb-tmp" > "$WORK/IOREG-USB-FIRMWARE.txt" || true
if [ ! -s "$WORK/IOREG-USB-FIRMWARE.txt" ]; then
    printf 'No FirmwareLoaded property returned in the IOUSB plane. See ERRORI.txt.\n' >> "$WORK/IOREG-USB-FIRMWARE.txt"
fi
# Keep only the context of FirmwareLoaded, not a full USB IORegistry copy.
/bin/rm -f "$WORK/.usb-tmp"

for key in bluetoothExternalDongleFailed bluetoothInternalControllerInfo; do
    capture_optional "$WORK/NVRAM-$key.txt" 10 "reading $key" /usr/sbin/nvram -x "$key" || true
    if [ ! -s "$WORK/NVRAM-$key.txt" ]; then
        printf 'Variable missing or unreadable. No changes made.\n' >> "$WORK/NVRAM-$key.txt"
    fi
done

# Read only named harmless fields, never the full config or Wi-Fi kext Info.plist.
CONFIG='/Volumes/240 GB/EFI/OC/config.plist'
SELECTED="$WORK/CONFIG-SELEZIONATO.txt"
if [ -f "$CONFIG" ] && [ ! -L "$CONFIG" ]; then
    {
        printf 'Selected fields from the config on 240 GB.\n'
        printf 'The file being present does not prove it was used for the current boot.\n'
        printf 'No PlatformInfo, NVRAM, comments or itlwm Info.plist included.\n'
    } > "$SELECTED"
    if /usr/bin/plutil -lint "$CONFIG" >/dev/null 2>> "$ERRORS"; then
        i=0
        while bundle=$(/usr/libexec/PlistBuddy -c "Print :Kernel:Add:$i:BundlePath" "$CONFIG" 2>/dev/null); do
            printf '\nKernel/Add/%s BundlePath: %s\n' "$i" "$bundle" >> "$SELECTED"
            for key in Enabled MinKernel MaxKernel; do
                value=$(/usr/libexec/PlistBuddy -c "Print :Kernel:Add:$i:$key" "$CONFIG" 2>/dev/null) || value='(missing)'
                printf '%s: %s\n' "$key" "$value" >> "$SELECTED"
            done
            i=$((i + 1))
        done
        i=0
        while identifier=$(/usr/libexec/PlistBuddy -c "Print :Kernel:Block:$i:Identifier" "$CONFIG" 2>/dev/null); do
            printf '\nKernel/Block/%s Identifier: %s\n' "$i" "$identifier" >> "$SELECTED"
            for key in Enabled MinKernel MaxKernel Strategy; do
                value=$(/usr/libexec/PlistBuddy -c "Print :Kernel:Block:$i:$key" "$CONFIG" 2>/dev/null) || value='(missing)'
                printf '%s: %s\n' "$key" "$value" >> "$SELECTED"
            done
            i=$((i + 1))
        done
        gpu='DeviceProperties.Add.PciRoot(0x0)/Pci(0x2,0x0)'
        for key in AAPL,ig-platform-id device-id framebuffer-patch-enable framebuffer-stolenmem framebuffer-fbmem; do
            printf '\nIGPU/%s (typed XML):\n' "$key" >> "$SELECTED"
            if ! /usr/bin/plutil -extract "$gpu.$key" xml1 -o - "$CONFIG" >> "$SELECTED" 2>/dev/null; then
                printf '(missing)\n' >> "$SELECTED"
            fi
        done
    else
        note_error 'The config on 240 GB fails plutil -lint; fields were not collected.'
    fi
else
    printf 'Config on 240 GB unavailable; no volume was mounted or modified.\n' > "$SELECTED"
fi

printf 'Incomplete checks: %s\n' "$PARTIAL" >> "$SUMMARY"
ARCHIVE="$WORK.zip"
[ ! -e "$ARCHIVE" ] || fail "$ARCHIVE already exists; the collection will not overwrite it."
printf 'Creating the ZIP on the Desktop...\n'
if ! capture "$WORK/CREAZIONE-ZIP.txt" 45 'ZIP creation' \
    /usr/bin/ditto -c -k --norsrc --noextattr --noacl --noqtn --keepParent "$WORK" "$ARCHIVE"; then
    printf '\nZIP creation did not complete. Keep the directory: %s\n' "$WORK" >&2
    exit 1
fi
[ -s "$ARCHIVE" ] || fail "ZIP empty or missing. Keep directory $WORK."
printf '\nCollection saved: %s\n' "$ARCHIVE"
printf 'Attach this ZIP in the chat. The private directory is preserved.\n'
if [ "$PARTIAL" -gt 0 ]; then
    printf 'Some checks are incomplete; see ERRORI.txt for details.\n'
fi
