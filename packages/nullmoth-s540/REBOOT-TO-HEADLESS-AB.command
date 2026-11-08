#!/bin/bash
set -euo pipefail

VOLUME="/Volumes/240 GB"
CONFIG="$VOLUME/EFI/OC/config.plist"
[ -f "$CONFIG" ] || { printf 'EFI esterna non trovata.\n' >&2; exit 1; }
args=$(plutil -extract NVRAM.Add.7C436110-AB2A-4BBB-A880-FE41995C9F82.boot-args raw -o - "$CONFIG")
case " $args " in *" nvaccel=1 "*) ;; *) printf 'nvaccel=1 assente.\n' >&2; exit 1;; esac
case " $args " in *" nvfb=1 "*) printf 'nvfb=1 ancora presente.\n' >&2; exit 1;; *) ;; esac

printf 'Imposto il profilo NVIDIA headless per il prossimo avvio.\n'
sudo /usr/sbin/bless --mount "$VOLUME" --setBoot --nextonly
sudo /sbin/shutdown -r now
