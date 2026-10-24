#!/bin/bash
# S540 SD: raccolta passiva dopo il riavvio; non cambia EFI o driver.
set -uo pipefail
export LC_ALL=C
export PATH=/usr/bin:/bin:/usr/sbin:/sbin

[ "$(/usr/bin/uname -s)" = Darwin ] || { printf 'Eseguire su macOS.\n'; exit 1; }
S540_REPORT=$(/usr/bin/mktemp -d "$HOME/Desktop/S540-SD-esterno.XXXXXX") || exit 1
S540_PID=
cleanup() {
    if [ -n "$S540_PID" ]; then
        kill -TERM "$S540_PID" 2>/dev/null || true
        /bin/sleep 1
        kill -KILL "$S540_PID" 2>/dev/null || true
        wait "$S540_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

capture() {
    local name=$1 limit=$2 deadline rc
    shift 2
    "$@" > "$S540_REPORT/$name.txt" 2>&1 & S540_PID=$!
    deadline=$((SECONDS+limit))
    while kill -0 "$S540_PID" 2>/dev/null; do
        if [ "$SECONDS" -ge "$deadline" ]; then
            cleanup
            S540_PID=
            printf '%s: timeout, dati incompleti\n' "$name" >> "$S540_REPORT/comandi.txt"
            return 0
        fi
        /bin/sleep 1
    done
    rc=0; wait "$S540_PID" || rc=$?
    S540_PID=
    printf '%s: exit %s\n' "$name" "$rc" >> "$S540_REPORT/comandi.txt"
}

printf 'Raccolta passiva SD. Non occorrono password o altri riavvii.\n'
capture macos 5 /usr/bin/sw_vers
capture boot-args 5 /usr/sbin/sysctl -n kern.bootargs
capture driver-caricati 10 /usr/bin/kmutil showloaded
capture controller-sd 10 /usr/sbin/ioreg -r -c BgSurSDXC -l -w0
capture dischi 15 /usr/sbin/diskutil list
printf 'Il report non dichiara funzionante la SD: serve anche aprire un file gia presente sulla scheda.\n' > "$S540_REPORT/LEGGIMI.txt"
printf '\nReport: %s\n' "$S540_REPORT"
if /usr/bin/ditto --norsrc -c -k --keepParent "$S540_REPORT" "$S540_REPORT.zip"; then
    printf 'ZIP da allegare: %s.zip\n' "$S540_REPORT"
else
    printf 'ZIP non creato: conserva la cartella del report.\n'
    exit 1
fi
