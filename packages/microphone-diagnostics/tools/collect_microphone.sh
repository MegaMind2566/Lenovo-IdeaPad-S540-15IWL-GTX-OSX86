#!/bin/bash
# macOS native / Bash 3.2. Read only; writes a private diagnostic ZIP.
set -uo pipefail
umask 077
export LC_ALL=C

WORK=''
ACTIVE_PID=''
WATCH_PID=''
MANUAL_CHANGED=0
fail() {
    printf 'Collection did not complete: %s\n' "$*" >&2
    if [ -n "$WORK" ]; then
        printf 'The partial directory remains here: %s\n' "$WORK" >&2
    fi
    if [ "$MANUAL_CHANGED" -eq 1 ]; then
        printf 'Manually restore the input volume to the value you noted.\n' >&2
    fi
    exit 1
}

stop_children() {
    if [ -n "$WATCH_PID" ]; then /bin/kill "$WATCH_PID" 2>/dev/null || true; fi
    if [ -n "$ACTIVE_PID" ]; then /bin/kill "$ACTIVE_PID" 2>/dev/null || true; fi
}
trap stop_children EXIT
trap 'fail "Operation interrupted."' INT TERM

[ "$#" -eq 0 ] || fail 'This command takes no arguments.'
[ "$(/usr/bin/uname -s)" = Darwin ] || fail 'Run from the macOS desktop.'
[ "$(/usr/bin/uname -m)" = x86_64 ] || fail 'This package requires the Intel laptop.'
[ -d /System/Volumes/Data ] && [ -d /Users ] || fail 'Run from the desktop, not Recovery.'
[ "$(/usr/bin/id -u)" -ne 0 ] || fail 'Run from your own account, without sudo.'
[ -n "${HOME:-}" ] && [ -d "$HOME/Desktop" ] || fail 'The Desktop is unavailable.'

PACKAGE=$(cd -P "$(/usr/bin/dirname "${BASH_SOURCE[0]}")/.." && pwd) || fail 'Cannot locate the package.'
BIN="$PACKAGE/bin/hda_mixer_snapshot"
SUMS="$PACKAGE/SHA256SUMS"
DRIVER_BUNDLE='/Library/Extensions/VoodooHDA.kext'
DRIVER="$DRIVER_BUNDLE/Contents/MacOS/VoodooHDA"
DRIVER_CHECK="$PACKAGE/tools/verify_microphone_driver.sh"
AUDIO_BACKUP='/Volumes/240 GB/EFI/OC/backup-audio-tahoe'
DRIVER_SHA=''

ordinary_file() { [ -f "$1" ] && [ ! -L "$1" ]; }
hash() { /usr/bin/shasum -a 256 "$1" | /usr/bin/awk '{print $1}'; }
ordinary_file "$BIN" && [ -x "$BIN" ] || fail 'The verified reader is missing or is not executable.'
ordinary_file "$SUMS" || fail 'The reader SHA256 manifest is missing.'
EXPECTED=$(/usr/bin/awk 'NF == 2 && $2 == "bin/hda_mixer_snapshot" && length($1) == 64 && $1 !~ /[^0-9a-f]/ {print $1}' "$SUMS") || fail 'Cannot read the manifest.'
case "$EXPECTED" in ''|*[!0-9a-f]*) fail 'Invalid SHA256 manifest.';; esac
[ "${#EXPECTED}" -eq 64 ] || fail 'The manifest must contain a single hash.'
printf '%s  bin/hda_mixer_snapshot\n' "$EXPECTED" | /usr/bin/cmp -s - "$SUMS" || fail 'The manifest has an unexpected format.'
[ "$(hash "$BIN")" = "$EXPECTED" ] || fail 'The reader does not match the manifest; it will not be executed.'
ordinary_file "$DRIVER" || fail 'The installed VoodooHDA driver is unavailable.'
ordinary_file "$DRIVER_CHECK" || fail 'The audio variant check is missing.'

WORK=$(/usr/bin/mktemp -d "$HOME/Desktop/DIAGNOSI-MICROFONO-XXXXXX") || fail 'Cannot create the collection directory.'
ERRORS="$WORK/ERRORI.txt"
SUMMARY="$WORK/RIEPILOGO.txt"
: > "$ERRORS"

# Bound each external read. No GNU timeout, Python, compiler or administrator
# permission is required. Failure is reported; the script never retries as root.
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
        fail "$label: ${seconds}s time limit exceeded."
    fi
    if [ "$rc" -ne 0 ]; then
        if [ "$label" = 'mixer snapshot' ]; then
            printf 'The reader could not finish accessing the driver. sudo will not be requested.\n' >&2
        fi
        [ ! -s "$ERRORS" ] || /bin/cat "$ERRORS" >&2
        fail "$label: command exited with code $rc."
    fi
}

capture "$WORK/DRIVER-VERIFICA.txt" 30 'audio variant verification' /bin/bash "$DRIVER_CHECK" "$DRIVER_BUNDLE" "$AUDIO_BACKUP"
DRIVER_SHA=$(/bin/cat "$WORK/DRIVER-VERIFICA.txt") || fail 'Cannot read the audio verification result.'
case "$DRIVER_SHA" in ''|*[!0-9a-f]*) fail 'The audio check did not return a valid hash.';; esac
[ "${#DRIVER_SHA}" -eq 64 ] || fail 'The audio check did not return a single hash.'
capture "$WORK/DRIVER-CARICATI.txt" 20 'loaded driver verification' /usr/bin/kmutil showloaded
/usr/bin/grep -Eq 'org\.voodoo\.driver\.VoodooHDA[[:space:]]+\(3\.6\.8\)' "$WORK/DRIVER-CARICATI.txt" || fail 'VoodooHDA 3.6.8 is not loaded. Restart with the working audio configuration.'
# Keep only the relevant audio/Lilu entries, not a complete kext listing.
/usr/bin/grep -E 'AppleHDA|AppleALC|Lilu|VoodooHDA' "$WORK/DRIVER-CARICATI.txt" > "$WORK/DRIVER-AUDIO.txt" || fail 'Cannot save the audio driver summary.'
/bin/rm -f "$WORK/DRIVER-CARICATI.txt"
capture "$WORK/AUDIO.txt" 30 'audio detection' /usr/sbin/system_profiler SPAudioDataType
capture "$WORK/CONTROLLI-INIZIALI.txt" 15 'initial input controls' /usr/sbin/ioreg -r -c IOAudioLevelControl -l -w 0
{
    printf 'Private VoodooHDA 3.6.8 microphone diagnostics\n'
    printf 'Reader SHA256: %s\nDriver SHA256: %s\n' "$EXPECTED" "$DRIVER_SHA"
    printf 'Two snapshots: input volume manually set to 30%% and 70%%.\n'
    printf 'This command does not change EFI, NVRAM, SIP, drivers or audio settings.\n'
    printf 'Mixer snapshots contain cached left-channel percentages, not dB.\n'
    printf 'The initialization buffers already exist; no new codec graph is generated.\n'
    printf 'Initialization buffers may be empty or unavailable without invalidating mixer snapshots.\n'
    printf 'Do not publish this ZIP in the repository.\n'
} > "$SUMMARY"

printf '\nOpen System Settings > Sound > Input.\n'
printf 'Disconnect Bluetooth headphones and select the internal microphone.\n'
printf 'Note the current input volume so you can restore it afterwards.\n'
printf 'Keep output volume unchanged during both snapshots.\n'
printf 'No voice recording is needed; we are comparing driver controls.\n'

snapshot() {
    local name=$1 percent=$2 folder answer
    MANUAL_CHANGED=1
    printf '\nSet input volume to about %s%%, then press ENTER.\n' "$percent"
    IFS= read -r answer || fail 'No input volume confirmation was received.'
    folder="$WORK/$name"
    /bin/mkdir "$folder" || fail 'Cannot create the snapshot directory.'
    # Recheck both executables before every probe execution.
    [ "$(hash "$BIN")" = "$EXPECTED" ] || fail 'The reader changed during collection.'
    [ "$(hash "$DRIVER")" = "$DRIVER_SHA" ] || fail 'The driver changed during collection.'
    capture "$folder/LETTURA.txt" 20 'mixer snapshot' "$BIN" --output-dir "$folder"
    ordinary_file "$folder/mixers.json" && [ -s "$folder/mixers.json" ] || fail 'The snapshot did not produce mixer data.'
    capture "$folder/CONTROLLI-AUDIO.txt" 15 'audio controls' /usr/sbin/ioreg -r -c IOAudioLevelControl -l -w 0
    printf '%s%% snapshot completed.\n' "$percent"
    printf 'Snapshot %s: input about %s%%; mixer and IOAudioLevelControl captured.\n' "$name" "$percent" >> "$SUMMARY"
}

snapshot basso 30
snapshot alto 70
printf '\nRestore input volume to the initial value you noted.\n'
MANUAL_CHANGED=0
ZIP="$WORK.zip"
capture "$WORK/ARCHIVIAZIONE.txt" 30 'ZIP creation' /usr/bin/ditto -c -k --norsrc --noextattr --noacl --noqtn --keepParent "$WORK" "$ZIP"
ordinary_file "$ZIP" && [ -s "$ZIP" ] || fail 'The ZIP is unavailable.'
printf '\nCollection complete: %s\nAttach this ZIP in the chat.\n' "$ZIP"
