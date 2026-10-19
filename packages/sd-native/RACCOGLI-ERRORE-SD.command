#!/bin/bash
# Read-only SD initialization capture. No EFI, NVRAM, sysctl or disk mutation.
set -u
umask 077

desktop_dir="$HOME/Desktop"
if [ ! -d "$desktop_dir" ]; then
    echo "Cartella Scrivania non trovata."
    exit 1
fi
report_dir=$(/usr/bin/mktemp -d "$desktop_dir/S540-SD-XXXXXX") || exit 1
stream_pid=""
predicate='senderImagePath CONTAINS[c] "AppleSDXC" OR (process == "kernel" AND (eventMessage CONTAINS[c] "SDXC" OR eventMessage CONTAINS[c] "SDHCI" OR eventMessage CONTAINS[c] "O2Micro"))'

# Each shell below owns exactly one background job. Address that job, never a
# possibly recycled numeric PID. Capture subshells have their own job table.
job_active() {
    [ -n "$(jobs -pr 2>/dev/null)$(jobs -ps 2>/dev/null)" ]
}

finish_job() {
    local owned_pid="$1"
    local attempt
    if job_active; then
        kill -TERM %1 2>/dev/null || true
        kill -CONT %1 2>/dev/null || true
        for attempt in 1 2; do
            job_active || break
            /bin/sleep 1
        done
        if job_active; then
            kill -KILL %1 2>/dev/null || true
            for attempt in 1 2; do
                job_active || break
                /bin/sleep 1
            done
        fi
    fi
    if job_active; then
        echo "Arresto del comando non confermato entro il limite." >&2
        return 125
    fi
    wait "$owned_pid" 2>/dev/null
}

run_bounded() (
    local limit="$1"
    shift
    local elapsed=0 owned_pid result
    "$@" &
    owned_pid=$!
    trap 'finish_job "$owned_pid" >/dev/null 2>&1 || true; exit 130' INT
    trap 'finish_job "$owned_pid" >/dev/null 2>&1 || true; exit 143' TERM
    while job_active; do
        if [ "$elapsed" -ge "$limit" ]; then
            printf 'Tempo massimo superato: %s secondi.\n' "$limit" >&2
            finish_job "$owned_pid" || true
            exit 124
        fi
        /bin/sleep 1
        elapsed=$((elapsed + 1))
    done
    wait "$owned_pid"
    result=$?
    exit "$result"
)

stop_stream() {
    local result
    if [ -n "$stream_pid" ]; then
        finish_job "$stream_pid" 2>> "$report_dir/sd-live.stderr"
        result=$?
        printf 'sd-live.log\t%s\n' "$result" >> "$report_dir/comandi.tsv"
        stream_pid=""
    fi
}
trap stop_stream EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

capture() {
    local filename="$1"
    local limit="$2"
    shift 2
    run_bounded "$limit" "$@" > "$report_dir/$filename" 2> "$report_dir/$filename.stderr"
    local result=$?
    printf '%s\t%s\n' "$filename" "$result" >> "$report_dir/comandi.tsv"
    return 0
}

echo "Raccolta dell'errore del lettore SD."
echo "Rimuovi la scheda SD e premi Invio."
IFS= read -r risposta || exit 1

capture prima-ioreg.txt 20 /usr/sbin/ioreg -r -c AppleSDXC -l -w 0
capture macos.txt 15 /usr/bin/sw_vers -productVersion
capture kernel.txt 15 /usr/bin/uname -r
capture inizio-utc.txt 15 /bin/date -u '+%Y-%m-%dT%H:%M:%SZ'

/usr/bin/log stream --style compact --level debug --predicate "$predicate" \
    > "$report_dir/sd-live.log" 2> "$report_dir/sd-live.stderr" &
stream_pid=$!

echo "Ora inserisci la scheda SD e premi Invio."
IFS= read -r risposta || exit 1
echo "Attendo 8 secondi per registrare il tentativo di lettura..."
/bin/sleep 8

capture dopo-ioreg.txt 20 /usr/sbin/ioreg -r -c AppleSDXC -l -w 0
capture lettore.spx 20 /usr/sbin/system_profiler SPCardReaderDataType -xml -detailLevel full
capture dischi.plist 20 /usr/sbin/diskutil list -plist
capture debug-SDXC.txt 15 /usr/sbin/sysctl debug.SDXC
capture AppleSDXC-Info.plist 15 /bin/cat /System/Library/Extensions/AppleSDXC.kext/Contents/Info.plist
capture sd-recente.log 20 /usr/bin/log show --last 3m --style compact --info --debug --predicate "$predicate"
capture fine-utc.txt 15 /bin/date -u '+%Y-%m-%dT%H:%M:%SZ'
stop_stream

/bin/cat > "$report_dir/LEGGIMI.txt" <<'TEXT'
Raccolta mirata SD: stato prima/dopo inserimento, log filtrati, elenco dischi
e Info.plist del driver AppleSDXC installato. Ogni comando ha un codice di uscita
in comandi.tsv. Log vuoti possono indicare che il driver non ha emesso messaggi
disponibili: questa raccolta non abilita nuovi flag di debug del driver.
I lettori hanno limiti di 15 o 20 secondi, esclusa una breve fase di arresto.
Codice 124: tempo superato; 125: arresto non confermato. Per sd-live.log,
143 indica il normale arresto richiesto; 137 indica un arresto forzato.
debug.SDXC viene soltanto letto; nessuna variabile viene modificata.
La cartella puo contenere identificativi della SD e dei volumi: tenerla privata.
TEXT

archive_path="$report_dir.zip"
if /usr/bin/ditto -c -k --keepParent "$report_dir" "$archive_path"; then
    echo ""
    echo "Raccolta completata. Allegami il file ZIP:"
    echo "$archive_path"
    /usr/bin/open -R "$archive_path" 2>/dev/null || true
else
    echo "Creazione ZIP non riuscita. I dati sono qui: $report_dir"
    exit 1
fi
echo "Premi Invio per chiudere."
IFS= read -r risposta || true
