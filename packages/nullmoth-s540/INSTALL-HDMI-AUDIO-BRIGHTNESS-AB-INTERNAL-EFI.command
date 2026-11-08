#!/bin/zsh

set -euo pipefail

script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)"
workspace="$(CDPATH= cd -- "$script_dir/../.." && pwd -P)"
expected_live_oc="$workspace/_candidates/S540-NullMoth-hdmi-ab/EFI/OC"
candidate_oc="$workspace/_candidates/S540-NullMoth-hdmi-audio-brightness-ab/EFI/OC"
candidate_config="$candidate_oc/config.plist"
candidate_kext="$candidate_oc/Kexts/NMXAudio.kext"
candidate_kext_info="$candidate_kext/Contents/Info.plist"
candidate_kext_binary="$candidate_kext/Contents/MacOS/NMXAudio"
device='/dev/disk0s1'
mount_point='/Volumes/EFI-S540-HDMI-AUDIO-BRIGHTNESS-AB'
validator_release="$workspace/_external/opencore-1.0.8/extracted/Utilities/ocvalidate/ocvalidate"
validator_debug="$workspace/_external/opencore-1.0.8-debug/extracted/Utilities/ocvalidate/ocvalidate"
expected_live_hash='60845fc27d7b27b4aaa0413f90e53e0852a5f0af3b44e4f6f6d729d667ea5705'
expected_candidate_hash='e445fbd3daafef9a1db176872143a590855872cdd63c11af574378a08676533f'
expected_kext_info_hash='ebff8ac2ea5b57f7d6ccbb764f56025213a22a4156df8dd3b8c9c9e64f126d4a'
expected_kext_binary_hash='77e19e244978ce64e4505c4701069edfe609379f91a9c76313b4a27ded4ab07a'
timestamp=$(date '+%Y%m%d-%H%M%S')
backup_root="$workspace/_backups/internal-oc-before-hdmi-audio-brightness-ab-$timestamp"
previous_name="config.S540-HDMI-BEFORE-AUDIO-BRIGHTNESS-$timestamp.plist"
stage_config_name="config.S540-HDMI-AUDIO-BRIGHTNESS-STAGE-$timestamp.plist"
stage_kext_name="NMXAudio.STAGE-$timestamp.kext"
failed_config_name="config.S540-HDMI-AUDIO-BRIGHTNESS-FAILED-$timestamp.plist"
failed_kext_name="NMXAudio.FAILED-$timestamp.kext"
result_file='/tmp/s540-hdmi-audio-brightness-ab-install-result.txt'
mounted=0
previous_moved=0
kext_installed=0

cleanup() {
    local exit_code=$?
    trap - EXIT

    if (( exit_code != 0 && mounted == 1 )); then
        if (( previous_moved == 1 )); then
            echo 'Errore dopo lo scambio del config: ripristino automaticamente il profilo HDMI precedente.'
            if [[ -f "$mount_point/EFI/OC/config.plist" ]]; then
                sudo /bin/mv "$mount_point/EFI/OC/config.plist" \
                    "$mount_point/EFI/$failed_config_name" || true
            fi
            if [[ -f "$mount_point/EFI/$previous_name" ]]; then
                sudo /bin/mv "$mount_point/EFI/$previous_name" \
                    "$mount_point/EFI/OC/config.plist" || true
            fi
        fi

        if (( kext_installed == 1 )) && [[ -d "$mount_point/EFI/OC/Kexts/NMXAudio.kext" ]]; then
            echo 'Rimuovo dal percorso di boot il driver audio installato durante il tentativo fallito.'
            sudo /bin/mv "$mount_point/EFI/OC/Kexts/NMXAudio.kext" \
                "$mount_point/EFI/$failed_kext_name" || true
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

echo 'Lenovo S540: preparazione A/B HDMI + audio HDMI + luminosità sulla EFI interna'
echo 'Verranno aggiunti NMXAudio per il solo controller NVIDIA e applbkl=1 al profilo HDMI già attivo.'
echo 'EFI/BOOT, EFI/Microsoft, EFI/refind e gli altri componenti non verranno modificati.'
echo 'Non verrà eseguito alcun riavvio automatico.'
echo 'Inserisci la password amministratore quando richiesta.'
sudo -v

[[ -d "$expected_live_oc" && -f "$expected_live_oc/config.plist" ]] || {
    echo 'Profilo HDMI di riferimento assente.'
    exit 1
}
[[ -f "$candidate_config" && -d "$candidate_kext" ]] || {
    echo 'Candidata combinata incompleta.'
    exit 1
}
[[ -f "$candidate_kext_info" && -f "$candidate_kext_binary" ]] || {
    echo 'Payload NMXAudio incompleto.'
    exit 1
}
[[ -x "$validator_release" && -x "$validator_debug" ]] || {
    echo 'ocvalidate 1.0.8 assente.'
    exit 1
}

live_reference_hash=$(/usr/bin/shasum -a 256 "$expected_live_oc/config.plist" | /usr/bin/awk '{print $1}')
candidate_hash=$(/usr/bin/shasum -a 256 "$candidate_config" | /usr/bin/awk '{print $1}')
kext_info_hash=$(/usr/bin/shasum -a 256 "$candidate_kext_info" | /usr/bin/awk '{print $1}')
kext_binary_hash=$(/usr/bin/shasum -a 256 "$candidate_kext_binary" | /usr/bin/awk '{print $1}')
[[ "$live_reference_hash" == "$expected_live_hash" ]] || {
    echo "Rifiuto: hash del profilo HDMI di riferimento inatteso ($live_reference_hash)."
    exit 1
}
[[ "$candidate_hash" == "$expected_candidate_hash" ]] || {
    echo "Rifiuto: hash della candidata inatteso ($candidate_hash)."
    exit 1
}
[[ "$kext_info_hash" == "$expected_kext_info_hash" ]] || {
    echo "Rifiuto: hash Info.plist di NMXAudio inatteso ($kext_info_hash)."
    exit 1
}
[[ "$kext_binary_hash" == "$expected_kext_binary_hash" ]] || {
    echo "Rifiuto: hash eseguibile NMXAudio inatteso ($kext_binary_hash)."
    exit 1
}
"$validator_release" "$candidate_config"
"$validator_debug" "$candidate_config"

primary_match=$(/usr/libexec/PlistBuddy -c \
    'Print :IOKitPersonalities:HDAudio:IOPCIPrimaryMatch' "$candidate_kext_info")
class_match=$(/usr/libexec/PlistBuddy -c \
    'Print :IOKitPersonalities:HDAudio:IOPCIClassMatch' "$candidate_kext_info")
[[ "$primary_match" == '0x10fa10de' ]] || {
    echo "Rifiuto: NMXAudio non è limitato al controller NVIDIA atteso ($primary_match)."
    exit 1
}
[[ "$class_match" == '0x04030000&0xffff0000' ]] || {
    echo "Rifiuto: classe PCI NMXAudio inattesa ($class_match)."
    exit 1
}

disk_info=$(/usr/sbin/diskutil info disk0s1)
internal_flag=$(echo "$disk_info" | /usr/bin/awk -F: '/Device Location/ {gsub(/^[[:space:]]+/, "", $2); print $2}')
partition_type=$(echo "$disk_info" | /usr/bin/awk -F: '/Partition Type/ {gsub(/^[[:space:]]+/, "", $2); print $2}')
disk_bytes=$(echo "$disk_info" | /usr/bin/awk '/Disk Size:/ {gsub(/[()]/, "", $5); print $5}')
[[ "$internal_flag" == 'Internal' ]] || {
    echo "Rifiuto: disk0s1 non risulta interno ($internal_flag)."
    exit 1
}
[[ "$partition_type" == 'EFI' ]] || {
    echo "Rifiuto: disk0s1 non è EFI ($partition_type)."
    exit 1
}
[[ "$disk_bytes" == '314572800' ]] || {
    echo "Rifiuto: dimensione ESP inattesa ($disk_bytes byte)."
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

sudo /bin/mkdir "$mount_point"
sudo /sbin/mount_msdos -u "$(id -u)" -g "$(id -g)" "$device" "$mount_point"
mounted=1

live_oc="$mount_point/EFI/OC"
live_config="$live_oc/config.plist"
live_kext="$live_oc/Kexts/NMXAudio.kext"
stage_config="$mount_point/EFI/$stage_config_name"
stage_kext="$mount_point/EFI/$stage_kext_name"
[[ -d "$live_oc" && -f "$live_config" && -d "$live_oc/Kexts" ]] || {
    echo 'Rifiuto: albero EFI/OC attivo incompleto.'
    exit 1
}
[[ ! -e "$live_kext" ]] || {
    echo 'Rifiuto: NMXAudio è già presente nel percorso di boot.'
    exit 1
}
[[ ! -e "$mount_point/EFI/$previous_name" && ! -e "$stage_config" && ! -e "$stage_kext" ]] || {
    echo 'Rifiuto: nome di staging o rollback già presente.'
    exit 1
}

live_hash=$(/usr/bin/shasum -a 256 "$live_config" | /usr/bin/awk '{print $1}')
[[ "$live_hash" == "$expected_live_hash" ]] || {
    echo "Rifiuto: il config attivo non è il profilo HDMI verificato ($live_hash)."
    exit 1
}
"$validator_release" "$live_config"

tree_diff=$(/usr/bin/mktemp /tmp/s540-hdmi-audio-live-tree.XXXXXX)
/usr/bin/rsync -rcni --delete --exclude '._*' \
    "$expected_live_oc/" "$live_oc/" | \
    /usr/bin/awk '$1 !~ /^\.[fd]\.\.[Tt]/ { print }' > "$tree_diff"
if [[ -s "$tree_diff" ]]; then
    echo 'Rifiuto: EFI/OC attivo non coincide esattamente con il profilo HDMI verificato.'
    /bin/cat "$tree_diff"
    exit 1
fi

/bin/mkdir -p "$backup_root"
/usr/bin/ditto "$live_oc" "$backup_root/OC"
backup_diff=$(/usr/bin/mktemp /tmp/s540-hdmi-audio-backup.XXXXXX)
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

/usr/bin/ditto "$candidate_config" "$stage_config"
/usr/bin/ditto "$candidate_kext" "$stage_kext"
stage_config_hash=$(/usr/bin/shasum -a 256 "$stage_config" | /usr/bin/awk '{print $1}')
stage_info_hash=$(/usr/bin/shasum -a 256 "$stage_kext/Contents/Info.plist" | /usr/bin/awk '{print $1}')
stage_binary_hash=$(/usr/bin/shasum -a 256 "$stage_kext/Contents/MacOS/NMXAudio" | /usr/bin/awk '{print $1}')
[[ "$stage_config_hash" == "$expected_candidate_hash" ]] || {
    echo 'Rifiuto: hash del config in staging differente.'
    exit 1
}
[[ "$stage_info_hash" == "$expected_kext_info_hash" ]] || {
    echo 'Rifiuto: hash Info.plist di NMXAudio in staging differente.'
    exit 1
}
[[ "$stage_binary_hash" == "$expected_kext_binary_hash" ]] || {
    echo 'Rifiuto: hash eseguibile NMXAudio in staging differente.'
    exit 1
}
stage_kext_diff=$(/usr/bin/mktemp /tmp/s540-hdmi-audio-stage-kext.XXXXXX)
/usr/bin/rsync -rcni --delete --exclude '._*' "$candidate_kext/" "$stage_kext/" | \
    /usr/bin/awk '$1 !~ /^\.[fd]\.\.[Tt]/ { print }' > "$stage_kext_diff"
if [[ -s "$stage_kext_diff" ]]; then
    echo 'Rifiuto: NMXAudio in staging non coincide con la candidata.'
    /bin/cat "$stage_kext_diff"
    exit 1
fi
"$validator_release" "$stage_config"

sudo /bin/mv "$stage_kext" "$live_kext"
kext_installed=1
sudo /bin/mv "$live_config" "$mount_point/EFI/$previous_name"
previous_moved=1
sudo /bin/mv "$stage_config" "$live_config"

final_config_hash=$(/usr/bin/shasum -a 256 "$live_config" | /usr/bin/awk '{print $1}')
final_info_hash=$(/usr/bin/shasum -a 256 "$live_kext/Contents/Info.plist" | /usr/bin/awk '{print $1}')
final_binary_hash=$(/usr/bin/shasum -a 256 "$live_kext/Contents/MacOS/NMXAudio" | /usr/bin/awk '{print $1}')
[[ "$final_config_hash" == "$expected_candidate_hash" ]] || {
    echo 'Verifica finale hash config fallita.'
    exit 1
}
[[ "$final_info_hash" == "$expected_kext_info_hash" ]] || {
    echo 'Verifica finale hash Info.plist NMXAudio fallita.'
    exit 1
}
[[ "$final_binary_hash" == "$expected_kext_binary_hash" ]] || {
    echo 'Verifica finale hash eseguibile NMXAudio fallita.'
    exit 1
}
"$validator_release" "$live_config"
"$validator_debug" "$live_config"
/bin/sync

echo "INSTALLAZIONE_HDMI_AUDIO_BRIGHTNESS_AB_OK config_sha256=$final_config_hash"
echo "NMXAUDIO_INFO_SHA256=$final_info_hash"
echo "NMXAUDIO_BINARY_SHA256=$final_binary_hash"
echo "ROLLBACK_SU_ESP=EFI/$previous_name"
echo "BACKUP_LOCALE=$backup_root"
echo 'EFI/BOOT, EFI/Microsoft, EFI/refind e tutti gli altri kext sono rimasti invariati.'
echo 'Salva il lavoro e riavvia con il monitor HDMI già acceso e collegato.'
