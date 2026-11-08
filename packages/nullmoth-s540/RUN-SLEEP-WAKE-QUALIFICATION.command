#!/bin/zsh

set -u

result_file="/tmp/s540-sleep-wake-qualification.txt"
done_file="/tmp/s540-sleep-wake-qualification.done"
rm -f "$result_file" "$done_file"

exec > >(tee "$result_file") 2>&1

echo "S540 NVIDIA: test Sleep/Wake completo"
echo "Inserisci la password amministratore quando richiesta."
sudo -v || exit 1

echo "PRE_TIME=$(date '+%Y-%m-%d %H:%M:%S %z')"
echo "PRE_WINDOWSERVER=$(pgrep -x WindowServer || true)"
echo "PRE_NV=$(ioreg -r -n NVAccel -lw0 2>/dev/null | sed -nE 's/.*\"Temperature\(C\)\"=([0-9]+).*/\1/p' | head -n 1)"
echo "PRE_TG0D=$(/Applications/Stats.app/Contents/Resources/smc list -t 2>/dev/null | awk '$1 == "[TG0D]" { print $2 }')"

echo "Programmo la riattivazione automatica fra 45 secondi e sospendo il sistema."
echo "Non toccare tastiera o trackpad: il Lenovo si riattivera da solo."
sudo pmset relative wake 45 || exit 1
pmset -g sched
sudo pmset sleepnow || exit 1

# Lascia tempo al ciclo firmware/macOS e alla ripresa dei servizi dopo il wake.
sleep 70

echo "POST_TIME=$(date '+%Y-%m-%d %H:%M:%S %z')"
echo "POST_WINDOWSERVER=$(pgrep -x WindowServer || true)"
echo "POST_KEXT=$(kmutil showloaded --list-only 2>/dev/null | /usr/bin/grep -E 'org\.s540\.S540Sensors' || true)"
echo "POST_NV=$(ioreg -r -n NVAccel -lw0 2>/dev/null | sed -nE 's/.*\"Temperature\(C\)\"=([0-9]+).*/\1/p' | head -n 1)"
echo "POST_TG0D=$(/Applications/Stats.app/Contents/Resources/smc list -t 2>/dev/null | awk '$1 == "[TG0D]" { print $2 }')"

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)"
S540_ROOT="$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd -P)"
cd "$S540_ROOT" || exit 1
./build/nullmoth-s540/metal_verify

echo "--- POWER LOG ---"
pmset -g log | /usr/bin/grep -Ei ' Sleep  | Wake  | DarkWake ' | tail -n 12 || true

touch "$done_file"
echo "TEST_COMPLETATO"
