#!/bin/bash
# Bounded, read-only Intel CPU telemetry. Compatible with the macOS Bash 3.2.
set -u
set -o pipefail
export LC_ALL=C
export LANG=C
umask 077

filter_metrics() {
    /usr/bin/awk '
      { sub(/^[ \t]+/, ""); sub(/[ \t]+$/, "") }
      /^CPU die temperature: [0-9]+([.][0-9]+)? C$/ { print; next }
      /^Intel energy model derived package power [(]CPUs[+]GT[+]SA[)]: [0-9]+([.][0-9]+)?[ ]?W$/ { print; next }
      /^(System|CPU) Average frequency as fraction of nominal: [0-9]+([.][0-9]+)?% [(][0-9]+([.][0-9]+)? [Mm][Hh][Zz][)]$/ { print; next }
      /^(CPU|IO|GPU) Thermal level: [0-9]+$/ { print; next }
      /^(CPU|GPU) Plimit: [0-9]+([.][0-9]+)?$/ { print; next }
      /^Number of prochots: [0-9]+$/ { print; next }
      /^(Current pressure level|Thermal pressure): (Nominal|Moderate|Heavy|Trapping|Fair|Serious|Critical)$/ { print; next }
      /^Fan: [0-9]+([.][0-9]+)?[ ]?(rpm|RPM)$/ { print; next }
      /^Invalid key detected!$/ { invalid++; next }
      END { if (invalid) print "Unavailable SMC keys reported: " invalid }
    '
}

temperature_value() {
    /usr/bin/awk '
      /^CPU die temperature: [0-9]+([.][0-9]+)? C$/ {
        value=$4+0; if (value>0 && value<=110) { count++; result=value }
      }
      END { if (count==1) print result }
    '
}

is_below_cutoff() {
    /usr/bin/awk -v value="$1" 'BEGIN {
      exit !(value ~ /^[0-9]+([.][0-9]+)?$/ && value+0>0 && value+0<85)
    }'
}

choose_samplers() {
    /usr/bin/awk '
      $1=="cpu_power" { cpu=1 }
      $1=="smc" { smc=1 }
      $1=="thermal" { thermal=1 }
      END {
        if (!cpu) exit 1;
        value="cpu_power";
        if (smc) value=value ",smc";
        if (thermal) value=value ",thermal";
        print value;
      }
    '
}

# A separate process owns every load worker. It does not depend on the
# telemetry pipeline to enforce the deadline or notice that its parent died.
load_supervisor() {
    local directory="$1" parent_pid="$2" workers="$3"
    local began=$SECONDS pid current_parent reason=deadline reached=0 stamp sensor extra now
    [[ "$parent_pid" =~ ^[1-9][0-9]*$ ]] || return 1
    [[ "$workers" =~ ^[1-8]$ ]] || return 1
    [[ -d "$directory" && ! -L "$directory" && -O "$directory" ]] || return 1

    stop_workers() {
        local candidate owned
        owned=$(jobs -p)
        # jobs also covers interruption between a fork and the PID assignment.
        for candidate in $(jobs -pr) $(jobs -ps); do
            kill -TERM "$candidate" 2>/dev/null || :
        done
        /bin/sleep 0.2
        for candidate in $(jobs -pr) $(jobs -ps); do
            kill -KILL "$candidate" 2>/dev/null || :
        done
        for candidate in $owned; do wait "$candidate" 2>/dev/null || :; done
        {
            printf 'Load supervisor result: %s\nLoad elapsed seconds: %s\n' "$reason" "$((SECONDS-began))"
            if [[ "${sensor-}" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
                printf 'Last guarded CPU temperature Celsius: %s\n' "$sensor"
            else
                printf 'Last guarded CPU temperature: unavailable\n'
            fi
        } > "$directory/load-result.txt"
        : > "$directory/load-finished"
    }
    trap 'reason=interrupted; exit 130' INT TERM HUP
    trap stop_workers EXIT
    check_conditions() {
        stamp=""; sensor=""; extra=""
        if ! { read -r stamp sensor extra < "$directory/temperature-status"; } 2>/dev/null; then
            reason=temperature_unavailable; return 1
        fi
        if [[ ! "$stamp" =~ ^[0-9]{1,10}$ || -n "$extra" ]] || ! is_below_cutoff "$sensor"; then
            reason=temperature_invalid_or_cutoff; return 1
        fi
        stamp=$((10#$stamp))
        now=$(/bin/date +%s)
        if (( now-stamp < 0 || now-stamp > 4 )); then reason=temperature_stale; return 1; fi
        current_parent=$(/bin/ps -p "$$" -o ppid= 2>/dev/null)
        current_parent=${current_parent//[[:space:]]/}
        [[ "$current_parent" == "$parent_pid" ]] || { reason=parent_exit; return 1; }
    }
    if ! check_conditions; then stop_workers; trap - EXIT; return 0; fi
    while (( reached < workers )); do
        /usr/bin/yes > /dev/null &
        pid=$!
        reached=$((reached+1))
    done
    : > "$directory/load-ready"
    while (( SECONDS-began < 20 )); do
        [[ ! -e "$directory/stop-load" ]] || { reason=stop_requested; break; }
        check_conditions || break
        /bin/sleep 0.2
    done
    stop_workers
    trap - EXIT
    return 0
}

if [[ "${1-}" == "--load-supervisor" && $# == 4 ]]; then
    load_supervisor "$2" "$3" "$4"
    exit $?
fi

if [[ "${1-}" == "--self-test" && $# == 1 ]]; then
    fixture=$'private-browser 123 42.0\nCPU die temperature: 46.00 C\nIntel energy model derived package power (CPUs+GT+SA): 0.80W\nSystem Average frequency as fraction of nominal: 48.29% (965.75 Mhz)\nCPU Average frequency as fraction of nominal: 42.87% (857.33 Mhz)\nCPU Thermal level: 0\nFan: 2100 rpm\nInvalid key detected!\n/Users/private-user/private-file\nCPU die temperature: invalid C\n'
    parsed=$(printf '%s' "$fixture" | filter_metrics)
    [[ "$parsed" != *private* ]] || exit 1
    [[ "$(printf '%s\n' "$parsed" | temperature_value)" == 46 ]] || exit 1
    [[ "$(printf 'CPU die temperature: 0 C\n' | temperature_value)" == "" ]] || exit 1
    [[ "$(printf 'CPU die temperature: 111 C\n' | temperature_value)" == "" ]] || exit 1
    [[ "$(printf 'CPU die temperature: 45 C\nCPU die temperature: 46 C\n' | temperature_value)" == "" ]] || exit 1
    is_below_cutoff 84.99 || exit 1
    if is_below_cutoff 85 || is_below_cutoff invalid; then exit 1; fi
    [[ "$(printf '  cpu_power CPU power\n  thermal pressure\n  smc sensors\n' | choose_samplers)" == "cpu_power,smc,thermal" ]] || exit 1
    [[ "$(printf '  cpu_power CPU power\n  thermal pressure\n' | choose_samplers)" == "cpu_power,thermal" ]] || exit 1
    if printf '  tasks names\n' | choose_samplers >/dev/null; then exit 1; fi
    printf 'Scalar filters, sampler discovery and temperature guards passed.\n'
    exit 0
fi

if (( $# != 0 )); then
    printf 'CPU check stopped: unexpected command arguments.\n' >&2
    exit 1
fi
if [[ "$(/usr/bin/uname -s)" != Darwin || "$(/usr/bin/uname -m)" != x86_64 || $EUID == 0 ]]; then
    printf 'Run this command as your normal desktop user on the Intel macOS laptop.\n' >&2
    exit 1
fi

package_directory=$(cd -P -- "$(dirname -- "$0")" && pwd) || exit 1
[[ -r "$package_directory/SHA256SUMS" ]] || { printf 'CPU check stopped: package checksums are missing.\n' >&2; exit 1; }
(cd "$package_directory" && /usr/bin/shasum -a 256 -c SHA256SUMS >/dev/null) || { printf 'CPU check stopped: package verification failed.\n' >&2; exit 1; }
[[ -d "$HOME/Desktop" && ! -L "$HOME/Desktop" ]] || { printf 'CPU check stopped: the Desktop folder is unavailable.\n' >&2; exit 1; }
work=$(/usr/bin/mktemp -d "${TMPDIR:-/tmp}/S540-CPU-XXXXXX") || exit 1
report="$work/cpu-report.txt"
supervisor_pid=""
cleanup() {
    if [[ -n "$supervisor_pid" ]]; then
        : > "$work/stop-load"
        wait "$supervisor_pid" 2>/dev/null || :
        supervisor_pid=""
    fi
    /bin/rm -rf -- "$work"
}
trap cleanup EXIT
trap 'printf "\nCPU check interrupted. Load workers are being stopped.\n" >&2; exit 130' INT TERM HUP

printf 'CPU, temperature and power check\n'
printf 'Connect the charger, close busy apps and leave the laptop on a firm surface.\n'
printf 'This takes about one minute. The CPU load lasts at most 20 seconds.\n'
printf 'Administrator authentication is used only for Apple powermetrics.\n'
/usr/bin/sudo -v || exit 1

help_text=$(/usr/bin/powermetrics --help 2>&1 || :)
samplers=$(printf '%s\n' "$help_text" | choose_samplers) || {
    printf 'CPU check stopped: the installed powermetrics does not advertise cpu_power.\n' >&2
    exit 1
}
logical=$(/usr/sbin/sysctl -n hw.logicalcpu 2>/dev/null)
[[ "$logical" =~ ^[1-9][0-9]*$ && ${#logical} -le 3 ]] || { printf 'CPU check stopped: CPU count unavailable.\n' >&2; exit 1; }
workers=$logical
(( workers <= 8 )) || workers=8
plugin=$(/usr/sbin/ioreg -r -c X86PlatformPlugin -d 1 2>/dev/null | /usr/bin/awk '
  /<class X86PlatformPlugin,/ && /, registered,/ && /, matched,/ && /, active,/ { found=1 }
  END { print found ? "registered, matched, active" : "not observed active" }
')
{
    printf 'S540 CPU telemetry report, version 1.0.0\n'
    printf 'macOS version: %s\n' "$(/usr/bin/sw_vers -productVersion)"
    printf 'macOS build: %s\n' "$(/usr/bin/sw_vers -buildVersion)"
    printf 'CPU model: %s\n' "$(/usr/sbin/sysctl -n machdep.cpu.brand_string 2>/dev/null)"
    printf 'Physical CPU cores: %s\n' "$(/usr/sbin/sysctl -n hw.physicalcpu 2>/dev/null)"
    printf 'Logical CPUs: %s\nLoad workers: %s\n' "$logical" "$workers"
    printf 'X86PlatformPlugin: %s\n' "$plugin"
    printf 'Selected advertised powermetrics samplers: %s\n' "$samplers"
    printf 'Sample interval milliseconds: 2000\nLoad deadline seconds: 20\nOperating cutoff Celsius: 85\n'
    printf 'Package power scope: estimated Intel CPUs+GT+SA; not total laptop wall power.\n'
    /usr/bin/pmset -g batt 2>/dev/null | /usr/bin/awk '
      /^Now drawing from '\''AC Power'\''$/ { print "Power source: AC" }
      /^Now drawing from '\''Battery Power'\''$/ { print "Power source: battery" }
    '
} > "$report"

sample_index=0
last_temperature=""
bounded_power_read() {
    # The static root wrapper owns only the Apple sampler and bounds its
    # lifetime. No command, file path or code is accepted from its arguments.
    /usr/bin/sudo -n /bin/bash -c '
      set -u
      selected=${1-}
      case "$selected" in cpu_power|cpu_power,smc|cpu_power,thermal|cpu_power,smc,thermal) ;; *) exit 1 ;; esac
      cleanup_reader() {
        local child
        for child in $(jobs -pr) $(jobs -ps); do kill -TERM "$child" 2>/dev/null || :; done
        /bin/sleep 0.2
        for child in $(jobs -pr) $(jobs -ps); do kill -KILL "$child" 2>/dev/null || :; done
        [[ -z "${reader_pid-}" ]] || wait "$reader_pid" 2>/dev/null || :
      }
      trap cleanup_reader EXIT
      trap "exit 130" INT TERM HUP
      /usr/bin/powermetrics --samplers "$selected" -n 1 -i 2000 &
      reader_pid=$!
      began=$SECONDS
      while [[ -n "$(jobs -pr; jobs -ps)" ]]; do
        if (( SECONDS-began >= 4 )); then exit 124; fi
        /bin/sleep 0.2
      done
      wait "$reader_pid"
      result=$?
      trap - EXIT
      exit "$result"
    ' cpu-power-reader "$samplers"
}
sample() {
    local phase="$1" output result
    sample_index=$((sample_index+1))
    # Explicit samplers avoid the per-process task sampler. The scalar filter
    # runs in the pipeline; no unfiltered command output is written to disk.
    output=$(bounded_power_read 2>&1 | filter_metrics)
    result=$?
    last_temperature=$(printf '%s\n' "$output" | temperature_value)
    if (( result == 0 )) && [[ -n "$last_temperature" ]]; then
        printf '%s %s\n' "$(/bin/date +%s)" "$last_temperature" > "$work/temperature-status.new"
        /bin/mv -f "$work/temperature-status.new" "$work/temperature-status"
    else
        : > "$work/temperature-status"
    fi
    {
        printf '\nPhase: %s; sample: %s; elapsed seconds: %s\n' "$phase" "$sample_index" "$SECONDS"
        printf 'powermetrics exit status: %s\n' "$result"
        [[ -z "$output" ]] || printf '%s\n' "$output"
        [[ -n "$last_temperature" ]] || printf 'CPU temperature: unavailable or ambiguous\n'
        /usr/bin/pmset -g therm 2>/dev/null | /usr/bin/awk '
          { sub(/^[ \t]+/, ""); sub(/[ \t]+$/, "") }
          /^(CPU_Scheduler_Limit|CPU_Speed_Limit|CPU_Available_CPUs|Thermal_Level) = [0-9]+$/ { print }
          /^Note: No thermal warning level has been recorded$/ { print }
          /^Note: No performance warning level has been recorded$/ { print }
        '
    } >> "$report"
    if [[ -n "$last_temperature" ]]; then
        printf '%s: CPU %s C\n' "$phase" "$last_temperature"
    else
        printf '%s: CPU temperature unavailable\n' "$phase"
    fi
    return "$result"
}

printf 'Idle measurement. Please leave the laptop untouched.\n'
baseline_ok=1
for pass in 1 2 3; do
    sample idle || baseline_ok=0
    [[ -n "$last_temperature" ]] || baseline_ok=0
    is_below_cutoff "$last_temperature" || baseline_ok=0
done
if (( baseline_ok )); then
    printf 'Short CPU load. It stops automatically at 85 C or after 20 seconds.\n'
    /bin/bash "$package_directory/CHECK-CPU.command" --load-supervisor "$work" "$$" "$workers" &
    supervisor_pid=$!
    for pass in 1 2 3 4 5 6 7 8 9 10; do
        [[ -e "$work/load-ready" || -e "$work/load-finished" ]] && break
        /bin/sleep 0.1
    done
    load_stop=supervisor_finished
    if [[ ! -e "$work/load-ready" ]]; then
        load_stop=supervisor_not_ready
        : > "$work/stop-load"
    else
        while [[ ! -e "$work/load-finished" ]]; do
            if ! sample load; then load_stop=telemetry_failed; : > "$work/stop-load"; break; fi
            if [[ -z "$last_temperature" ]]; then load_stop=temperature_unavailable; : > "$work/stop-load"; break; fi
            if ! is_below_cutoff "$last_temperature"; then
                load_stop=temperature_cutoff
                printf 'CPU load stopped at %s C.\n' "$last_temperature"
                : > "$work/stop-load"; break
            fi
        done
    fi
    wait "$supervisor_pid" 2>/dev/null || :
    supervisor_pid=""
    printf '\nLoad stop reason: %s\n' "$load_stop" >> "$report"
    [[ ! -f "$work/load-result.txt" ]] || /bin/cat "$work/load-result.txt" >> "$report"
    if [[ -f "$work/load-result.txt" ]]; then
        /usr/bin/awk '/^Load supervisor result:|^Last guarded CPU temperature/ { print }' "$work/load-result.txt"
    fi
else
    printf 'CPU load skipped: temperature unavailable, telemetry failed, or baseline at/above 85 C.\n'
    printf '\nLoad: skipped; valid baseline below 85 C was not available for every sample.\n' >> "$report"
fi
printf 'Recovery measurement.\n'
for pass in 1 2 3; do sample recovery || :; done
printf '\nFan RPM and thermal-limit data are unavailable if not present above.\n' >> "$report"
printf 'This brief check does not certify sustained-load cooling or battery autonomy.\n' >> "$report"

destination=$(/usr/bin/mktemp -d "$HOME/Desktop/CPU-THERMAL-XXXXXX") || exit 1
/bin/cp "$report" "$destination/cpu-report.txt" || exit 1
(cd "$destination" && /usr/bin/zip -q "$destination.zip" cpu-report.txt) || exit 1
/bin/rm -f "$destination/cpu-report.txt"
/bin/rmdir "$destination" || :
printf '\nReport saved: %s.zip\nAttach this ZIP in the chat.\n' "$destination"
