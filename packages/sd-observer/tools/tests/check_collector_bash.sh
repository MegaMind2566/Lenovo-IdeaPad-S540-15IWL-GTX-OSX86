#!/bin/bash
# Exercise the real collector's process helpers without Desktop or hardware I/O.
set -u
umask 077

test_dir=$(cd "$(dirname "$0")" && pwd) || exit 1
collector="$test_dir/../RACCOGLI-STATO-SD.command"
temporary_base="${TMPDIR:-/tmp}"
temporary_dir=$(/usr/bin/mktemp -d "$temporary_base/s540-collector-test.XXXXXX") || exit 1
outer_pid=""

/usr/bin/awk '
    /^job_active\(\)[[:space:]]*\{/ { copying = 1 }
    copying && /^stop_stream\(\)[[:space:]]*\{/ { exit }
    copying { print }
' "$collector" > "$temporary_dir/functions.sh" || exit 1
. "$temporary_dir/functions.sh"

cleanup() {
    if [ -n "$outer_pid" ]; then
        finish_job "$outer_pid" >/dev/null 2>&1 || true
    fi
    /bin/rm -rf "$temporary_dir"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

check_status() {
    local name="$1" expected="$2" limit="$3" result
    shift 3
    run_bounded "$limit" "$@" > "$temporary_dir/$name.out" 2> "$temporary_dir/$name.stderr"
    result=$?
    if [ "$result" -ne "$expected" ]; then
        printf 'FAIL: %s returned %s, expected %s\n' "$name" "$result" "$expected" >&2
        /bin/cat "$temporary_dir/$name.stderr" >&2
        exit 1
    fi
    printf 'PASS: %s\n' "$name"
}

check_status completed-command 0 3 /bin/bash -c 'exit 0'
check_status command-exit-status 7 3 /bin/bash -c 'exit 7'
check_status command-timeout 124 1 /bin/sleep 10

# The outer shell owns the log-like job; the helper subshell owns its reader.
/bin/sleep 30 &
outer_pid=$!
check_status timeout-with-outer-stream 124 1 /bin/sleep 10
if [ "$(jobs -pr 2>/dev/null)" != "$outer_pid" ]; then
    echo 'FAIL: the reader timeout affected the outer stream job.' >&2
    exit 1
fi
echo 'PASS: outer stream remains running'

finish_job "$outer_pid" >/dev/null 2>&1
result=$?
outer_pid=""
if [ "$result" -ne 143 ]; then
    printf 'FAIL: stream cleanup returned %s, expected 143\n' "$result" >&2
    exit 1
fi
if [ -n "$(jobs -pr 2>/dev/null)$(jobs -ps 2>/dev/null)" ]; then
    echo 'FAIL: an owned background job remains after cleanup.' >&2
    exit 1
fi
echo 'PASS: stream cleanup and exit status'

