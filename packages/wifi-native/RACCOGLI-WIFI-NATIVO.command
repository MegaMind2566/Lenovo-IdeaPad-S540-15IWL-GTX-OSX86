#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"

finish() {
    local wifi_status=$?
    if [[ "$wifi_status" -ne 0 ]]; then
        echo "Report non completato. Leggi il messaggio qui sopra."
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
    echo "Serve Python 3.10 o successivo per raccogliere il report."
    exit 1
fi

wifi_report="$HOME/Desktop/S540-wifi-native-report-$(date +%Y%m%d-%H%M%S).json"
python3 tools/collect_wifi_native.py --output "$wifi_report"
echo
echo "Report pronto: $wifi_report"
echo "Invia il file JSON insieme all'esito delle prove sul menu Wi-Fi."
/usr/bin/open -R "$wifi_report"
