#!/bin/zsh

set -euo pipefail

result_file='/tmp/s540-sleep-wake-hdmi-result.txt'
post_av='/tmp/s540-sleep-wake-post-av.txt'
post_wifi='/tmp/s540-sleep-wake-post-wifi.txt'
post_bluetooth='/tmp/s540-sleep-wake-post-bluetooth.txt'

/bin/rm -f "$result_file" "$post_av" "$post_wifi" "$post_bluetooth"
exec > >(tee "$result_file") 2>&1

echo 'Test sleep/wake S540 con HDMI e audio attivi.'
echo 'Dopo l’autenticazione il sistema dormirà per circa 45–60 secondi.'
echo 'Non premere tasti finché lo schermo non si riaccende da solo.'
sudo -v

echo '-- stato prima dello sleep --'
/usr/bin/uptime
/usr/sbin/system_profiler SPAudioDataType SPDisplaysDataType -detailLevel mini | \
    /usr/bin/egrep 'NVIDIA \(0x0094\)|Internal Speakers|Internal Microphone|LG TV|NV156FHM|Default Output Device'
/usr/bin/kmutil showloaded 2>/dev/null | \
    /usr/bin/egrep 'com\.nullmoth\.(NMXAudio|NVRM|NVRMFB|NVAccel)|org\.voodoo\.driver\.VoodooHDA|BrightnessKeys'

sleep_start=$(/bin/date '+%Y-%m-%d %H:%M:%S %z')
echo "Programmo il risveglio relativo a 45 secondi. Inizio: $sleep_start"
sudo /usr/bin/pmset relative wake 45
/usr/bin/pmset -g sched
/bin/sync
sudo /usr/bin/pmset sleepnow

echo 'Sistema risvegliato; attendo 15 secondi per rete, audio e WindowServer.'
/bin/sleep 15
wake_observed=$(/bin/date '+%Y-%m-%d %H:%M:%S %z')
echo "Ripresa osservata: $wake_observed"

/usr/sbin/system_profiler SPAudioDataType SPDisplaysDataType -detailLevel full > "$post_av"
/usr/sbin/system_profiler SPAirPortDataType -detailLevel mini > "$post_wifi"
/usr/sbin/system_profiler SPBluetoothDataType -detailLevel mini > "$post_bluetooth"

failures=0
check() {
    local description=$1
    shift
    if "$@"; then
        echo "OK: $description"
    else
        echo "ERRORE: $description"
        failures=$((failures + 1))
    fi
}
bundle_loaded() {
    /usr/bin/kmutil showloaded --list-only --bundle-identifier "$1" 2>/dev/null | \
        /usr/bin/grep -Fq "$1"
}
backlight_present() {
    /usr/sbin/ioreg -r -c AppleBacklightDisplay -l -w0 | \
        /usr/bin/grep -q 'AppleBacklightDisplay'
}

echo '-- verifiche dopo il wake --'
check 'NMXAudio ancora caricato' bundle_loaded com.nullmoth.NMXAudio
check 'VoodooHDA ancora caricato' bundle_loaded org.voodoo.driver.VoodooHDA
check 'NVRMFB ancora caricato' bundle_loaded com.nullmoth.NVRMFB
check 'televisore LG ancora online' /usr/bin/grep -q 'LG TV:' "$post_av"
check 'uscita NVIDIA HDMI ancora presente' /usr/bin/grep -q 'NVIDIA (0x0094) (HDMI/DP 8ch):' "$post_av"
check 'altoparlanti interni ancora presenti' /usr/bin/grep -q 'Internal Speakers:' "$post_av"
check 'microfono interno ancora presente' /usr/bin/grep -q 'Internal Microphone:' "$post_av"
check 'pannello retroilluminato ancora pubblicato' backlight_present
check 'Wi-Fi riconnesso' /usr/bin/grep -q 'Status: Connected' "$post_wifi"
check 'controller Bluetooth attivo' /usr/bin/grep -q 'State: On' "$post_bluetooth"

echo '-- percorso audio durante la riproduzione post-wake --'
/usr/bin/afplay /System/Library/Sounds/Glass.aiff &
player_pid=$!
/bin/sleep 0.3
engine_state=$(/usr/sbin/ioreg -r -c NMXAudioEngine -l -w0 | \
    /usr/bin/egrep 'IOAudioEngineState|IOAudioEngineNumActiveUserClients|IOAudioSampleRate|IOAudioEngineDescription')
echo "$engine_state"
wait "$player_pid"
echo "$engine_state" | /usr/bin/grep -q '"IOAudioEngineState" = 1' || failures=$((failures + 1))
echo "$engine_state" | /usr/bin/grep -q '"IOAudioEngineNumActiveUserClients" = 1' || failures=$((failures + 1))

echo '-- ultimo evento sleep/wake registrato --'
/usr/bin/pmset -g log | /usr/bin/egrep ' Sleep  | Wake  | DarkWake |Sleep Failure|Wake Failure' | /usr/bin/tail -n 12

if (( failures == 0 )); then
    echo "TEST_SLEEP_WAKE_HDMI_OK sleep_start=$sleep_start wake_observed=$wake_observed"
else
    echo "TEST_SLEEP_WAKE_HDMI_FALLITO failures=$failures"
    exit 1
fi
