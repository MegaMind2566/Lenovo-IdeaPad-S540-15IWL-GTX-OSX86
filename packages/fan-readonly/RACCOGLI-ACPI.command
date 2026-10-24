#!/bin/bash
# Export only DSDT/SSDT data already published in IORegistry; no EC calls.
set -euo pipefail
export PATH=/usr/bin:/bin:/usr/sbin:/sbin
export LC_ALL=C
[ "$(uname -s)" = Darwin ] || { printf 'Eseguire su macOS.\n'; exit 1; }
S540_REPORT=$(mktemp -d "$HOME/Desktop/S540-Ventole-ACPI.XXXXXX")
S540_RAW=$(mktemp "${TMPDIR:-/tmp}/S540-ACPI-raw.XXXXXX")
trap 'rm -f "$S540_RAW"' EXIT
printf 'Raccolta passiva delle tabelle firmware gia disponibili in macOS.\n'
printf 'Nessuna lettura EC, modifica EFI, installazione driver o regolazione ventole.\n'
if ioreg -a -r -c AppleACPIPlatformExpert -d 1 > "$S540_RAW" 2> "$S540_REPORT/comandi.txt"; then
  if plutil -extract '0.ACPI Tables.DSDT' xml1 -o "$S540_REPORT/DSDT.plist" "$S540_RAW" 2>> "$S540_REPORT/comandi.txt"; then
    printf 'DSDT=esportato\n' > "$S540_REPORT/stato.txt"
  else
    rm -f "$S540_REPORT/DSDT.plist"
    printf 'DSDT=non_esposto_da_IORegistry\nRISULTATO=inconcludente\n' > "$S540_REPORT/stato.txt"
  fi
  S540_COUNT=0
  for S540_TABLE in SSDT SSDT-{0..31}; do
    if plutil -extract "0.ACPI Tables.$S540_TABLE" xml1 -o "$S540_REPORT/$S540_TABLE.plist" "$S540_RAW" 2>/dev/null; then
      S540_COUNT=$((S540_COUNT+1))
    else
      rm -f "$S540_REPORT/$S540_TABLE.plist"
    fi
  done
  printf 'SSDT_esportate=%s\n' "$S540_COUNT" >> "$S540_REPORT/stato.txt"
else
  printf 'IORegistry=errore\nRISULTATO=inconcludente\n' > "$S540_REPORT/stato.txt"
fi
printf 'Solo DSDT e SSDT sono conservate. Le altre proprieta IORegistry e le altre tabelle, incluso MSDM, non sono incluse.\n' > "$S540_REPORT/LEGGIMI.txt"
rm -f "$S540_RAW"
trap - EXIT
ditto --norsrc --noextattr --noacl -c -k --keepParent "$S540_REPORT" "$S540_REPORT.zip"
printf '\nAllega questo ZIP: %s.zip\n' "$S540_REPORT"
