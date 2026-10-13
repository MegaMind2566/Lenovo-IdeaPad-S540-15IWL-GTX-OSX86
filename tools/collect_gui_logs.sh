#!/bin/bash
# Read installed-system reports from Data; write only to the OpenCore HDD.
set -euo pipefail
umask 077

fail() { printf 'Raccolta non eseguita: %s\n' "$*" >&2; exit 1; }

if [ "$#" -gt 1 ]; then
    fail 'Indica al massimo il percorso del volume Data.'
fi
if [ "${1:-}" = '--help' ]; then
    printf 'Uso: bash collect_gui_logs.sh ["/Volumes/Machintosh SSD - Data"]\n'
    exit 0
fi
if [ "$(uname -s)" != 'Darwin' ]; then
    fail 'Esegui questo programma dal Terminale della Recovery macOS.'
fi

bundle_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
[ -d "$bundle_root/EFI/OC" ] || fail 'Estrai il pacchetto nella radice dell HDD di OpenCore, accanto a EFI.'

data_root=${1:-}
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
[ -d "$data_root/Library" ] && [ -d "$data_root/private/var" ] && [ -d "$data_root/Users" ] || fail 'Il percorso non contiene la struttura attesa del volume Data.'
case "$bundle_root/" in
    "$data_root/"*) fail 'La destinazione deve essere sull HDD di OpenCore, fuori dal volume Data.' ;;
esac
command -v ditto >/dev/null 2>&1 || fail 'ditto non disponibile in questa Recovery.'

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
    if [ -e "$data_root/private/var/db/.AppleSetupDone" ]; then
        printf 'Marcatore di configurazione iniziale: presente\n'
    else
        printf 'Marcatore di configurazione iniziale: assente\n'
    fi
} > "$summary"

copy_item() {
    local source=$1 label=$2
    if [ -e "$source" ]; then
        # Diagnostic text needs file contents, not macOS extended attributes.
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

if command -v diskutil >/dev/null 2>&1; then
    diskutil apfs list > "$work/VOLUMI-APFS.txt" 2>> "$errors" || true
fi
find "$work" -type f -print > "$work/INVENTARIO.txt"
{
    printf 'Elementi copiati: %s; assenti: %s; copie incomplete: %s\n' "$copied" "$missing" "$copy_errors"
    printf 'L assenza di un report non dimostra che il processo funzioni.\n'
} >> "$summary"

archive="$work.zip"
ditto -c -k "$work" "$archive"
printf '\nRaccolta salvata: %s\n' "$archive"
printf 'Allega quel file ZIP nella chat. La cartella di raccolta viene conservata.\n'
if [ "$copy_errors" -gt 0 ]; then
    printf 'Alcune copie sono incomplete: i dettagli sono nello ZIP.\n'
fi
