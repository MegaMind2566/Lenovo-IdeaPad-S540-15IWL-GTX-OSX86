#!/bin/bash
# The unchanged native failsafe is the only owner of LogScanCodes writes.
set -eu
umask 077
export PATH=/usr/bin:/bin:/usr/sbin:/sbin
export LC_ALL=C

BASE=$(cd "$(dirname "$0")" && pwd -P)
PROBE="$BASE/bin/function-key-scancodes"
PARSER="$BASE/parse-trace.js"
TMP_WORK=''
REPORT_DIR=''
TTY_SAVED=''
TTY_CAPTURE_ACTIVE=0
LOGGER_PID=''
FAILSAFE_PID=''
CONTROL_OPEN=0
STATUS_OPEN=0
RESTORED=0
FINISHED=0
REASON=interrupted
PREFIX=''

alive() { jobs -pr | /usr/bin/grep -qx -- "$1"; }

save_message() {
    printf '%s\n' "$MESSAGE" >> "$TMP_WORK/protocol.jsonl"
}

field() {
    printf '%s\n' "$MESSAGE" | /usr/bin/plutil -extract "$1" raw -o - - 3>&- 4>&- 2>/dev/null
}

receive() {
    MESSAGE=''
    IFS= read -r -t "$1" MESSAGE <&4 || return 1
    save_message
}

zero_now() {
    /usr/sbin/ioreg -r -c ApplePS2Keyboard -l -w0 > "$TMP_WORK/after.ioreg" 3>&- 4>&- || return 1
    /usr/bin/awk '/^[ \t]*"LogScanCodes" = 0[ \t]*$/ {n++} END {exit(n != 1)}' "$TMP_WORK/after.ioreg" 3>&- 4>&-
}

stop_helper() {
    if [ "$CONTROL_OPEN" -eq 1 ]; then
        exec 3>&-
        CONTROL_OPEN=0
    fi
    if [ -n "$FAILSAFE_PID" ]; then
        # EOF cancels a live window. Read the explicit final restoration result.
        if [ "$STATUS_OPEN" -eq 1 ]; then
            for ATTEMPT in 1 2 3 4; do
                receive 4 || break
                if [ "$(field state || true)" = failsafe-restored ] && [ "$(field logging_restored || true)" = true ]; then
                    RESTORED=1
                    break
                fi
            done
        fi
        if alive "$FAILSAFE_PID"; then
            /bin/sleep 0.2 3>&- 4>&-
        fi
        if alive "$FAILSAFE_PID"; then
            # TERM is handled by the unchanged helper and also restores logging.
            /usr/bin/sudo -n /bin/kill -TERM "$FAILSAFE_PID" 3>&- 4>&- >/dev/null 2>&1 || true
            /bin/sleep 0.3 3>&- 4>&-
        fi
        if ! alive "$FAILSAFE_PID"; then
            if ! wait "$FAILSAFE_PID"; then RESTORED=0; fi
        else
            RESTORED=0
        fi
        FAILSAFE_PID=''
    fi
    if [ "$STATUS_OPEN" -eq 1 ]; then
        exec 4>&-
        STATUS_OPEN=0
    fi
    if [ "$RESTORED" -eq 1 ] && ! zero_now; then RESTORED=0; fi
}

stop_logger() {
    if [ -n "$LOGGER_PID" ]; then
        /usr/bin/sudo -n /bin/kill -TERM "$LOGGER_PID" 3>&- 4>&- >/dev/null 2>&1 || true
        for ATTEMPT in 1 2 3 4 5 6 7 8 9 10; do
            alive "$LOGGER_PID" || break
            /bin/sleep 0.1 3>&- 4>&-
        done
        if alive "$LOGGER_PID"; then
            /usr/bin/sudo -n /bin/kill -KILL "$LOGGER_PID" 3>&- 4>&- >/dev/null 2>&1 || true
        fi
        wait "$LOGGER_PID" 2>/dev/null || true
        LOGGER_PID=''
    fi
}

restore_terminal() {
    if [ -n "$TTY_SAVED" ]; then
        # In noncanonical mode min=0/time=0, dd returns as soon as input is drained.
        if [ "$TTY_CAPTURE_ACTIVE" -eq 1 ]; then
            /bin/dd if=/dev/tty of=/dev/null bs=256 count=64 2>/dev/null || true
        fi
        /bin/stty "$TTY_SAVED" </dev/tty || true
        TTY_SAVED=''
        TTY_CAPTURE_ACTIVE=0
    fi
}

save_report() {
    [ -n "$REPORT_DIR" ] || return 0
    if [ ! -f "$REPORT_DIR/report.json" ]; then
        /usr/bin/osascript -l JavaScript "$PARSER" report "$TMP_WORK/trace.ndjson" "$TMP_WORK/protocol.jsonl" "$PREFIX" "$REPORT_DIR/report.json" "$REASON" > /dev/null 2> "$TMP_WORK/report.stderr" ||
            printf '{"schema":1,"result":"INCONCLUSIVE","reason":"report_generation_failed","logging_restored":%s}\n' "$([ "$RESTORED" -eq 1 ] && printf true || printf false)" > "$REPORT_DIR/report.json"
    fi
    printf 'S540 PS2 trace. Session reason: %s. Logging restoration verified: %s.\n' "$REASON" "$RESTORED" > "$REPORT_DIR/STATUS.txt"
    for ERROR_FILE in log.stderr failsafe.stderr parser.stderr report.stderr; do
        if [ -s "$TMP_WORK/$ERROR_FILE" ]; then
            printf '\n--- %s (maximum 8192 bytes) ---\n' "$ERROR_FILE" >> "$REPORT_DIR/diagnostics.txt"
            /bin/dd if="$TMP_WORK/$ERROR_FILE" bs=8192 count=1 >> "$REPORT_DIR/diagnostics.txt" 2>/dev/null
        fi
    done
    (cd "$(dirname "$REPORT_DIR")" && /usr/bin/zip -q -r "$REPORT_DIR.zip" "$(basename "$REPORT_DIR")") || return 1
    printf '\nAllega questo ZIP: %s.zip\n' "$REPORT_DIR"
}

cleanup() {
    CODE=$?
    trap '' INT TERM HUP QUIT
    trap - EXIT
    set +e
    stop_helper
    stop_logger
    restore_terminal
    if [ "$FINISHED" -eq 0 ] && [ -n "$TMP_WORK" ]; then
        if [ "$RESTORED" -eq 1 ]; then
            printf '\nProva interrotta; logging della tastiera ripristinato a 0.\n'
        elif [ -n "$REPORT_DIR" ] && [ -f "$TMP_WORK/protocol.jsonl" ] && [ -s "$TMP_WORK/protocol.jsonl" ]; then
            printf '\nATTENZIONE: ripristino non verificato. Non ripetere la prova; comunicami questo messaggio.\n'
        fi
        save_report || printf '\nImpossibile creare lo ZIP. Cartella report: %s\n' "$REPORT_DIR"
    fi
    if [ -n "$TMP_WORK" ]; then /bin/rm -rf -- "$TMP_WORK"; fi
    exit "$CODE"
}

fail() { [ "$REASON" != interrupted ] || REASON=session_error; printf '\nSTOP: %s\n' "$1" >&2; exit 1; }
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP
trap 'exit 131' QUIT

[ "$(/usr/bin/uname -s)" = Darwin ] && [ "$(/usr/bin/uname -m)" = x86_64 ] || fail 'Questa prova richiede macOS Intel.'
[ "$(/usr/bin/id -u)" != 0 ] || fail 'Avvia con bash dal tuo utente, senza sudo davanti al comando.'
[ -t 0 ] && [ -t 1 ] || fail 'Avvia il comando nel Terminale.'
[ -d "$HOME/Desktop" ] || fail 'Cartella Desktop non disponibile.'
cd "$BASE"
/usr/bin/shasum -a 256 -c SHA256SUMS || fail 'Pacchetto incompleto o modificato: estrai di nuovo lo ZIP.'
[ -x "$PROBE" ] || fail 'Programma di protezione non eseguibile: estrai di nuovo lo ZIP.'
/usr/bin/codesign --verify --strict "$PROBE" || fail 'Firma del programma di protezione non valida.'
"$PROBE" --self-test || fail 'Controllo iniziale del programma fallito.'
/usr/bin/osascript -l JavaScript "$PARSER" self-test >/dev/null || fail 'Controllo iniziale del parser fallito.'
printf 'Controlli iniziali superati.\n'

TMP_WORK=$(/usr/bin/mktemp -d "${TMPDIR:-/tmp}/S540-PS2-private.XXXXXX")
: > "$TMP_WORK/protocol.jsonl"
: > "$TMP_WORK/trace.ndjson"
/usr/sbin/ioreg -r -c ApplePS2Keyboard -l -w0 > "$TMP_WORK/before.ioreg"
PREFIX=$(/usr/bin/awk '/\+-o / && /<class ApplePS2Keyboard,/ {sub(/^.*\+-o /, ""); sub(/[ \t]+<class.*$/, ""); print}' "$TMP_WORK/before.ioreg")
printf '%s\n' "$PREFIX" | /usr/bin/grep -Eq '^[A-Za-z0-9_. -]{1,80}$' || fail 'Nome del servizio PS/2 non riconosciuto.'
[ "$(printf '%s\n' "$PREFIX" | /usr/bin/wc -l | /usr/bin/tr -d ' ')" = 1 ] || fail 'Trovati piu servizi PS/2.'
zero_now || fail 'LogScanCodes non e impostato a 0: nessuna prova eseguita.'

printf '\nQuesta prova osserva sei combinazioni, senza installare driver.\n'
printf 'Il logging si attiva soltanto nelle finestre VIA di 3 secondi.\n'
printf 'Durante VIA premi solo il tasto indicato, una volta, poi rilascialo.\n'
printf 'Non digitare testo o password durante le prove. Ctrl+C interrompe.\n'
printf '\nLa password amministratore viene richiesta adesso, prima delle prove.\n'
/usr/bin/sudo -v || fail 'Autenticazione annullata.'
printf '\nPremi Invio UNA volta per iniziare; poi non servira altro Invio. '
IFS= read -r INITIAL_LINE || fail 'Input terminato prima della prova.'
TTY_SAVED=$(/bin/stty -g </dev/tty)
# Keep Ctrl+C (ISIG) but prevent terminal suspend/quit from stopping the watchdog.
/bin/stty -echo -icanon min 0 time 0 quit undef susp undef dsusp undef </dev/tty || fail 'Impossibile preparare il Terminale.'
TTY_CAPTURE_ACTIVE=1
/bin/dd if=/dev/tty of=/dev/null bs=256 count=64 2>/dev/null || true
REPORT_DIR=$(/usr/bin/mktemp -d "$HOME/Desktop/S540-PS2-Trace.XXXXXX")

# Only this filtered stream is transiently retained; the shareable ZIP contains numeric records only.
/usr/bin/sudo -n /usr/bin/log stream --style ndjson --level debug --predicate 'eventMessage CONTAINS "sending key"' > "$TMP_WORK/trace.ndjson" 2> "$TMP_WORK/log.stderr" &
LOGGER_PID=$!
/bin/sleep 1
alive "$LOGGER_PID" || fail 'Il servizio log non e partito; nessun tasto da provare.'

/usr/bin/mkfifo "$TMP_WORK/control" "$TMP_WORK/status"
exec 3<> "$TMP_WORK/control"
CONTROL_OPEN=1
exec 4<> "$TMP_WORK/status"
STATUS_OPEN=1
/usr/bin/sudo -n "$PROBE" --failsafe < "$TMP_WORK/control" > "$TMP_WORK/status" 2> "$TMP_WORK/failsafe.stderr" 3>&- 4>&- &
FAILSAFE_PID=$!
receive 8 || fail 'Il programma di protezione non risponde; nessuna finestra attivata.'
[ "$(field state || true)" = failsafe-ready ] || fail 'Driver o stato iniziale non corrispondenti: prova fermata.'

INDEX=0
while [ "$INDEX" -lt 6 ]; do
    case "$INDEX" in
        0) LABEL='Tieni Fn, premi e rilascia F5, poi rilascia Fn.' ;;
        1) LABEL='Premi e rilascia F4 SENZA Fn.' ;;
        2) LABEL='Premi e rilascia F7 SENZA Fn.' ;;
        3) LABEL='Premi e rilascia F8 SENZA Fn.' ;;
        4) LABEL='Premi e rilascia F9 SENZA Fn.' ;;
        5) LABEL='Tieni il tasto Windows, premi e rilascia L, poi rilascia Windows.' ;;
    esac
    printf '\nProva %s/6: %s\n' "$((INDEX+1))" "$LABEL"
    printf 'Preparazione: '
    for SECOND in 3 2 1; do printf '%s... ' "$SECOND"; /bin/sleep 1 3>&- 4>&-; done
    printf '\n'
    alive "$LOGGER_PID" || fail 'Il servizio log si e fermato: nessun altro tasto da provare.'
    /bin/dd if=/dev/tty of=/dev/null bs=256 count=64 3>&- 4>&- 2>/dev/null || true
    printf 'ARM %s\n' "$INDEX" >&3
    receive 4 || fail 'Manca conferma di attivazione: prova fermata.'
    [ "$(field state || true)" = armed ] && [ "$(field trial || true)" = "$INDEX" ] || fail 'Conferma di attivazione non valida.'
    printf 'VIA: adesso.\n'
    receive 5 || fail 'Manca conferma di fine finestra: prova fermata.'
    [ "$(field state || true)" = window-off ] && [ "$(field trial || true)" = "$INDEX" ] &&
        [ "$(field logging_restored || true)" = true ] && [ "$(field window_complete || true)" = true ] || fail 'Finestra incompleta o ripristino non confermato.'
    printf 'FINE.\n'
    alive "$LOGGER_PID" || fail 'Il servizio log si e fermato durante la prova.'
    if [ "$INDEX" -eq 0 ]; then
        # Logging is already OFF. Allow delayed kernel messages to reach the stream.
        /bin/sleep 2 3>&- 4>&-
        if ! /usr/bin/osascript -l JavaScript "$PARSER" check "$TMP_WORK/trace.ndjson" "$TMP_WORK/protocol.jsonl" "$PREFIX" 0 3>&- 4>&- > "$TMP_WORK/control-result.txt" 2> "$TMP_WORK/parser.stderr"; then
            REASON=positive_control_missing
            printf '\nIl controllo Fn+F5 non rende visibili i codici: mi fermo qui.\n'
            break
        fi
        printf 'Controllo Fn+F5 valido. Proseguo con i soli tasti mancanti.\n'
    fi
    INDEX=$((INDEX+1))
done
if [ "$INDEX" -eq 6 ]; then REASON=complete; fi
stop_helper
if [ "$RESTORED" -ne 1 ]; then
    REASON=restoration_unverified
    fail 'Ripristino del logging non verificato: non ripetere la prova; comunicami questo messaggio.'
fi
/bin/sleep 2
stop_logger
restore_terminal
save_report || fail 'Impossibile generare lo ZIP; logging gia ripristinato.'
FINISHED=1
printf '\nLogging ripristinato a 0.\n'
