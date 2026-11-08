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
LOG="$ROOT/_captures/nullmoth-1401-dry-run-20261107.log"

for required in "$SETUP" "$PACKAGE" "$CONFIG" "$TOOL" "$APP"; do
  [ -e "$required" ] || { printf 'Manca: %s\n' "$required" >&2; exit 1; }
done

printf 'NullMoth 1401 dry-run: nessun file verra installato.\n'
printf 'Inserisci la password soltanto nel prompt sudo.\n\n'

sudo /bin/bash "$SETUP" \
  --pkg "$PACKAGE" \
  --sha "$PACKAGE_SHA" \
  --config "$CONFIG" \
  --tool "$TOOL" \
  --app "$APP" \
  --dry 2>&1 | tee "$LOG"

printf '\nDry-run terminato. Log: %s\n' "$LOG"
