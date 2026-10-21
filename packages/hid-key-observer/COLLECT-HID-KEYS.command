#!/bin/bash
set -eu
umask 077

S540_PACKAGE=$(CDPATH= cd -- "$(dirname "$0")" && pwd -P)
S540_PROBE="$S540_PACKAGE/bin/hid-key-probe"

if [ "$(id -u)" -eq 0 ]; then
    printf '%s\n' 'Esegui dal tuo utente macOS, senza sudo.' >&2
    exit 77
fi
if [ ! -f "$S540_PACKAGE/SHA256SUMS" ] || [ ! -f "$S540_PROBE" ]; then
    printf '%s\n' 'Pacchetto incompleto: servono il binario compilato e SHA256SUMS.' >&2
    exit 66
fi
(
    cd "$S540_PACKAGE"
    /usr/bin/shasum -a 256 -c SHA256SUMS
)
/usr/bin/file "$S540_PROBE" | /usr/bin/grep -q 'Mach-O.*x86_64' || {
    printf '%s\n' 'Binario Mach-O Intel x86_64 non riconosciuto.' >&2
    exit 65
}
/usr/bin/codesign --verify --strict "$S540_PROBE"

S540_REPORT=$(mktemp -d "$HOME/Desktop/S540-HID-Keys.XXXXXX")
S540_STATUS=0
"$S540_PROBE" --output "$S540_REPORT/report.json" || S540_STATUS=$?
if [ -f "$S540_REPORT/report.json" ]; then
    /usr/bin/ditto -c -k --norsrc --noextattr --noacl --keepParent "$S540_REPORT" "$S540_REPORT.zip"
    printf '\nReport privato da allegare: %s.zip\n' "$S540_REPORT"
fi
if [ "$S540_STATUS" -eq 77 ]; then
    printf '%s\n' 'Consenti Monitoraggio input alla voce indicata da macOS, chiudi e riapri Terminale e riesegui questo comando.'
elif [ "$S540_STATUS" -ne 0 ]; then
    printf '%s\n' 'Raccolta inconclusiva: non ripetere i tasti e non cambiare mappature. Allega il report disponibile.'
fi
exit "$S540_STATUS"
