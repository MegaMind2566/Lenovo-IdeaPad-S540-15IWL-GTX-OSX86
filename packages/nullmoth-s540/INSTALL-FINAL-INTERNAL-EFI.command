#!/bin/zsh

set -euo pipefail

script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)"
workspace="$(CDPATH= cd -- "$script_dir/../.." && pwd -P)"
candidate="$workspace/_candidates/S540-NullMoth-final/EFI/OC"
device='/dev/disk0s1'
mount_point='/Volumes/EFI-S540-INTERNAL'
validator="$workspace/_external/opencore-1.0.8/extracted/Utilities/ocvalidate/ocvalidate"
timestamp=$(date '+%Y%m%d-%H%M%S')
backup_root="$workspace/_backups/internal-efi-before-nullmoth-$timestamp"
stage_name="OC.S540-CANDIDATE-$timestamp"
previous_name="OC.S540-PREVIOUS-$timestamp"
result_file='/tmp/s540-internal-efi-install-result.txt'
mounted=0
old_moved=0

cleanup() {
    local exit_code=$?

    trap - EXIT

    if (( exit_code != 0 && mounted == 1 && old_moved == 1 )); then
        if [[ -d "$mount_point/EFI/$previous_name" ]]; then
            echo 'Errore durante lo scambio: ripristino automaticamente la EFI precedente.'
            if [[ -d "$mount_point/EFI/OC" ]]; then
                sudo /bin/mv "$mount_point/EFI/OC" "$mount_point/EFI/OC.S540-FAILED-$timestamp" || true
            fi
            sudo /bin/mv "$mount_point/EFI/$previous_name" "$mount_point/EFI/OC" || true
        fi
    fi

    if (( mounted == 1 )); then
        /bin/sync
        sudo /sbin/umount "$mount_point" >/dev/null 2>&1 || \
            sudo /usr/sbin/diskutil unmount disk0s1 >/dev/null 2>&1 || true
    fi
    sudo /bin/rmdir "$mount_point" >/dev/null 2>&1 || true
    exit "$exit_code"
}
trap cleanup EXIT

rm -f "$result_file"
exec > >(tee "$result_file") 2>&1

echo 'Lenovo S540: installazione EFI interna definitiva'
echo "Dispositivo previsto: $device (ESP interna NVMe da 314,6 MB)"
echo 'Verrà sostituita soltanto EFI/OC; BOOT, rEFInd e Microsoft resteranno invariati.'
echo 'Inserisci la password amministratore quando richiesta.'
sudo -v

[[ -d "$candidate" ]] || { echo "Candidata assente: $candidate"; exit 1; }
[[ -x "$validator" ]] || { echo "ocvalidate assente: $validator"; exit 1; }
"$validator" "$candidate/config.plist"

internal_flag=$(/usr/sbin/diskutil info disk0s1 | /usr/bin/awk -F: '/Device Location/ {gsub(/^[[:space:]]+/, "", $2); print $2}')
partition_type=$(/usr/sbin/diskutil info disk0s1 | /usr/bin/awk -F: '/Partition Type/ {gsub(/^[[:space:]]+/, "", $2); print $2}')
disk_bytes=$(/usr/sbin/diskutil info disk0s1 | /usr/bin/awk '/Disk Size:/ {gsub(/[()]/, "", $5); print $5}')
[[ "$internal_flag" == 'Internal' ]] || { echo "Rifiuto: disk0s1 non risulta interno ($internal_flag)."; exit 1; }
[[ "$partition_type" == 'EFI' ]] || { echo "Rifiuto: disk0s1 non è una partizione EFI ($partition_type)."; exit 1; }
[[ "$disk_bytes" == '314572800' ]] || { echo "Rifiuto: dimensione ESP inattesa ($disk_bytes byte)."; exit 1; }

if /sbin/mount | /usr/bin/grep -q '^/dev/disk0s1 '; then
    echo 'Rifiuto: disk0s1 risulta già montato; smontalo prima di riprovare.'
    exit 1
fi
[[ ! -e "$mount_point" ]] || { echo "Rifiuto: mount point già esistente: $mount_point"; exit 1; }

sudo /bin/mkdir "$mount_point"
sudo /sbin/mount_msdos -u "$(id -u)" -g "$(id -g)" "$device" "$mount_point"
mounted=1

[[ -d "$mount_point/EFI" ]] || { echo 'Rifiuto: cartella EFI assente nella ESP interna.'; exit 1; }
[[ -d "$mount_point/EFI/OC" ]] || { echo 'Rifiuto: EFI/OC interna assente.'; exit 1; }
[[ ! -e "$mount_point/EFI/$stage_name" ]] || { echo 'Rifiuto: staging già presente.'; exit 1; }
[[ ! -e "$mount_point/EFI/$previous_name" ]] || { echo 'Rifiuto: rollback con lo stesso nome già presente.'; exit 1; }

echo 'Cartelle EFI preservate:'
/bin/ls -1 "$mount_point/EFI" | /usr/bin/sed 's/^/  - /'

candidate_kb=$(/usr/bin/du -sk "$candidate" | /usr/bin/awk '{print $1}')
free_kb=$(/bin/df -k "$mount_point" | /usr/bin/awk 'NR==2 {print $4}')
required_kb=$((candidate_kb + 10240))
echo "Spazio libero: ${free_kb} KiB; staging richiesto con margine: ${required_kb} KiB."
(( free_kb >= required_kb )) || { echo 'Rifiuto: spazio insufficiente per uno staging verificabile.'; exit 1; }

/bin/mkdir -p "$backup_root"
/usr/bin/ditto "$mount_point/EFI" "$backup_root/EFI"
/usr/bin/rsync -rcni --delete \
    --exclude '._*' --exclude '.Trashes' --exclude '.Spotlight-V100' \
    "$mount_point/EFI/" "$backup_root/EFI/" | \
    /usr/bin/awk '$1 !~ /^\.[fd]\.\.[Tt]/ { print }' | \
    /usr/bin/tee "$backup_root/backup-compare.txt"
[[ ! -s "$backup_root/backup-compare.txt" ]] || { echo 'Rifiuto: il backup locale non coincide con la ESP.'; exit 1; }
echo "$device" > "$backup_root/source-device.txt"
/usr/bin/shasum -a 256 "$candidate/config.plist" > "$backup_root/candidate-config.sha256"
echo "Backup completo verificato: $backup_root"

/usr/bin/ditto "$candidate" "$mount_point/EFI/$stage_name"
stage_diff=$(mktemp /tmp/s540-stage-diff.XXXXXX)
/usr/bin/rsync -rcni --delete --exclude '._*' "$candidate/" "$mount_point/EFI/$stage_name/" | \
    /usr/bin/awk '$1 !~ /^\.[fd]\.\.[Tt]/ { print }' > "$stage_diff"
if [[ -s "$stage_diff" ]]; then
    echo 'Rifiuto: lo staging interno non coincide con la candidata.'
    /bin/cat "$stage_diff"
    exit 1
fi
"$validator" "$mount_point/EFI/$stage_name/config.plist"
candidate_hash=$(/usr/bin/shasum -a 256 "$candidate/config.plist" | /usr/bin/awk '{print $1}')
stage_hash=$(/usr/bin/shasum -a 256 "$mount_point/EFI/$stage_name/config.plist" | /usr/bin/awk '{print $1}')
[[ "$candidate_hash" == "$stage_hash" ]] || { echo 'Rifiuto: hash config staging differente.'; exit 1; }
echo "Staging verificato: SHA-256 config $stage_hash"

sudo /bin/mv "$mount_point/EFI/OC" "$mount_point/EFI/$previous_name"
old_moved=1
sudo /bin/mv "$mount_point/EFI/$stage_name" "$mount_point/EFI/OC"

live_diff=$(mktemp /tmp/s540-live-diff.XXXXXX)
/usr/bin/rsync -rcni --delete --exclude '._*' "$candidate/" "$mount_point/EFI/OC/" | \
    /usr/bin/awk '$1 !~ /^\.[fd]\.\.[Tt]/ { print }' > "$live_diff"
live_hash=$(/usr/bin/shasum -a 256 "$mount_point/EFI/OC/config.plist" | /usr/bin/awk '{print $1}')
if [[ -s "$live_diff" || "$live_hash" != "$candidate_hash" ]]; then
    echo 'Verifica finale fallita: ripristino la EFI precedente.'
    sudo /bin/mv "$mount_point/EFI/OC" "$mount_point/EFI/OC.S540-FAILED-$timestamp"
    sudo /bin/mv "$mount_point/EFI/$previous_name" "$mount_point/EFI/OC"
    old_moved=0
    exit 1
fi

"$validator" "$mount_point/EFI/OC/config.plist"
/bin/sync
echo "INSTALLAZIONE_OK config_sha256=$live_hash"
echo "ROLLBACK_INTERNO=EFI/$previous_name"
echo "BACKUP_LOCALE=$backup_root"
echo 'EFI/BOOT, rEFInd e Microsoft non sono stati modificati.'
