#!/bin/bash
# Read installed-system reports from Data; write only to the OpenCore HDD.
set -euo pipefail
umask 077

fail() { printf 'Raccolta non eseguita: %s\n' "$*" >&2; exit 1; }

unified=0
intel=0
data_root=''
while [ "$#" -gt 0 ]; do
    case "$1" in
        --unified) unified=1 ;;
        --intel) intel=1 ;;
        --help)
            printf 'Uso: bash collect_gui_logs.sh [--unified] [--intel] ["/Volumes/Machintosh SSD - Data"]\n'
            printf '%s\n' '--unified include diagnostics e uuidtext del sistema installato.'
            printf '%s\n' '--intel include i file diretti Lilu/WhateverGreen e la configurazione della traccia.'
            exit 0 ;;
        --*) fail "Opzione sconosciuta: $1" ;;
        *)
            [ -z "$data_root" ] || fail 'Indica al massimo il percorso del volume Data.'
            [ -n "$1" ] || fail 'Il percorso Data non puo essere vuoto.'
            data_root=$1 ;;
    esac
    shift
done
if [ "$(uname -s)" != 'Darwin' ]; then
    fail 'Esegui questo programma dal Terminale della Recovery macOS.'
fi

bundle_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
[ -d "$bundle_root/EFI/OC" ] || fail 'Estrai il pacchetto nella radice dell HDD di OpenCore, accanto a EFI.'

if [ -z "$data_root" ]; then
    for candidate in '/Volumes/Machintosh SSD - Data' '/Volumes/Machintosh SSD - Dati'; do
        if [ -d "$candidate/Library" ] && [ -d "$candidate/private/var" ] && [ -d "$candidate/Users" ]; then
            [ -z "$data_root" ] || fail 'Piu volumi candidati: indica esplicitamente il percorso Data del Samsung.'
            data_root=$candidate
        fi
    done
fi
if [ -z "$data_root" ] || [ ! -d "$data_root" ]; then
    printf 'Volumi attualmente montati:\n' >&2
    ls -1 /Volumes >&2 || true
    fail 'Monta il volume Data del Samsung in Utility Disco. Se il nome e diverso, passalo come argomento.'
fi
data_root=$(cd "$data_root" && pwd -P)
case "$data_root" in
    /Volumes/*) ;;
    *) fail 'Seleziona il volume Data montato sotto /Volumes, non il sistema Recovery in esecuzione.' ;;
esac
[ -d "$data_root/Library" ] && [ -d "$data_root/private/var" ] && [ -d "$data_root/Users" ] || fail 'Il percorso non contiene la struttura attesa del volume Data.'
case "$bundle_root/" in
    "$data_root/"*) fail 'La destinazione deve essere sull HDD di OpenCore, fuori dal volume Data.' ;;
esac
command -v ditto >/dev/null 2>&1 || fail 'ditto non disponibile in questa Recovery.'

space_check='non richiesto'
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
            source_kb=$(du -sk "$source" | awk '{print $1}') || fail 'Impossibile stimare la dimensione dei log unificati.'
            case "$source_kb" in ''|*[!0-9]*) fail 'Dimensione dei log non valida.' ;; esac
            unified_kb=$((unified_kb + source_kb))
        fi
    done
    free_kb=$(LC_ALL=C df -Pk "$bundle_root" | awk 'END {print $4}') || fail 'Impossibile leggere lo spazio libero sull HDD.'
    case "$free_kb" in ''|*[!0-9]*) fail 'Spazio libero non valido.' ;; esac
    # Retain the raw copy and ZIP; reserve additional room for reports.
    needed_kb=$((unified_kb * 2 + 65536))
    [ "$free_kb" -ge "$needed_kb" ] || fail 'Spazio insufficiente sull HDD per conservare cartella e ZIP dei log.'
    printf 'Log unificati: circa %s MB; avvio della raccolta.\n' "$((unified_kb / 1024))"
        space_check='stima disponibile; spazio sufficiente al momento del controllo'
    else
        space_check="stima non disponibile; strumenti mancanti:$missing_space_tools"
        printf 'Stima dello spazio non disponibile (mancano:%s). Procedo con la copia dei log.\n' "$missing_space_tools"
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
    printf 'Raccolta offline dei report del sistema installato\n'
    printf 'Origine Data: %s\n' "$data_root"
    printf 'Destinazione: %s\n' "$work"
    printf 'Il programma legge Data e scrive soltanto questa raccolta sull HDD.\n'
    printf 'Non filtra i report per data: gli orologi dei tentativi possono differire.\n'
    printf 'Non esegue log show o sysdiagnose sul sistema Recovery.\n'
    printf 'Raccolta log unificati richiesta: %s\n' "$unified"
    printf 'Controllo dello spazio: %s\n' "$space_check"
    if [ -e "$data_root/private/var/db/.AppleSetupDone" ]; then
        printf 'Marcatore di configurazione iniziale: presente\n'
    else
        printf 'Marcatore di configurazione iniziale: assente\n'
    fi
} > "$summary"

copy_item() {
    local source=$1 label=$2
    if [ -e "$source" ]; then
        # Diagnostic data needs file contents, not macOS extended attributes.
        # FAT/exFAT destinations can reject those attributes despite copying data.
        if cp -RX "$source" "$work/$label" 2>> "$errors"; then
            printf 'Copiato: %s\n' "$label" >> "$summary"
            copied=$((copied + 1))
        else
            printf 'Copia incompleta: %s\n' "$label" >> "$summary"
            copy_errors=$((copy_errors + 1))
        fi
    else
        printf 'Assente: %s\n' "$label" >> "$summary"
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
printf 'Cartelle report utente trovate: %s\n' "$user_index" >> "$summary"
copy_item "$data_root/private/var/log/install.log" 'install.log'
copy_item "$data_root/private/var/log/system.log" 'system.log'

if [ "$intel" -eq 1 ]; then
    mkdir "$work/TracciaIntel"
    intel_found=0
    for trace in "$data_root"/private/var/log/Lilu_*.txt "$data_root"/private/var/log/AppleIntelFramebuffer_*; do
        copy_item "$trace" "TracciaIntel/${trace##*/}"
        intel_found=$((intel_found + 1))
    done
    printf 'File diretti Intel trovati: %s\n' "$intel_found" >> "$summary"
    if [ "$intel_found" -eq 0 ]; then
        printf 'Nessun file diretto Intel trovato; il riepilogo registra anche questa assenza.\n'
    fi
    copy_item "$bundle_root/EFI/OC/backup-traccia-intel" 'TracciaIntel/backup-traccia-intel'
    copy_item "$bundle_root/EFI/OC/config.plist" 'TracciaIntel/config-recovery.plist'
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
    printf 'Copia diagnostics dal volume Data del Samsung...\n'
    copy_item "$data_root/private/var/db/diagnostics" 'UnifiedLogs/diagnostics'
    printf 'Copia uuidtext dal volume Data del Samsung...\n'
    copy_item "$data_root/private/var/db/uuidtext" 'UnifiedLogs/uuidtext'
    if [ "$copied" -eq "$((copied_before + 2))" ] && [ -d "$work/UnifiedLogs/diagnostics" ] && [ -d "$work/UnifiedLogs/uuidtext" ]; then
        unified_complete=1
        printf 'Coppia log unificati: copiata senza errori segnalati\n' >> "$summary"
    else
        printf 'Coppia log unificati: incompleta o assente; verificare ERRORI-COPIA.txt\n' >> "$summary"
    fi
    printf 'diagnostics e uuidtext sono dati offline separati, non un archivio logarchive convertito.\n' >> "$summary"
fi

if command -v diskutil >/dev/null 2>&1; then
    diskutil apfs list > "$work/VOLUMI-APFS.txt" 2>> "$errors" || true
fi
find "$work" -type f -print > "$work/INVENTARIO.txt"
{
    printf 'Elementi copiati: %s; assenti: %s; copie incomplete: %s\n' "$copied" "$missing" "$copy_errors"
    printf 'L assenza di un report non dimostra che il processo funzioni.\n'
} >> "$summary"

archive="$work.zip"
printf 'Creazione dello ZIP...\n'
ditto -c -k "$work" "$archive"
printf '\nRaccolta salvata: %s\n' "$archive"
printf 'Allega quel file ZIP nella chat. La cartella di raccolta viene conservata.\n'
if [ "$copy_errors" -gt 0 ]; then
    printf 'Alcune copie sono incomplete: i dettagli sono nello ZIP.\n'
fi
if [ "$unified" -eq 1 ] && [ "$unified_complete" -eq 0 ]; then
    printf 'I log unificati sono incompleti o assenti. Allega comunque lo ZIP con il riepilogo.\n'
fi
