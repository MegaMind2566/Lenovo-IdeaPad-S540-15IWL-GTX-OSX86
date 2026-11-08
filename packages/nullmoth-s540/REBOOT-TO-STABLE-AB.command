#!/bin/bash
set -euo pipefail

args=$(nvram -p 2>/dev/null | awk -F '\t' '$1=="boot-args"{print $2}')
case " $args " in *" nvfb=1 "*) ;; *)
  printf 'Il boot corrente non risulta il profilo NullMoth; riavvio A/B rifiutato.\n' >&2
  exit 1
esac

printf 'Riavvio senza forzare la EFI esterna.\n'
printf 'Se compare il picker, scegli la EFI interna stabile/non-NVIDIA.\n'
sudo /sbin/shutdown -r now
