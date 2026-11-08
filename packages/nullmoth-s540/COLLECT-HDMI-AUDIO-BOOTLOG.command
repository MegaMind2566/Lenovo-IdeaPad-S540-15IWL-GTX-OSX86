#!/bin/zsh

set -euo pipefail

script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)"
workspace="$(CDPATH= cd -- "$script_dir/../.." && pwd -P)"
device='/dev/disk0s1'
mount_point='/Volumes/EFI-S540-HDMI-AUDIO-DIAG'
timestamp=$(date '+%Y%m%d-%H%M%S')
output="$workspace/_diagnostics/hdmi-audio-postboot-$timestamp"
result_file='/tmp/s540-hdmi-audio-bootlog-result.txt'
mounted=0

cleanup() {
    local exit_code=$?
    trap - EXIT
    if (( mounted == 1 )); then
        sudo /sbin/umount "$mount_point" >/dev/null 2>&1 || \
            sudo /usr/sbin/diskutil unmount disk0s1 >/dev/null 2>&1 || true
    fi
    sudo /bin/rmdir "$mount_point" >/dev/null 2>&1 || true
    exit "$exit_code"
}
trap cleanup EXIT

/bin/rm -f "$result_file"
exec > >(tee "$result_file") 2>&1

echo 'Raccolta in sola lettura del log OpenCore dalla EFI interna.'
echo 'Inserisci la password amministratore quando richiesta.'
sudo -v

disk_info=$(/usr/sbin/diskutil info disk0s1)
internal_flag=$(echo "$disk_info" | /usr/bin/awk -F: '/Device Location/ {gsub(/^[[:space:]]+/, "", $2); print $2}')
partition_type=$(echo "$disk_info" | /usr/bin/awk -F: '/Partition Type/ {gsub(/^[[:space:]]+/, "", $2); print $2}')
disk_bytes=$(echo "$disk_info" | /usr/bin/awk '/Disk Size:/ {gsub(/[()]/, "", $5); print $5}')
[[ "$internal_flag" == 'Internal' && "$partition_type" == 'EFI' && "$disk_bytes" == '314572800' ]] || {
    echo "Rifiuto: ESP inattesa ($internal_flag, $partition_type, $disk_bytes byte)."
    exit 1
}
if /sbin/mount | /usr/bin/grep -q '^/dev/disk0s1 '; then
    echo 'Rifiuto: disk0s1 è già montato.'
    exit 1
fi
[[ ! -e "$mount_point" ]] || {
    echo "Rifiuto: mount point già presente: $mount_point"
    exit 1
}

/bin/mkdir -p "$output"
sudo /bin/mkdir "$mount_point"
sudo /sbin/mount_msdos -o rdonly -u "$(id -u)" -g "$(id -g)" "$device" "$mount_point"
mounted=1

live_config="$mount_point/EFI/OC/config.plist"
live_kext="$mount_point/EFI/OC/Kexts/NMXAudio.kext"
[[ -f "$live_config" && -d "$live_kext" ]] || {
    echo 'Rifiuto: config o NMXAudio assente dalla EFI attiva.'
    exit 1
}

echo '-- hash EFI attiva --'
/usr/bin/shasum -a 256 "$live_config" \
    "$live_kext/Contents/Info.plist" \
    "$live_kext/Contents/MacOS/NMXAudio"

log_count=0
while IFS= read -r -d '' log_file; do
    /usr/bin/ditto "$log_file" "$output/$(basename "$log_file")"
    log_count=$((log_count + 1))
done < <(/usr/bin/find "$mount_point" -maxdepth 3 -type f \
    \( -iname 'opencore-*.txt' -o -iname 'opencore*.log' \) -print0)

echo "Log OpenCore copiati: $log_count"
if (( log_count > 0 )); then
    echo '-- righe rilevanti --'
    /usr/bin/grep -RinE 'NMXAudio|Prelinked|Kext|OC: Kernel|OC: Prelink' "$output" || true
fi
echo "RACCOLTA_HDMI_AUDIO_BOOTLOG_OK output=$output logs=$log_count"
