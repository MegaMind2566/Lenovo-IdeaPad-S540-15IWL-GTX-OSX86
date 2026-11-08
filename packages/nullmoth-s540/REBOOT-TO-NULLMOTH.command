#!/bin/bash
set -euo pipefail

VOLUME="/Volumes/240 GB"
CONFIG="$VOLUME/EFI/OC/config.plist"

[ -f "$CONFIG" ] || { printf 'EFI NullMoth non trovata: %s\n' "$CONFIG" >&2; exit 1; }
args=$(plutil -extract NVRAM.Add.7C436110-AB2A-4BBB-A880-FE41995C9F82.boot-args raw -o - "$CONFIG")
case " $args " in *" nvfb=1 "*" nvaccel=1 "*" gfxrst=4 "*) ;; *)
  printf 'Boot arguments NullMoth incompleti: riavvio rifiutato.\n' >&2
  exit 1
esac

printf 'Imposto la EFI esterna soltanto per il prossimo avvio.\n'
sudo /usr/sbin/bless --mount "$VOLUME" --setBoot --nextonly
printf 'Riavvio verso il test NullMoth. Lascia collegata l unita 240 GB.\n'
sudo /sbin/shutdown -r now
