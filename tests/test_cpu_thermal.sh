#!/bin/bash
# Native macOS lifecycle checks use sleeping fixture workers, never CPU load.
set -eu
set -o pipefail
export LC_ALL=C
umask 077
source_file="${1:-packages/cpu-thermal/CHECK-CPU.command}"
test_root=$(/usr/bin/mktemp -d "${TMPDIR:-/tmp}/cpu-guardian-tests-XXXXXX")
cleanup() {
    local child
    for child in $(jobs -pr) $(jobs -ps); do kill -TERM "$child" 2>/dev/null || :; done
    /bin/sleep 0.2
    for child in $(jobs -pr) $(jobs -ps); do kill -KILL "$child" 2>/dev/null || :; done
    /bin/rm -rf -- "$test_root"
}
trap cleanup EXIT
trap 'exit 130' INT TERM HUP
/bin/bash -n "$source_file"
/bin/bash "$source_file" --self-test

# The guardian source is preserved except for a harmless sleeping workload,
# a shorter deadline, and recording fixture child PIDs for cleanup assertions.
/usr/bin/awk '
  /^[ ]*\/usr\/bin\/yes > \/dev\/null [&]$/ { $0="        /bin/sleep 30 > /dev/null &" }
  { sub("SECONDS-began < 20", "SECONDS-began < 2") }
  { print }
  /^        pid=\$!$/ { print "        printf '\''%s\\n'\'' \"$pid\" >> \"$directory/test-workers\"" }
' "$source_file" > "$test_root/guardian.command"

wait_for_file() {
    local path="$1" count
    for count in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 31 32 33 34 35 36 37 38 39 40; do
        [[ ! -e "$path" ]] || return 0
        /bin/sleep 0.1
    done
    printf 'Timed out waiting for a lifecycle fixture.\n' >&2
    return 1
}
assert_workers_gone() {
    local directory="$1" pid
    while read -r pid; do
        if kill -0 "$pid" 2>/dev/null; then
            printf 'A fixture worker survived guardian cleanup.\n' >&2
            return 1
        fi
    done < "$directory/test-workers"
}
for action in stop stopped cutoff stale malformed missing term deadline parent_exit; do
    directory="$test_root/$action"
    /bin/mkdir "$directory"
    printf '%s 46\n' "$(/bin/date +%s)" > "$directory/temperature-status"
    if [[ "$action" == parent_exit ]]; then
        /bin/bash -c '/bin/bash "$1" --load-supervisor "$2" "$$" 1 & wait' fixture-parent "$test_root/guardian.command" "$directory" > "$directory/output.txt" 2>&1 &
    else
        /bin/bash "$test_root/guardian.command" --load-supervisor "$directory" "$$" 1 > "$directory/output.txt" 2>&1 &
    fi
    process=$!
    wait_for_file "$directory/load-ready"
    while read -r worker; do kill -0 "$worker"; done < "$directory/test-workers"
    case "$action" in
      stop) : > "$directory/stop-load"; expected=stop_requested ;;
      stopped) while read -r worker; do kill -STOP "$worker"; done < "$directory/test-workers"; : > "$directory/stop-load"; expected=stop_requested ;;
      cutoff) printf '%s 85\n' "$(/bin/date +%s)" > "$directory/temperature-status.new"; /bin/mv "$directory/temperature-status.new" "$directory/temperature-status"; expected=temperature_invalid_or_cutoff ;;
      stale) printf '%s 46\n' "$(( $(/bin/date +%s)-10 ))" > "$directory/temperature-status.new"; /bin/mv "$directory/temperature-status.new" "$directory/temperature-status"; expected=temperature_stale ;;
      malformed) printf 'malformed\n' > "$directory/temperature-status.new"; /bin/mv "$directory/temperature-status.new" "$directory/temperature-status"; expected=temperature_invalid_or_cutoff ;;
      missing) /bin/rm "$directory/temperature-status"; expected=temperature_unavailable ;;
      term) kill -TERM "$process"; expected=interrupted ;;
      deadline) expected=deadline ;;
      parent_exit) kill -KILL "$process"; expected=parent_exit ;;
    esac
    wait_for_file "$directory/load-finished"
    wait "$process" 2>/dev/null || :
    assert_workers_gone "$directory"
    /usr/bin/grep -qx "Load supervisor result: $expected" "$directory/load-result.txt"
    printf 'Guardian fixture passed: %s\n' "$action"
done

# Test the real bounded-reader lifecycle with a harmless sampler replacement.
# No sudo or hardware telemetry is used in this isolated source fixture.
{
    printf '#!/bin/bash\nset -u\nsamplers=cpu_power\n'
    /usr/bin/awk '
      /^bounded_power_read[(][)] [{]$/ { inside=1 }
      inside {
        sub("/usr/bin/sudo -n /bin/bash -c", "/bin/bash -c")
        if ($0 ~ /^[ ]*\/usr\/bin\/powermetrics --samplers /) $0="      /bin/sleep 30 &"
        sub("SECONDS-began >= 4", "SECONDS-began >= 2")
        print
      }
      inside && /^[}]$/ { exit }
    ' "$source_file"
    printf 'bounded_power_read\n'
} > "$test_root/reader.command"
result=0
/bin/bash "$test_root/reader.command" > "$test_root/reader-output.txt" 2>&1 || result=$?
[[ "$result" == 124 ]]
printf 'Bounded reader timeout fixture passed.\n'

# A sampler stopped by a signal must still hit its deadline, rather than
# falling through to an unbounded wait on the stopped child.
/usr/bin/awk '
  { print }
  /^      reader_pid=\$!$/ { print "      kill -STOP \"$reader_pid\"" }
' "$test_root/reader.command" > "$test_root/stopped-reader.command"
result=0
/bin/bash "$test_root/stopped-reader.command" > "$test_root/stopped-reader-output.txt" 2>&1 || result=$?
[[ "$result" == 124 ]]
printf 'Stopped reader timeout fixture passed.\n'
