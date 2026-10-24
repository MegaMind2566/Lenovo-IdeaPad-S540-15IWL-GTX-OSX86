#!/bin/bash
set -euo pipefail
umask 077
S540_BASE=$(cd "$(dirname "$0")" && pwd -P)
cd "$S540_BASE"
if [ "$(uname -s)" != Darwin ] || [ "$(uname -m)" != x86_64 ]; then
  printf 'Questo test richiede il macOS Intel del Lenovo S540.\n' >&2
  exit 1
fi
if [ "$EUID" -eq 0 ]; then
  printf 'Avvia il comando dal tuo utente, senza sudo davanti a bash.\n' >&2
  exit 1
fi
/usr/bin/shasum -a 256 -c SHA256SUMS
/usr/bin/codesign --verify --strict "$S540_BASE/bin/sd-init-trace"
"$S540_BASE/bin/sd-init-trace" --self-test
if ! S540_LOADED=$(/usr/bin/kmutil showloaded 2>/dev/null | /usr/bin/awk '$0 ~ /com\.apple\.driver\.BigSurSDXC/ { print }'); then
  printf 'STOP: impossibile verificare il driver SD caricato con kmutil.\n' >&2
  exit 1
fi
case "$S540_LOADED" in
  *'com.apple.driver.BigSurSDXC (1.9.0) D2EAAA60-AF10-360F-B645-1592B9B3A804 '*) ;;
  *) printf 'STOP: non risulta caricato il BigSurSDXC della prova verificata.\n' >&2; exit 1 ;;
esac
printf '\nAvvia dalla EFI esterna attuale e lascia inserita la SD da 8 GB.\n'
printf 'Segui le indicazioni: il programma chiedera di toglierla e poi reinserirla.\n'
printf 'La password serve per la traccia temporanea del driver.\n\n'
sudo -v
S540_REPORT=""
S540_FINISH() {
  S540_EXIT=$?
  trap - EXIT
  if [ -n "$S540_REPORT" ] && [ -d "$S540_REPORT" ]; then
    printf '%s\n' "$S540_EXIT" > "$S540_REPORT/exit-status.txt"
    if [ ! -s "$S540_REPORT/report.json" ]; then
      printf '{"result":"INCONCLUSIVE","reason":"Il programma non ha prodotto un report; vedere exit-status.txt."}\n' > "$S540_REPORT/report.json"
    fi
    if /usr/bin/ditto -c -k --norsrc --noextattr --noqtn --keepParent "$S540_REPORT" "$S540_REPORT.zip"; then
      printf '\nReport pronto: %s.zip\nAllega questo ZIP nella conversazione.\n' "$S540_REPORT"
    else
      printf '\nArchivio non creato; il report e in: %s\n' "$S540_REPORT" >&2
    fi
  fi
}
trap S540_FINISH EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
S540_REPORT=$(mktemp -d "$HOME/Desktop/S540-SD-Init.XXXXXX")
set +e
sudo "$S540_BASE/bin/sd-init-trace" --run > "$S540_REPORT/report.json"
S540_RESULT=$?
set -e
exit "$S540_RESULT"
