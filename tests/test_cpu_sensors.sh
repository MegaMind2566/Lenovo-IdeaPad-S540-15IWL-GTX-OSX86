#!/bin/bash
# Native Bash 3.2 fixtures replace each reader with a harmless sleeping child.
set -eu
set -o pipefail
export LC_ALL=C
umask 077
source_file="${1:-packages/cpu-sensors/CHECK-SENSORS.command}"
source_directory=$(cd -P -- "$(dirname -- "$source_file")" && pwd)
test_root=$(/usr/bin/mktemp -d "${TMPDIR:-/tmp}/passive-sensor-tests-XXXXXX")
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

# Unsafe text, unit-free readings, invalid tokens, extreme values, duplicate
# values and missing lines have distinct fixed outcomes without text leakage.
{
    printf '%s\n' 'CPU die temperature: 46 C' 'Invalid key detected!'
    for value in '45 C' '+4.6e1 Celsius' '.47e2 degC' 'NaN C' 'N/A C' '+inf C' '-inf C' '0 C' '111 C' '1e999 C' '46' '46 /Users/private-path' 'private-text C' '46 C private-tail'; do
        printf '%s\n' '*** Sampled system activity (private timestamp) ***' "CPU die temperature: $value" 'private-process /Users/private-path'
    done
    printf '%s\n' '*** Sampled system activity (private timestamp) ***' 'CPU die temperature = private-payload'
    printf '%s\n' '*** Sampled system activity (private timestamp) ***' 'cpu die temperature: private-payload'
    printf '%s\n' '*** Sampled system activity (private timestamp) ***' 'Fan: 2300 rpm'
} | /usr/bin/awk -f "$source_directory/filter-sensors.awk" > "$test_root/grammar.txt"
/usr/bin/grep -qx 'Samples observed: 17' "$test_root/grammar.txt"
/usr/bin/grep -qx 'Samples with one valid CPU temperature: 3' "$test_root/grammar.txt"
/usr/bin/grep -qx 'Samples with a rejected CPU temperature: 13' "$test_root/grammar.txt"
/usr/bin/grep -qx 'Samples with no CPU temperature line: 1' "$test_root/grammar.txt"
/usr/bin/grep -qx 'Unavailable SMC keys before first sample: 1' "$test_root/grammar.txt"
/usr/bin/grep -qx 'CPU temperature lines before first sample: 1' "$test_root/grammar.txt"
if /usr/bin/grep -E 'private|/Users/|timestamp|process' "$test_root/grammar.txt" >/dev/null; then
    printf 'The telemetry privacy fixture leaked a rejected payload.\n' >&2; exit 1
fi
printf 'Passive temperature grammar and privacy fixtures passed.\n'

# Exercise the exact lifecycle body of every reader. Only its fixed command,
# sudo prefix and deadline are changed in these isolated source fixtures.
for reader in bounded_power_read bounded_driver_read bounded_processor_read; do
    for action in normal timeout stopped; do
        export READER_FIXTURE_PID_FILE="$test_root/$reader-$action.pid"
        fixture="$test_root/$reader-$action.command"
        {
            printf '#!/bin/bash\nset -u\nsamplers=cpu_power\n'
            /usr/bin/awk -v wanted="$reader" -v action="$action" '
              $0==wanted "() {" { inside=1 }
              inside {
                sub("/usr/bin/sudo -n /bin/bash -c", "/bin/bash -c");
                if ($0 ~ /^[ ]*\/usr\/bin\/powermetrics --samplers / ||
                    $0 ~ /^[ ]*\/usr\/bin\/kmutil showloaded / ||
                    $0 ~ /^[ ]*\/usr\/sbin\/ioreg -r -c SMCProcessor /)
                    $0=(action=="normal" ? "      /bin/sleep 0.1 &" : "      /bin/sleep 30 &");
                sub("SECONDS-began >= 40", "SECONDS-began >= 2");
                sub("SECONDS-began >= 10", "SECONDS-began >= 2");
                print;
                if ($0=="      reader_pid=$!") {
                    print "      printf \"%s\\n\" \"$reader_pid\" > \"$READER_FIXTURE_PID_FILE\"";
                    if (action=="stopped") print "      kill -STOP \"$reader_pid\"";
                }
              }
              inside && /^[}]$/ { exit }
            ' "$source_file"
            printf '%s\n' "$reader"
        } > "$fixture"
        /bin/bash -n "$fixture"
        result=0
        /bin/bash "$fixture" > "$test_root/$reader-$action-output.txt" 2>&1 || result=$?
        if [[ "$action" == normal ]]; then expected=0; else expected=124; fi
        [[ "$result" == "$expected" ]]
        read -r child < "$READER_FIXTURE_PID_FILE"
        if kill -0 "$child" 2>/dev/null; then
            printf 'A passive reader fixture child survived cleanup.\n' >&2; exit 1
        fi
        printf 'Passive reader lifecycle passed: %s %s\n' "$reader" "$action"
    done
done
