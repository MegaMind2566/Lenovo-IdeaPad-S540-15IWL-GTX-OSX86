#!/bin/bash
# Native macOS / Bash 3.2. Read diagnostics; write only a private report.
set -uo pipefail
umask 077
export LC_ALL=C

fail() { printf 'Raccolta non eseguita: %s\n' "$*" >&2; exit 1; }
[ "$#" -eq 0 ] || fail 'Questo comando non richiede argomenti.'
[ "$(/usr/bin/uname -s)" = Darwin ] || fail 'Esegui il comando dal desktop macOS Tahoe.'
case "$(/usr/bin/uname -r)" in 25.*) ;; *) fail 'Questa raccolta richiede macOS Tahoe (Darwin 25).';; esac
[ -d /System/Volumes/Data ] && [ -d /Users ] || fail 'Esegui dal desktop, non dalla Recovery.'
[ "$(/usr/bin/id -u)" -ne 0 ] || fail 'Esegui dal tuo account, senza anteporre sudo.'
[ -n "${HOME:-}" ] && [ -d "$HOME/Desktop" ] || fail 'La cartella Scrivania non è disponibile.'

WORK=$(/usr/bin/mktemp -d "$HOME/Desktop/DIAGNOSI-AVVIO-RETE-XXXXXX") || fail 'Impossibile creare la raccolta sulla Scrivania.'
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
trap 'printf "Raccolta interrotta. La cartella parziale resta sulla Scrivania.\n" >&2; exit 130' INT TERM

note_error() {
    printf '%s\n' "$*" >> "$ERRORS"
    if [ "$OPTIONAL_STEP" -eq 1 ]; then
        printf 'Lettura opzionale non disponibile: %s\n' "$*" >> "$SUMMARY"
    else
        PARTIAL=$((PARTIAL + 1))
        printf 'Incompleto: %s\n' "$*" >> "$SUMMARY"
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
        note_error "$label: tempo massimo di ${seconds}s superato."
        return 1
    fi
    if [ "$rc" -ne 0 ]; then
        note_error "$label: comando terminato con codice $rc."
        return 1
    fi
    printf 'Letto: %s\n' "$label" >> "$SUMMARY"
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
    printf 'Diagnosi avvio, Bluetooth e rete — desktop Tahoe\n'
    printf 'Raccolta privata. Può contenere indirizzi hardware e messaggi dei processi selezionati.\n'
    printf 'Non pubblicare questo ZIP nella repository.\n'
    printf 'Nessuna modifica a EFI, NVRAM, driver, impostazioni o archivio dei log.\n'
    printf 'Non copia EFI, config completo, credenziali Wi-Fi o Info.plist di itlwm.\n'
    printf 'I log riguardano soltanto i primi cinque minuti dell avvio corrente.\n'
    printf 'Eventuali messaggi non conservati dal sistema non possono essere recuperati.\n'
    printf 'Le letture correnti dei dispositivi sono successive all avvio.\n'
} > "$SUMMARY"

printf 'Raccolgo avvio, Bluetooth, USB, grafica e interfacce di rete...\n'
capture "$WORK/VERSIONE-MACOS.txt" 10 'versione macOS' /usr/bin/sw_vers || true
capture "$WORK/BOOT-TIME.txt" 10 'ora di avvio' /usr/sbin/sysctl kern.boottime || true
capture "$WORK/BOOT-ARGS.txt" 10 'argomenti di avvio attivi' /usr/sbin/sysctl -n kern.bootargs || true
capture "$WORK/BOOT-SESSION.txt" 10 'sessione di avvio' /usr/sbin/sysctl -n kern.bootsessionuuid || true

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
        printf 'Boot epoch: %s\nFine epoch: %s\n' "$boot_epoch" "$end_epoch"
        printf 'Da: %s\nA: %s\n' "$start_date" "$end_date"
        printf 'Durata disponibile: %ss (massimo 300s).\n' "$((end_epoch - boot_epoch))"
    } > "$WORK/FINESTRA-AVVIO.txt"
    predicate='process IN {"kernel", "WindowServer", "loginwindow", "bluetoothd", "BlueTool", "configd", "corebrightnessd", "diskarbitrationd"}'
    printf 'Per leggere i log di avvio può essere richiesta la password del tuo account.\n'
    if /usr/bin/sudo -v; then
        capture "$WORK/AVVIO-PRIMI-5-MINUTI.log" 60 'log del boot corrente' \
            /usr/bin/sudo -n /usr/bin/log show --style compact --color none --info --no-debug --no-pager \
            --start "$start_date" --end "$end_date" --predicate "$predicate" || true
    else
        note_error 'Autenticazione annullata o non disponibile: log di avvio non raccolti.'
    fi
else
    note_error 'Ora di avvio non valida: nessun log storico generico usato come sostituto.'
fi

capture "$WORK/DISPOSITIVI.txt" 45 'Bluetooth, USB e grafica' \
    /usr/sbin/system_profiler -detailLevel mini -timeout 30 SPBluetoothDataType SPUSBDataType SPDisplaysDataType || true
capture "$WORK/PORTE-RETE.txt" 15 'porte hardware della rete' /usr/sbin/networksetup -listallhardwareports || true
capture "$WORK/SERVIZI-RETE.txt" 15 'servizi della rete' /usr/sbin/networksetup -listallnetworkservices || true

capture "$WORK/.kexts-tmp" 30 'driver caricati' /usr/bin/kmutil showloaded || true
# Keep relevant rows only. No raw copy of all loaded drivers remains in the ZIP.
/usr/bin/grep -Ei 'Lilu|WhateverGreen|RestrictEvents|IntelBluetooth|IntelBTPatcher|BlueToolFixup|BrcmPatchRAM|itlwm|AirportItlwm|USBToolBox|UTBMap|IOUSBHostFamily|IOBluetooth|AppleIntel.*Graphics|AppleIntel.*Framebuffer|IntelAccelerator|VoodooHDA|AppleALC|VirtualSMC|SMCBatteryManager' \
    "$WORK/.kexts-tmp" > "$WORK/DRIVER-CARICATI.txt" || true
if [ ! -s "$WORK/DRIVER-CARICATI.txt" ]; then
    printf 'Nessuna riga pertinente restituita. Consultare ERRORI.txt.\n' >> "$WORK/DRIVER-CARICATI.txt"
fi
/bin/rm -f "$WORK/.kexts-tmp"

FRAMEBUFFER_INFO='/System/Library/Extensions/AppleIntelCFLGraphicsFramebuffer.kext/Contents/Info.plist'
if [ -f "$FRAMEBUFFER_INFO" ]; then
    capture "$WORK/VERSIONE-FRAMEBUFFER.txt" 10 'versione framebuffer CFL installato' \
        /usr/libexec/PlistBuddy -c 'Print :CFBundleVersion' "$FRAMEBUFFER_INFO" || true
else
    printf 'Info.plist del framebuffer CFL non presente nel percorso previsto.\n' > "$WORK/VERSIONE-FRAMEBUFFER.txt"
fi

for class in IntelBluetoothFirmware IOBluetoothHCIController AppleIntelFramebuffer IntelAccelerator; do
    capture "$WORK/IOREG-$class.txt" 15 "IORegistry $class" /usr/sbin/ioreg -r -c "$class" -d 1 -l || true
    if [ ! -s "$WORK/IOREG-$class.txt" ]; then
        printf 'La classe %s non compare in questa lettura.\n' "$class" >> "$WORK/IOREG-$class.txt"
    fi
done

capture "$WORK/.usb-tmp" 15 'stato firmware dei dispositivi USB' /usr/sbin/ioreg -p IOUSB -l -w 0 || true
/usr/bin/grep -B 8 -A 16 'FirmwareLoaded' "$WORK/.usb-tmp" > "$WORK/IOREG-USB-FIRMWARE.txt" || true
if [ ! -s "$WORK/IOREG-USB-FIRMWARE.txt" ]; then
    printf 'Nessuna proprietà FirmwareLoaded restituita nel piano IOUSB. Consultare ERRORI.txt.\n' >> "$WORK/IOREG-USB-FIRMWARE.txt"
fi
# Keep only the context of FirmwareLoaded, not a full USB IORegistry copy.
/bin/rm -f "$WORK/.usb-tmp"

for key in bluetoothExternalDongleFailed bluetoothInternalControllerInfo; do
    capture_optional "$WORK/NVRAM-$key.txt" 10 "lettura $key" /usr/sbin/nvram -x "$key" || true
    if [ ! -s "$WORK/NVRAM-$key.txt" ]; then
        printf 'Variabile assente oppure non leggibile. Nessuna modifica eseguita.\n' >> "$WORK/NVRAM-$key.txt"
    fi
done

# Read only named harmless fields, never the full config or Wi-Fi kext Info.plist.
CONFIG='/Volumes/240 GB/EFI/OC/config.plist'
SELECTED="$WORK/CONFIG-SELEZIONATO.txt"
if [ -f "$CONFIG" ] && [ ! -L "$CONFIG" ]; then
    {
        printf 'Campi selezionati dal config presente su 240 GB.\n'
        printf 'La presenza del file non dimostra che questo sia il config usato all avvio corrente.\n'
        printf 'Nessun PlatformInfo, NVRAM, commento o Info.plist di itlwm incluso.\n'
    } > "$SELECTED"
    if /usr/bin/plutil -lint "$CONFIG" >/dev/null 2>> "$ERRORS"; then
        i=0
        while bundle=$(/usr/libexec/PlistBuddy -c "Print :Kernel:Add:$i:BundlePath" "$CONFIG" 2>/dev/null); do
            printf '\nKernel/Add/%s BundlePath: %s\n' "$i" "$bundle" >> "$SELECTED"
            for key in Enabled MinKernel MaxKernel; do
                value=$(/usr/libexec/PlistBuddy -c "Print :Kernel:Add:$i:$key" "$CONFIG" 2>/dev/null) || value='(assente)'
                printf '%s: %s\n' "$key" "$value" >> "$SELECTED"
            done
            i=$((i + 1))
        done
        i=0
        while identifier=$(/usr/libexec/PlistBuddy -c "Print :Kernel:Block:$i:Identifier" "$CONFIG" 2>/dev/null); do
            printf '\nKernel/Block/%s Identifier: %s\n' "$i" "$identifier" >> "$SELECTED"
            for key in Enabled MinKernel MaxKernel Strategy; do
                value=$(/usr/libexec/PlistBuddy -c "Print :Kernel:Block:$i:$key" "$CONFIG" 2>/dev/null) || value='(assente)'
                printf '%s: %s\n' "$key" "$value" >> "$SELECTED"
            done
            i=$((i + 1))
        done
        gpu='DeviceProperties.Add.PciRoot(0x0)/Pci(0x2,0x0)'
        for key in AAPL,ig-platform-id device-id framebuffer-patch-enable framebuffer-stolenmem framebuffer-fbmem; do
            printf '\nIGPU/%s (XML con tipo):\n' "$key" >> "$SELECTED"
            if ! /usr/bin/plutil -extract "$gpu.$key" xml1 -o - "$CONFIG" >> "$SELECTED" 2>/dev/null; then
                printf '(assente)\n' >> "$SELECTED"
            fi
        done
    else
        note_error 'Il config presente su 240 GB non supera plutil -lint; campi non raccolti.'
    fi
else
    printf 'Config su 240 GB non disponibile; nessun volume montato o modificato.\n' > "$SELECTED"
fi

printf 'Controlli incompleti: %s\n' "$PARTIAL" >> "$SUMMARY"
ARCHIVE="$WORK.zip"
[ ! -e "$ARCHIVE" ] || fail "Esiste già $ARCHIVE; la raccolta non lo sovrascrive."
printf 'Creo lo ZIP sulla Scrivania...\n'
if ! capture "$WORK/CREAZIONE-ZIP.txt" 45 'creazione ZIP' \
    /usr/bin/ditto -c -k --norsrc --noextattr --noacl --noqtn --keepParent "$WORK" "$ARCHIVE"; then
    printf '\nZIP non completato. Conserva la cartella: %s\n' "$WORK" >&2
    exit 1
fi
[ -s "$ARCHIVE" ] || fail "ZIP vuoto o assente. Conserva la cartella $WORK."
printf '\nRaccolta salvata: %s\n' "$ARCHIVE"
printf 'Allega questo ZIP nella chat. La cartella privata viene conservata.\n'
if [ "$PARTIAL" -gt 0 ]; then
    printf 'Alcuni controlli sono incompleti: i dettagli sono in ERRORI.txt.\n'
fi
