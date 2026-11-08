#!/bin/zsh

set -euo pipefail

script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)"
workspace="$(CDPATH= cd -- "$script_dir/../.." && pwd -P)"
candidate_oc="$workspace/_candidates/S540-NullMoth-hdmi-ab/EFI/OC"
candidate_config="$candidate_oc/config.plist"
device='/dev/disk0s1'
mount_point='/Volumes/EFI-S540-HDMI-AB'
validator_release="$workspace/_external/opencore-1.0.8/extracted/Utilities/ocvalidate/ocvalidate"
validator_debug="$workspace/_external/opencore-1.0.8-debug/extracted/Utilities/ocvalidate/ocvalidate"
expected_live_hash='d0cb59c8677850c1166ab08691a83bcd7db71589019277eba0d42c970aab5fac'
expected_candidate_hash='60845fc27d7b27b4aaa0413f90e53e0852a5f0af3b44e4f6f6d729d667ea5705'
timestamp=$(date '+%Y%m%d-%H%M%S')
backup_root="$workspace/_backups/internal-oc-before-hdmi-ab-$timestamp"
previous_name="config.S540-HEADLESS-BEFORE-HDMI-AB-$timestamp.plist"
stage_name="config.S540-HDMI-AB-STAGE-$timestamp.plist"
failed_name="config.S540-HDMI-AB-FAILED-$timestamp.plist"
result_file='/tmp/s540-hdmi-ab-install-result.txt'
mounted=0
swapped=0

cleanup() {
    local exit_code=$?
    trap - EXIT

    if (( exit_code != 0 && mounted == 1 && swapped == 1 )); then
        echo 'Errore dopo lo scambio: ripristino automaticamente il config headless.'
        if [[ -f "$mount_point/EFI/OC/config.plist" ]]; then
            sudo /bin/mv "$mount_point/EFI/OC/config.plist" "$mount_point/EFI/$failed_name" || true
        fi
        if [[ -f "$mount_point/EFI/$previous_name" ]]; then
            sudo /bin/mv "$mount_point/EFI/$previous_name" "$mount_point/EFI/OC/config.plist" || true
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

/bin/rm -f "$result_file"
exec > >(tee "$result_file") 2>&1

echo 'Lenovo S540: preparazione A/B HDMI sulla EFI interna'
echo 'Verrà sostituito soltanto EFI/OC/config.plist.'
echo 'Il profilo abilita nvfb=1 e quattro testate NVRMFB; non riavvia automaticamente.'
echo 'Inserisci la password amministratore quando richiesta.'
sudo -v

[[ -f "$candidate_config" ]] || { echo "Candidata assente: $candidate_config"; exit 1; }
[[ -x "$validator_release" && -x "$validator_debug" ]] || { echo 'ocvalidate 1.0.8 assente.'; exit 1; }

candidate_hash=$(/usr/bin/shasum -a 256 "$candidate_config" | /usr/bin/awk '{print $1}')
[[ "$candidate_hash" == "$expected_candidate_hash" ]] || {
    echo "Rifiuto: hash candidata inatteso ($candidate_hash)."
    exit 1
}
"$validator_release" "$candidate_config"
"$validator_debug" "$candidate_config"

internal_flag=$(/usr/sbin/diskutil info disk0s1 | /usr/bin/awk -F: '/Device Location/ {gsub(/^[[:space:]]+/, "", $2); print $2}')
partition_type=$(/usr/sbin/diskutil info disk0s1 | /usr/bin/awk -F: '/Partition Type/ {gsub(/^[[:space:]]+/, "", $2); print $2}')
disk_bytes=$(/usr/sbin/diskutil info disk0s1 | /usr/bin/awk '/Disk Size:/ {gsub(/[()]/, "", $5); print $5}')
[[ "$internal_flag" == 'Internal' ]] || { echo "Rifiuto: disk0s1 non risulta interno ($internal_flag)."; exit 1; }
[[ "$partition_type" == 'EFI' ]] || { echo "Rifiuto: disk0s1 non è EFI ($partition_type)."; exit 1; }
[[ "$disk_bytes" == '314572800' ]] || { echo "Rifiuto: dimensione ESP inattesa ($disk_bytes byte)."; exit 1; }

if /sbin/mount | /usr/bin/grep -q '^/dev/disk0s1 '; then
    echo 'Rifiuto: disk0s1 è già montato.'
    exit 1
fi
[[ ! -e "$mount_point" ]] || { echo "Rifiuto: mount point già presente: $mount_point"; exit 1; }

sudo /bin/mkdir "$mount_point"
sudo /sbin/mount_msdos -u "$(id -u)" -g "$(id -g)" "$device" "$mount_point"
mounted=1

live_oc="$mount_point/EFI/OC"
live_config="$live_oc/config.plist"
[[ -d "$live_oc" && -f "$live_config" ]] || { echo 'Rifiuto: EFI/OC/config.plist assente.'; exit 1; }
[[ ! -e "$mount_point/EFI/$previous_name" && ! -e "$live_oc/$stage_name" ]] || {
    echo 'Rifiuto: nome di staging o rollback già presente.'
    exit 1
}

live_hash=$(/usr/bin/shasum -a 256 "$live_config" | /usr/bin/awk '{print $1}')
[[ "$live_hash" == "$expected_live_hash" ]] || {
    echo "Rifiuto: il config attivo non è il profilo headless finale atteso ($live_hash)."
    exit 1
}
"$validator_release" "$live_config"

tree_diff=$(/usr/bin/mktemp /tmp/s540-hdmi-tree.XXXXXX)
/usr/bin/rsync -rcni --delete --exclude '._*' --exclude 'config.plist' \
    "$candidate_oc/" "$live_oc/" | /usr/bin/awk '$1 !~ /^\.[fd]\.\.[Tt]/ { print }' > "$tree_diff"
if [[ -s "$tree_diff" ]]; then
    echo 'Rifiuto: i file EFI attivi diversi da config.plist non coincidono con la candidata.'
    /bin/cat "$tree_diff"
    exit 1
fi

/bin/mkdir -p "$backup_root"
/usr/bin/ditto "$live_oc" "$backup_root/OC"
backup_diff=$(/usr/bin/mktemp /tmp/s540-hdmi-backup.XXXXXX)
/usr/bin/rsync -rcni --delete --exclude '._*' "$live_oc/" "$backup_root/OC/" | \
    /usr/bin/awk '$1 !~ /^\.[fd]\.\.[Tt]/ { print }' > "$backup_diff"
if [[ -s "$backup_diff" ]]; then
    echo 'Rifiuto: il backup locale non coincide con EFI/OC.'
    /bin/cat "$backup_diff"
    exit 1
fi
echo "$device" > "$backup_root/source-device.txt"
/usr/bin/shasum -a 256 "$live_config" > "$backup_root/active-config-before.sha256"
echo "Backup verificato: $backup_root"

/usr/bin/ditto "$candidate_config" "$live_oc/$stage_name"
stage_hash=$(/usr/bin/shasum -a 256 "$live_oc/$stage_name" | /usr/bin/awk '{print $1}')
[[ "$stage_hash" == "$expected_candidate_hash" ]] || { echo 'Rifiuto: hash staging differente.'; exit 1; }
"$validator_release" "$live_oc/$stage_name"

sudo /bin/mv "$live_config" "$mount_point/EFI/$previous_name"
sudo /bin/mv "$live_oc/$stage_name" "$live_config"
swapped=1

final_hash=$(/usr/bin/shasum -a 256 "$live_config" | /usr/bin/awk '{print $1}')
[[ "$final_hash" == "$expected_candidate_hash" ]] || { echo 'Verifica finale hash fallita.'; exit 1; }
"$validator_release" "$live_config"
/bin/sync

echo "INSTALLAZIONE_HDMI_AB_OK config_sha256=$final_hash"
echo "ROLLBACK_SU_ESP=EFI/$previous_name"
echo "BACKUP_LOCALE=$backup_root"
echo 'EFI/BOOT, EFI/Microsoft, EFI/refind e tutti i kext sono rimasti invariati.'
echo 'Salva il lavoro e riavvia con il monitor HDMI già acceso e collegato.'
