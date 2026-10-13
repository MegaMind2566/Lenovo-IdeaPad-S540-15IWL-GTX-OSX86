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
    printf 'Raccolta non completata: %s\n' "$*" >&2
    if [ -n "$WORK" ]; then
        printf 'La cartella parziale resta qui: %s\n' "$WORK" >&2
    fi
    if [ "$MANUAL_CHANGED" -eq 1 ]; then
        printf 'Riporta manualmente il volume di ingresso al valore che avevi annotato.\n' >&2
    fi
    exit 1
}

stop_children() {
    if [ -n "$WATCH_PID" ]; then /bin/kill "$WATCH_PID" 2>/dev/null || true; fi
    if [ -n "$ACTIVE_PID" ]; then /bin/kill "$ACTIVE_PID" 2>/dev/null || true; fi
}
trap stop_children EXIT
trap 'fail "Operazione interrotta."' INT TERM

[ "$#" -eq 0 ] || fail 'Questo comando non richiede argomenti.'
[ "$(/usr/bin/uname -s)" = Darwin ] || fail 'Esegui dal desktop macOS.'
[ "$(/usr/bin/uname -m)" = x86_64 ] || fail 'Questo pacchetto richiede il portatile Intel.'
[ -d /System/Volumes/Data ] && [ -d /Users ] || fail 'Esegui dal desktop, non dalla Recovery.'
[ "$(/usr/bin/id -u)" -ne 0 ] || fail 'Esegui dal tuo account, senza sudo.'
[ -n "${HOME:-}" ] && [ -d "$HOME/Desktop" ] || fail 'La Scrivania non è disponibile.'

PACKAGE=$(cd -P "$(/usr/bin/dirname "${BASH_SOURCE[0]}")/.." && pwd) || fail 'Impossibile trovare il pacchetto.'
BIN="$PACKAGE/bin/hda_mixer_snapshot"
SUMS="$PACKAGE/SHA256SUMS"
DRIVER='/Library/Extensions/VoodooHDA.kext/Contents/MacOS/VoodooHDA'
DRIVER_SHA='932a7c9e46a65fdab7c8729f599c1094b568ae4fc7f17dad9818c83e833a0973'

ordinary_file() { [ -f "$1" ] && [ ! -L "$1" ]; }
hash() { /usr/bin/shasum -a 256 "$1" | /usr/bin/awk '{print $1}'; }
ordinary_file "$BIN" && [ -x "$BIN" ] || fail 'Il lettore verificato manca o non è eseguibile.'
ordinary_file "$SUMS" || fail 'Manca il manifesto SHA256 del lettore.'
EXPECTED=$(/usr/bin/awk 'NF == 2 && $2 == "bin/hda_mixer_snapshot" && length($1) == 64 && $1 !~ /[^0-9a-f]/ {print $1}' "$SUMS") || fail 'Impossibile leggere il manifesto.'
case "$EXPECTED" in ''|*[!0-9a-f]*) fail 'Manifesto SHA256 non valido.';; esac
[ "${#EXPECTED}" -eq 64 ] || fail 'Il manifesto deve contenere un solo hash.'
printf '%s  bin/hda_mixer_snapshot\n' "$EXPECTED" | /usr/bin/cmp -s - "$SUMS" || fail 'Il manifesto non ha il formato previsto.'
[ "$(hash "$BIN")" = "$EXPECTED" ] || fail 'Il lettore non coincide con il manifesto; non viene eseguito.'
ordinary_file "$DRIVER" || fail 'Il driver VoodooHDA installato non è disponibile.'
[ "$(hash "$DRIVER")" = "$DRIVER_SHA" ] || fail 'Il driver installato non è il binario VoodooHDA 3.6.8 verificato.'

WORK=$(/usr/bin/mktemp -d "$HOME/Desktop/DIAGNOSI-MICROFONO-XXXXXX") || fail 'Impossibile creare la raccolta.'
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
        fail "$label: tempo massimo di ${seconds}s superato."
    fi
    if [ "$rc" -ne 0 ]; then
        if [ "$label" = 'lettura mixer' ]; then
            printf 'Il lettore non ha completato l accesso al driver. Non viene richiesto sudo.\n' >&2
            [ ! -s "$ERRORS" ] || /bin/cat "$ERRORS" >&2
        fi
        fail "$label: comando terminato con codice $rc."
    fi
}

capture "$WORK/DRIVER-CARICATI.txt" 20 'verifica driver caricato' /usr/bin/kmutil showloaded
/usr/bin/grep -Eq 'org\.voodoo\.driver\.VoodooHDA[[:space:]]+\(3\.6\.8\)' "$WORK/DRIVER-CARICATI.txt" || fail 'VoodooHDA 3.6.8 non risulta caricato. Riavvia con la configurazione audio funzionante.'
# Keep only the relevant audio/Lilu entries, not a complete kext listing.
/usr/bin/grep -E 'AppleHDA|AppleALC|Lilu|VoodooHDA' "$WORK/DRIVER-CARICATI.txt" > "$WORK/DRIVER-AUDIO.txt" || fail 'Impossibile conservare il riepilogo dei driver audio.'
/bin/rm -f "$WORK/DRIVER-CARICATI.txt"
capture "$WORK/AUDIO.txt" 30 'rilevamento audio' /usr/sbin/system_profiler SPAudioDataType
capture "$WORK/CONTROLLI-INIZIALI.txt" 15 'controlli di ingresso iniziali' /usr/sbin/ioreg -r -c IOAudioLevelControl -l -w 0
{
    printf 'Diagnosi privata microfono VoodooHDA 3.6.8\n'
    printf 'Lettore SHA256: %s\nDriver SHA256: %s\n' "$EXPECTED" "$DRIVER_SHA"
    printf 'Due letture: volume di ingresso 30%% e 70%%, scelto manualmente.\n'
    printf 'Il comando non modifica EFI, NVRAM, SIP, driver o impostazioni audio.\n'
    printf 'Le letture mixer sono percentuali cached del canale sinistro, non dB.\n'
    printf 'I buffer iniziali sono già esistenti: non viene generato un nuovo grafico codec.\n'
    printf 'I buffer iniziali possono essere vuoti o non disponibili senza invalidare i mixer.\n'
    printf 'Non pubblicare questo ZIP nella repository.\n'
} > "$SUMMARY"

printf '\nApri Impostazioni di Sistema > Suono > Ingresso.\n'
printf 'Scollega le cuffie Bluetooth e seleziona il microfono interno.\n'
printf 'Annota il valore attuale del volume di ingresso, per ripristinarlo alla fine.\n'
printf 'Lascia invariato il volume di uscita durante entrambe le letture.\n'
printf 'Non serve registrare la voce: confrontiamo i controlli del driver.\n'

snapshot() {
    local name=$1 percent=$2 folder answer
    MANUAL_CHANGED=1
    printf '\nImposta il volume di ingresso a circa %s%%, poi premi INVIO.\n' "$percent"
    IFS= read -r answer || fail 'Non è arrivata la conferma del valore di ingresso.'
    folder="$WORK/$name"
    /bin/mkdir "$folder" || fail 'Impossibile creare la cartella della lettura.'
    # Recheck both executables before every probe execution.
    [ "$(hash "$BIN")" = "$EXPECTED" ] || fail 'Il lettore è cambiato durante la raccolta.'
    [ "$(hash "$DRIVER")" = "$DRIVER_SHA" ] || fail 'Il driver è cambiato durante la raccolta.'
    capture "$folder/LETTURA.txt" 20 'lettura mixer' "$BIN" --output-dir "$folder"
    ordinary_file "$folder/mixers.json" && [ -s "$folder/mixers.json" ] || fail 'La lettura non ha prodotto i dati mixer.'
    capture "$folder/CONTROLLI-AUDIO.txt" 15 'controlli audio' /usr/sbin/ioreg -r -c IOAudioLevelControl -l -w 0
    printf 'Lettura %s%% completata.\n' "$percent"
    printf 'Lettura %s: ingresso circa %s%%, mixer e IOAudioLevelControl acquisiti.\n' "$name" "$percent" >> "$SUMMARY"
}

snapshot basso 30
snapshot alto 70
printf '\nRiporta il volume di ingresso al valore iniziale che avevi annotato.\n'
MANUAL_CHANGED=0
ZIP="$WORK.zip"
capture "$WORK/ARCHIVIAZIONE.txt" 30 'creazione ZIP' /usr/bin/ditto -c -k --norsrc --noextattr --noacl --noqtn --keepParent "$WORK" "$ZIP"
ordinary_file "$ZIP" && [ -s "$ZIP" ] || fail 'Lo ZIP non è disponibile.'
printf '\nRaccolta completata: %s\nAllega questo ZIP nella chat.\n' "$ZIP"
