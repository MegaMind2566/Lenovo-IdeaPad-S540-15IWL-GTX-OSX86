#!/bin/bash
set -euo pipefail

usage() {
  printf 'Uso: %s /percorso/assoluto/pkgroot [cartella-output]\n' "$0" >&2
  exit 2
}

[ "$#" -ge 1 ] && [ "$#" -le 2 ] || usage
SOURCE=$1
[ -d "$SOURCE" ] || { printf 'pkgroot non trovata: %s\n' "$SOURCE" >&2; exit 1; }
[ "${SOURCE#/}" != "$SOURCE" ] || { printf 'Usare un percorso assoluto per pkgroot.\n' >&2; exit 2; }

if [ "$#" -eq 2 ]; then
  DEST=$2
else
  DEST="$(dirname "$SOURCE")/S540-NullMoth-2.7.2-staged"
fi

[ "${DEST#/}" != "$DEST" ] || { printf 'Usare un percorso assoluto per l’output.\n' >&2; exit 2; }
[ "$SOURCE" != "$DEST" ] || { printf 'Output e input devono essere directory diverse.\n' >&2; exit 2; }
[ ! -e "$DEST" ] || { printf 'La cartella output esiste già: %s\n' "$DEST" >&2; exit 1; }

mkdir -p "$DEST"
ditto "$SOURCE" "$DEST"

AUDIO="$DEST/Library/Extensions/NMXAudio.kext"
if [ -e "$AUDIO" ]; then
  rm -rf "$AUDIO"
  if [ -f "$DEST/SHA256SUMS" ]; then
    tmp="$DEST/SHA256SUMS.s540.tmp"
    grep -v 'Library/Extensions/NMXAudio\.kext/' "$DEST/SHA256SUMS" > "$tmp"
    mv "$tmp" "$DEST/SHA256SUMS"
  fi
  if [ -f "$DEST/MANIFEST.txt" ]; then
    tmp="$DEST/MANIFEST.txt.s540.tmp"
    grep -v '^Library/Extensions/NMXAudio\.kext/' "$DEST/MANIFEST.txt" > "$tmp"
    mv "$tmp" "$DEST/MANIFEST.txt"
  fi
  printf 'Rimosso dalla copia di staging: Library/Extensions/NMXAudio.kext\n'
else
  printf 'NMXAudio non presente nel pacchetto: nessuna rimozione necessaria\n'
fi

[ -x "$DEST/install.sh" ] || chmod 755 "$DEST/install.sh"
[ ! -e "$DEST/Library/Extensions/NMXAudio.kext" ] || {
  printf 'ERRORE: NMXAudio è ancora presente nella copia di staging.\n' >&2
  exit 1
}

printf '\nStaging pronto: %s\n' "$DEST"
printf 'Controllo successivo: shasum -a 256 -c SHA256SUMS (se presente)\n'
printf 'Installazione successiva, solo dopo revisione: sudo ./install.sh\n'
printf 'Questo script non ha installato kext, modificato EFI o ricostruito la AuxKC.\n'
