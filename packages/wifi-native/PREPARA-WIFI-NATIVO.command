#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"

finish() {
    local wifi_status=$?
    if [[ "$wifi_status" -ne 0 ]]; then
        echo "Preparazione non completata. Leggi il messaggio qui sopra."
    fi
    if [[ -t 0 ]]; then
        read -r -p "Premi Invio per chiudere. " wifi_close || true
    fi
    exit "$wifi_status"
}
trap finish EXIT

if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "Apri questo comando sul Lenovo da macOS."
    exit 1
fi
if ! command -v python3 >/dev/null 2>&1; then
    echo "Serve Python 3.10 o successivo per preparare la EFI."
    exit 1
fi

echo "Seleziona la cartella EFI che usi adesso."
echo "La copia di prova verrà creata sulla Scrivania."
wifi_source=$(/usr/bin/osascript -e 'POSIX path of (choose folder with prompt "Seleziona la cartella EFI attualmente funzionante")')
wifi_source="${wifi_source%/}"
if [[ ! -f "$wifi_source/OC/config.plist" && -f "$wifi_source/EFI/OC/config.plist" ]]; then
    wifi_source="$wifi_source/EFI"
fi
wifi_target="$HOME/Desktop/S540-WiFi-Nativo-TEST-$(date +%Y%m%d-%H%M%S)/EFI"
python3 tools/stage_wifi_native.py --efi "$wifi_source" --output "$wifi_target"
echo
echo "EFI di prova pronta: $wifi_target"
echo "Copia questa cartella EFI sulla partizione EFI della chiavetta di prova."
echo "Poi avvia il Lenovo dalla chiavetta e prova il menu Wi-Fi di macOS."
/usr/bin/open -R "$wifi_target"
