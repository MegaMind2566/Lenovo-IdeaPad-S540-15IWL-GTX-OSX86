#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)"
ROOT="$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd -P)"
SETUP="$ROOT/_external/nullmoth-release-2.7.2/1401/1401.app/Contents/Resources/nullmoth-setup.sh"
PACKAGE="$ROOT/_external/nullmoth-release-2.7.2/nullmoth-nvidia-2.7.2-s540-no-nmxaudio.tar.gz"
PACKAGE_SHA="20c2d2cccb5b008021721252ca2598df7b0b87b8686d8fdff5cf690707c10a70"
CONFIG="/Volumes/240 GB/EFI/OC/config.plist"
TOOL="$ROOT/_external/nullmoth-release-2.7.2/1401/1401.app/Contents/Resources/NullMothSafe.efi"
APP="$ROOT/_external/nullmoth-release-2.7.2/1401/1401.app/Contents/MacOS/1401"
DRY_LOG="$ROOT/_captures/nullmoth-1401-dry-run-20261107.log"
LOG="$ROOT/_captures/nullmoth-1401-install-20261107.log"

for required in "$SETUP" "$PACKAGE" "$CONFIG" "$TOOL" "$APP" "$DRY_LOG"; do
  [ -e "$required" ] || { printf 'Manca: %s\n' "$required" >&2; exit 1; }
done

grep -q '^RESULT ok$' "$DRY_LOG" || {
  printf 'Il dry-run 1401 non risulta completato con RESULT ok.\n' >&2
  exit 1
}

actual_sha=$(shasum -a 256 "$PACKAGE" | awk '{print $1}')
[ "$actual_sha" = "$PACKAGE_SHA" ] || {
  printf 'Hash del pacchetto S540 non valido.\n' >&2
  exit 1
}

probe_index=""
index=0
while bundle=$(/usr/libexec/PlistBuddy -c "Print :Kernel:Add:$index:BundlePath" "$CONFIG" 2>/dev/null); do
  if [ "$bundle" = "S540NvidiaPCIProbe.kext" ]; then probe_index=$index; break; fi
  index=$((index + 1))
done
[ -n "$probe_index" ] || { printf 'Voce S540NvidiaPCIProbe non trovata.\n' >&2; exit 1; }
[ "$(/usr/libexec/PlistBuddy -c "Print :Kernel:Add:$probe_index:Enabled" "$CONFIG")" = false ] || {
  printf 'S540NvidiaPCIProbe e ancora abilitato: installazione rifiutata.\n' >&2
  exit 1
}

printf 'Installazione NullMoth S540: verra richiesta la password sudo.\n'
printf 'Il pacchetto non contiene NMXAudio e il probe e disabilitato.\n\n'

sudo /bin/bash "$SETUP" \
  --pkg "$PACKAGE" \
  --sha "$PACKAGE_SHA" \
  --config "$CONFIG" \
  --tool "$TOOL" \
  --app "$APP" 2>&1 | tee "$LOG"

printf '\nInstallazione terminata. Log: %s\n' "$LOG"
