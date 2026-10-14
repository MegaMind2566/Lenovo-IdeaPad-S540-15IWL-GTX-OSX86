#!/bin/bash
# Passive, bounded Intel sensor telemetry; macOS Bash 3.2 compatible.
set -u
set -o pipefail
export LC_ALL=C
export LANG=C
umask 077

choose_samplers() {
    /usr/bin/awk '
      $1=="cpu_power" { cpu=1 }
      $1=="smc" { smc=1 }
      $1=="thermal" { thermal=1 }
      END {
        if (!cpu) exit 1;
        result="cpu_power";
        if (smc) result=result ",smc";
        if (thermal) result=result ",thermal";
        print result;
      }
    '
}

filter_driver_versions() {
    /usr/bin/awk '
      {
        for (i=1;i<=NF;i++) {
          if ($i=="as.vit9696.Lilu" || $i=="as.vit9696.VirtualSMC" || $i=="as.vit9696.SMCProcessor" || $i=="ru.usrsse2.SMCBatteryManager") {
            version=$(i+1);
            if (version ~ /^[(][0-9]+[.][0-9]+([.][0-9]+)?([.][0-9]+)?[)]$/) {
              sub(/^[(]/,"",version); sub(/[)]$/,"",version);
              print "Loaded driver: " $i "; version: " version; seen++;
            } else print "Loaded driver: " $i "; version: unavailable";
          }
        }
      }
      END { print "Relevant loaded drivers with recognized versions: " seen+0 }
    '
}

filter_processor_status() {
    /usr/bin/awk '
      /<class SMCProcessor,/ && /, registered,/ && /, matched,/ && /, active,/ { active=1 }
      /^[ \t]*"VersionInfo" = "[0-9]+[.][0-9]+([.][0-9]+)?([.][0-9]+)?"[ \t]*$/ {
        line=$0; sub(/^[ \t]*"VersionInfo" = "/,"",line); sub(/"[ \t]*$/,"",line);
        print "SMCProcessor numeric VersionInfo: " line;
        next;
      }
      /^[ \t]*"VersionInfo" = / { print "SMCProcessor VersionInfo: present; nonnumeric payload omitted" }
      END { print "SMCProcessor runtime state: " (active ? "registered, matched, active" : "not observed registered, matched, active") }
    '
}

bounded_power_read() {
    # This static root wrapper accepts only the advertised sampler allowlist.
    # It owns only its Apple reader, including if that child becomes stopped.
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
      /usr/bin/powermetrics --samplers "$selected" -n 15 -i 2000 &
      reader_pid=$!
      began=$SECONDS
      while [[ -n "$(jobs -pr; jobs -ps)" ]]; do
        if (( SECONDS-began >= 40 )); then exit 124; fi
        /bin/sleep 0.2
      done
      wait "$reader_pid"
      result=$?
      trap - EXIT
      exit "$result"
    ' smc-passive-reader "$samplers"
}

bounded_driver_read() {
    /usr/bin/sudo -n /bin/bash -c '
      set -u
      cleanup_reader() {
        local child
        for child in $(jobs -pr) $(jobs -ps); do kill -TERM "$child" 2>/dev/null || :; done
        /bin/sleep 0.2
        for child in $(jobs -pr) $(jobs -ps); do kill -KILL "$child" 2>/dev/null || :; done
        [[ -z "${reader_pid-}" ]] || wait "$reader_pid" 2>/dev/null || :
      }
      trap cleanup_reader EXIT
      trap "exit 130" INT TERM HUP
      /usr/bin/kmutil showloaded &
      reader_pid=$!
      began=$SECONDS
      while [[ -n "$(jobs -pr; jobs -ps)" ]]; do
        if (( SECONDS-began >= 10 )); then exit 124; fi
        /bin/sleep 0.2
      done
      wait "$reader_pid"
      result=$?
      trap - EXIT
      exit "$result"
    ' smc-driver-reader
}

bounded_processor_read() {
    /bin/bash -c '
      set -u
      cleanup_reader() {
        local child
        for child in $(jobs -pr) $(jobs -ps); do kill -TERM "$child" 2>/dev/null || :; done
        /bin/sleep 0.2
        for child in $(jobs -pr) $(jobs -ps); do kill -KILL "$child" 2>/dev/null || :; done
        [[ -z "${reader_pid-}" ]] || wait "$reader_pid" 2>/dev/null || :
      }
      trap cleanup_reader EXIT
      trap "exit 130" INT TERM HUP
      /usr/sbin/ioreg -r -c SMCProcessor -l -d 1 &
      reader_pid=$!
      began=$SECONDS
      while [[ -n "$(jobs -pr; jobs -ps)" ]]; do
        if (( SECONDS-began >= 10 )); then exit 124; fi
        /bin/sleep 0.2
      done
      wait "$reader_pid"
      result=$?
      trap - EXIT
      exit "$result"
    ' smc-processor-reader
}

if [[ "${1-}" == "--self-test" && $# == 1 ]]; then
    source_directory=$(cd -P -- "$(dirname -- "$0")" && pwd) || exit 1
    parsed=$(printf '%s\n' \
      '*** Sampled system activity (private timestamp) (2000ms elapsed) ***' \
      'CPU die temperature: 4.6e1 C' 'Intel energy model derived package power (CPUs+GT+SA): 0.80W' \
      'Invalid key detected!' 'private-browser 123 42.0 /Users/private-user/private-file' \
      '*** Sampled system activity (private timestamp) (2000ms elapsed) ***' \
      'CPU die temperature: -1 C' \
      '*** Sampled system activity (private timestamp) (2000ms elapsed) ***' \
      'CPU die temperature: NaN C' \
      '*** Sampled system activity (private timestamp) (2000ms elapsed) ***' \
      'CPU die temperature: /Users/private-user/private-file C' \
      '*** Sampled system activity (private timestamp) (2000ms elapsed) ***' \
      'CPU die temperature: 46 C' 'CPU die temperature: 47 C' \
      '*** Sampled system activity (private timestamp) (2000ms elapsed) ***' \
      'Fan: 2100 rpm' | /usr/bin/awk -f "$source_directory/filter-sensors.awk") || exit 1
    [[ "$parsed" != *private* && "$parsed" != */Users/* ]] || exit 1
    [[ "$parsed" == *'Samples observed: 6'* ]] || exit 1
    [[ "$parsed" == *'Samples with one valid CPU temperature: 1'* ]] || exit 1
    [[ "$parsed" == *'Samples with no CPU temperature line: 1'* ]] || exit 1
    [[ "$parsed" == *'Samples with a rejected CPU temperature: 3'* ]] || exit 1
    [[ "$parsed" == *'Samples with duplicate CPU temperature lines: 1'* ]] || exit 1
    [[ "$parsed" == *'numeric; value: 4.6e1; unit: C; accepted: yes'* ]] || exit 1
    [[ "$parsed" == *'numeric; value: -1; unit: C; accepted: no'* ]] || exit 1
    [[ "$parsed" == *'nonfinite or unavailable; token: nan; unit: C'* ]] || exit 1
    [[ "$parsed" == *'Total unavailable SMC keys within samples: 1'* ]] || exit 1
    [[ "$(printf '  cpu_power CPU power\n  smc sensors\n  thermal pressure\n' | choose_samplers)" == 'cpu_power,smc,thermal' ]] || exit 1
    if printf '  tasks private paths\n' | choose_samplers >/dev/null; then exit 1; fi
    versions=$(printf '%s\n' '56 6 address size as.vit9696.Lilu (1.7.2) private-UUID' '57 0 address size as.vit9696.SMCProcessor (1.3.7) private-UUID' 'private-bundle (1.0.0) private-UUID' | filter_driver_versions) || exit 1
    [[ "$versions" != *private* && "$versions" != *address* && "$versions" != *UUID* ]] || exit 1
    [[ "$versions" == *'Relevant loaded drivers with recognized versions: 2'* ]] || exit 1
    processor=$(printf '%s\n' '+-o SMCProcessor <class SMCProcessor, id private-id, registered, matched, active, busy 0, retain 8>' '  "VersionInfo" = "1.3.8"' '  "private-path" = "/Users/private-user/private-file"' | filter_processor_status) || exit 1
    [[ "$processor" != *private* && "$processor" == *'SMCProcessor numeric VersionInfo: 1.3.8'* ]] || exit 1
    [[ "$processor" == *'SMCProcessor runtime state: registered, matched, active'* ]] || exit 1
    processor=$(printf '%s\n' '  "VersionInfo" = "REL-138-private-build-date"' | filter_processor_status) || exit 1
    [[ "$processor" != *private* && "$processor" == *'SMCProcessor VersionInfo: present; nonnumeric payload omitted'* ]] || exit 1
    printf 'Passive sensor parser, privacy and sampler fixtures passed.\n'
    exit 0
fi

if (( $#!=0 )); then printf 'Sensor check stopped: unexpected arguments.\n' >&2; exit 1; fi
if [[ "$(/usr/bin/uname -s)" != Darwin || "$(/usr/bin/uname -m)" != x86_64 || $EUID == 0 ]]; then
    printf 'Run this command as your normal desktop user on the Intel macOS laptop.\n' >&2; exit 1
fi
package_directory=$(cd -P -- "$(dirname -- "$0")" && pwd) || exit 1
[[ -r "$package_directory/SHA256SUMS" ]] || { printf 'Sensor check stopped: checksums are missing.\n' >&2; exit 1; }
(cd "$package_directory" && /usr/bin/shasum -a 256 -c SHA256SUMS >/dev/null) || { printf 'Sensor check stopped: package verification failed.\n' >&2; exit 1; }
[[ -d "$HOME/Desktop" && ! -L "$HOME/Desktop" ]] || { printf 'Sensor check stopped: the Desktop folder is unavailable.\n' >&2; exit 1; }
work=$(/usr/bin/mktemp -d "${TMPDIR:-/tmp}/S540-SENSORS-XXXXXX") || exit 1
cleanup() { /bin/rm -rf -- "$work"; }
trap cleanup EXIT
trap 'printf "\nSensor check interrupted. The bounded Apple reader will stop.\n" >&2; exit 130' INT TERM HUP
report="$work/sensors-report.txt"
printf 'Passive CPU sensor check\nLeave the laptop idle for about 30 seconds.\n'
printf 'This reads sensor telemetry and loaded driver versions. It starts no CPU workload.\n'
printf 'Administrator authentication is used only for the two bounded Apple readers.\n'
/usr/bin/sudo -v || exit 1
help_text=$(/usr/bin/powermetrics --help 2>&1 || :)
samplers=$(printf '%s\n' "$help_text" | choose_samplers) || { printf 'Sensor check stopped: powermetrics does not advertise cpu_power.\n' >&2; exit 1; }
{
    printf 'S540 passive sensor report, version 1.0.0\n'
    printf 'Selected advertised powermetrics samplers: %s\n' "$samplers"
    printf 'Requested samples: 15\nSample interval milliseconds: 2000\nReader deadline seconds: 40\n'
    printf 'Workload: none; normal background activity continues.\n'
    printf 'Temperature acceptance: one numeric CPU die value greater than 0 and at most 110 Celsius.\n'
    printf 'Package power scope: estimated Intel CPUs+GT+SA, not total laptop wall power.\n'
} > "$report"
printf 'Reading relevant loaded driver versions.\n'
bounded_driver_read 2>&1 | filter_driver_versions >> "$report"
reader_results=("${PIPESTATUS[@]}")
driver_status=${reader_results[0]}
[[ "${reader_results[1]}" == 0 ]] || { printf 'Sensor check stopped: driver filter failed.\n' >&2; exit 1; }
printf 'kmutil exit status: %s\n' "$driver_status" >> "$report"
bounded_processor_read 2>&1 | filter_processor_status >> "$report"
reader_results=("${PIPESTATUS[@]}")
processor_status=${reader_results[0]}
[[ "${reader_results[1]}" == 0 ]] || { printf 'Sensor check stopped: processor filter failed.\n' >&2; exit 1; }
printf 'SMCProcessor status reader exit status: %s\n' "$processor_status" >> "$report"
printf 'Reading 15 consecutive powermetrics samples. Please leave the laptop untouched.\n'
bounded_power_read 2>&1 | /usr/bin/awk -f "$package_directory/filter-sensors.awk" >> "$report"
reader_results=("${PIPESTATUS[@]}")
reader_status=${reader_results[0]}
[[ "${reader_results[1]}" == 0 ]] || { printf 'Sensor check stopped: telemetry filter failed.\n' >&2; exit 1; }
printf '\npowermetrics exit status: %s\n' "$reader_status" >> "$report"
printf 'A missing sensor reading does not identify its cause. No driver or configuration was changed.\n' >> "$report"
printf 'This passive check does not certify cooling under load.\n' >> "$report"
destination=$(/usr/bin/mktemp -d "$HOME/Desktop/SMC-SENSORS-XXXXXX") || exit 1
/bin/cp "$report" "$destination/sensors-report.txt" || exit 1
(cd "$destination" && /usr/bin/zip -q "$destination.zip" sensors-report.txt) || exit 1
/bin/rm -f "$destination/sensors-report.txt"
/bin/rmdir "$destination" || :
printf '\nReport saved: %s.zip\nAttach this ZIP in the chat.\n' "$destination"
