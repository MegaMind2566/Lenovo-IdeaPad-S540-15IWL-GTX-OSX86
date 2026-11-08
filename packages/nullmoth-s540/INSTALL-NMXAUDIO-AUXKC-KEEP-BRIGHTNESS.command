#!/bin/zsh

set -euo pipefail

script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)"
workspace="$(CDPATH= cd -- "$script_dir/../.." && pwd -P)"
result_file='/tmp/s540-nmxaudio-auxkc-install-result.txt'

if [[ "$(id -u)" -ne 0 ]]; then
    /bin/rm -f "$result_file"
    exec > >(tee "$result_file") 2>&1
    echo 'Lenovo S540: installazione mirata NMXAudio nella Auxiliary Kernel Collection.'
    echo 'Il profilo HDMI e la regolazione della luminosità resteranno attivi.'
    echo 'Non verrà eseguito alcun riavvio automatico.'
    echo 'Inserisci la password amministratore quando richiesta.'
    exec sudo /usr/bin/env \
        S540_CALLER_UID="$(id -u)" \
        S540_CALLER_GID="$(id -g)" \
        /bin/zsh "$0" --root
fi

[[ "${1:-}" == '--root' ]] || {
    echo 'Rifiuto: esecuzione root non autenticata dal wrapper.'
    exit 1
}
caller_uid="${S540_CALLER_UID:-}"
caller_gid="${S540_CALLER_GID:-}"
[[ "$caller_uid" =~ ^[0-9]+$ && "$caller_gid" =~ ^[0-9]+$ && "$caller_uid" -ne 0 ]] || {
    echo 'Rifiuto: identità dell’utente chiamante non valida.'
    exit 1
}

device='/dev/disk0s1'
mount_point='/Volumes/EFI-S540-NMXAUDIO-AUXKC'
current_efi_oc="$workspace/_candidates/S540-NullMoth-hdmi-audio-brightness-ab/EFI/OC"
candidate_efi_oc="$workspace/_candidates/S540-NullMoth-hdmi-brightness-auxaudio/EFI/OC"
candidate_config="$candidate_efi_oc/config.plist"
source_nmx="$workspace/_candidates/S540-NullMoth-hdmi-audio-brightness-ab/EFI/OC/Kexts/NMXAudio.kext"
validator_release="$workspace/_external/opencore-1.0.8/extracted/Utilities/ocvalidate/ocvalidate"
validator_debug="$workspace/_external/opencore-1.0.8-debug/extracted/Utilities/ocvalidate/ocvalidate"
system_extensions='/Library/Extensions'
system_nmx="$system_extensions/NMXAudio.kext"
system_kc='/Library/KernelCollections/AuxiliaryKernelExtensions.kc'
boot_kc='/System/Library/KernelCollections/BootKernelExtensions.kc'
system_base_kc='/System/Library/KernelCollections/SystemKernelExtensions.kc'
kernel='/System/Library/Kernels/kernel'
expected_live_config_hash='e445fbd3daafef9a1db176872143a590855872cdd63c11af574378a08676533f'
expected_candidate_config_hash='0c4c6bece507ba34f0e5d0b293e758a9436d47ad34c5e87ef786fd15d0a4b6e1'
expected_nmx_info_hash='ebff8ac2ea5b57f7d6ccbb764f56025213a22a4156df8dd3b8c9c9e64f126d4a'
expected_nmx_binary_hash='77e19e244978ce64e4505c4701069edfe609379f91a9c76313b4a27ded4ab07a'
expected_current_kc_hash='9b8b03683bf356e254c93e449b89f6bf16adc27a91db0b98be7a382b40d8f7a9'
timestamp=$(date '+%Y%m%d-%H%M%S')
temporary_root=$(/usr/bin/mktemp -d /var/tmp/s540-nmxaudio-auxkc.XXXXXX)
local_backup="$workspace/_backups/before-nmxaudio-auxkc-$timestamp"
system_backup="/Library/NullMoth/backup-nmxaudio-s540-$timestamp"
previous_config_name="config.S540-HDMI-BRIGHTNESS-BEFORE-AUXAUDIO-$timestamp.plist"
previous_kext_name="NMXAudio.OC-BEFORE-AUXAUDIO-$timestamp.kext"
failed_config_name="config.S540-AUXAUDIO-FAILED-$timestamp.plist"
system_kc_stage="$system_kc.s540-nmxaudio-stage-$timestamp"
mounted=0
system_nmx_installed=0
system_kc_replaced=0
efi_kext_moved=0
efi_config_moved=0
success=0

cleanup() {
    local exit_code=$?
    trap - EXIT HUP INT TERM

    if (( success == 0 )); then
        echo 'Installazione non completata: ripristino gli elementi già scambiati.'

        if (( system_kc_replaced == 1 )) && [[ -f "$system_backup/AuxiliaryKernelExtensions.kc" ]]; then
            /usr/bin/ditto "$system_backup/AuxiliaryKernelExtensions.kc" \
                "$system_kc.restore-$timestamp"
            /usr/sbin/chown root:wheel "$system_kc.restore-$timestamp"
            /bin/chmod "$(/usr/bin/stat -f '%Lp' "$system_backup/AuxiliaryKernelExtensions.kc")" \
                "$system_kc.restore-$timestamp"
            /bin/mv -f "$system_kc.restore-$timestamp" "$system_kc" || true
        fi
        if (( system_nmx_installed == 1 )) && [[ -d "$system_nmx" ]]; then
            /bin/mv "$system_nmx" "$system_backup/NMXAudio.failed-install.kext" || true
        fi

        if (( mounted == 1 )); then
            live_oc="$mount_point/EFI/OC"
            if (( efi_config_moved == 1 )); then
                if [[ -f "$live_oc/config.plist" ]]; then
                    /bin/mv "$live_oc/config.plist" "$mount_point/EFI/$failed_config_name" || true
                fi
                if [[ -f "$mount_point/EFI/$previous_config_name" ]]; then
                    /bin/mv "$mount_point/EFI/$previous_config_name" "$live_oc/config.plist" || true
                fi
            fi
            if (( efi_kext_moved == 1 )) && [[ -d "$mount_point/EFI/$previous_kext_name" ]]; then
                /bin/mv "$mount_point/EFI/$previous_kext_name" "$live_oc/Kexts/NMXAudio.kext" || true
            fi
        fi
    fi

    [[ ! -e "$system_kc_stage" ]] || /bin/rm -f "$system_kc_stage" || true
    if (( mounted == 1 )); then
        /bin/sync
        /sbin/umount "$mount_point" >/dev/null 2>&1 || \
            /usr/sbin/diskutil unmount disk0s1 >/dev/null 2>&1 || true
    fi
    /bin/rmdir "$mount_point" >/dev/null 2>&1 || true
    case "$temporary_root" in
        /var/tmp/s540-nmxaudio-auxkc.*) /bin/rm -rf "$temporary_root" ;;
        *) echo "ATTENZIONE: directory temporanea inattesa non rimossa: $temporary_root" ;;
    esac
    exit "$exit_code"
}
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

[[ -d "$source_nmx" && -f "$candidate_config" && -d "$current_efi_oc" ]] || {
    echo 'Rifiuto: sorgenti candidate incomplete.'
    exit 1
}
[[ -x "$validator_release" && -x "$validator_debug" ]] || {
    echo 'Rifiuto: ocvalidate 1.0.8 assente.'
    exit 1
}
[[ -f "$system_kc" && -f "$boot_kc" && -f "$system_base_kc" ]] || {
    echo 'Rifiuto: raccolte kernel di sistema incomplete.'
    exit 1
}
[[ ! -e "$system_nmx" ]] || {
    echo 'Rifiuto: NMXAudio è già presente in /Library/Extensions.'
    exit 1
}

candidate_config_hash=$(/usr/bin/shasum -a 256 "$candidate_config" | /usr/bin/awk '{print $1}')
source_info_hash=$(/usr/bin/shasum -a 256 "$source_nmx/Contents/Info.plist" | /usr/bin/awk '{print $1}')
source_binary_hash=$(/usr/bin/shasum -a 256 "$source_nmx/Contents/MacOS/NMXAudio" | /usr/bin/awk '{print $1}')
current_kc_hash=$(/usr/bin/shasum -a 256 "$system_kc" | /usr/bin/awk '{print $1}')
[[ "$candidate_config_hash" == "$expected_candidate_config_hash" ]] || {
    echo "Rifiuto: hash config candidata inatteso ($candidate_config_hash)."
    exit 1
}
[[ "$source_info_hash" == "$expected_nmx_info_hash" && "$source_binary_hash" == "$expected_nmx_binary_hash" ]] || {
    echo "Rifiuto: hash sorgente NMXAudio inattesi ($source_info_hash, $source_binary_hash)."
    exit 1
}
[[ "$current_kc_hash" == "$expected_current_kc_hash" ]] || {
    echo "Rifiuto: Auxiliary KC corrente cambiata dopo il preflight ($current_kc_hash)."
    exit 1
}
"$validator_release" "$candidate_config"
"$validator_debug" "$candidate_config"
if /usr/libexec/PlistBuddy -c 'Print :Kernel:Add' "$candidate_config" | /usr/bin/grep -q NMXAudio; then
    echo 'Rifiuto: la config finale contiene ancora NMXAudio in Kernel.Add.'
    exit 1
fi

echo '1/5 — Creo una copia root privata e verificata del driver audio.'
private_nmx="$temporary_root/NMXAudio.kext"
/usr/bin/ditto "$source_nmx" "$private_nmx"
/usr/sbin/chown -R root:wheel "$private_nmx"
/bin/chmod -R go-w,a+rX "$private_nmx"
private_info_hash=$(/usr/bin/shasum -a 256 "$private_nmx/Contents/Info.plist" | /usr/bin/awk '{print $1}')
private_binary_hash=$(/usr/bin/shasum -a 256 "$private_nmx/Contents/MacOS/NMXAudio" | /usr/bin/awk '{print $1}')
[[ "$private_info_hash" == "$expected_nmx_info_hash" && "$private_binary_hash" == "$expected_nmx_binary_hash" ]] || {
    echo 'Rifiuto: la copia root privata di NMXAudio non coincide.'
    exit 1
}

echo '2/5 — Costruisco e ispeziono la nuova Auxiliary Kernel Collection.'
repo="$temporary_root/repo"
/bin/mkdir "$repo"
for extension in "$system_extensions"/*.kext; do
    /usr/bin/ditto "$extension" "$repo/$(/usr/bin/basename "$extension")"
done
/usr/bin/ditto "$private_nmx" "$repo/NMXAudio.kext"
/usr/sbin/chown -R root:wheel "$repo"
/bin/chmod -R go-w "$repo"
old_inspect="$temporary_root/current-kc-inspect.txt"
new_inspect="$temporary_root/new-kc-inspect.txt"
old_ids="$temporary_root/current-kc-ids.txt"
new_ids="$temporary_root/new-kc-ids.txt"
new_kc="$temporary_root/AuxiliaryKernelExtensions.kc"
kmutil_log="$temporary_root/kmutil-create.log"
/usr/bin/kmutil inspect -a x86_64 -A "$system_kc" > "$old_inspect"
kargs=(--allow-missing-kdk)
[[ ! -f "$kernel" ]] || kargs+=(--kernel "$kernel")
if ! /usr/bin/kmutil create -n aux --volume-root / "${kargs[@]}" \
    -B "$boot_kc" -S "$system_base_kc" --repository "$repo" \
    -A "$new_kc" -z > "$kmutil_log" 2>&1; then
    /usr/bin/tail -n 80 "$kmutil_log"
    echo 'Rifiuto: costruzione della nuova Auxiliary KC fallita.'
    exit 1
fi
[[ -s "$new_kc" ]] || {
    echo 'Rifiuto: la nuova Auxiliary KC è vuota.'
    exit 1
}
/usr/bin/kmutil inspect -a x86_64 -A "$new_kc" > "$new_inspect"
/usr/bin/awk -F '\t' '$1 ~ /^[A-Za-z0-9_.-]+$/ {print $1}' "$old_inspect" | /usr/bin/sort -u > "$old_ids"
/usr/bin/awk -F '\t' '$1 ~ /^[A-Za-z0-9_.-]+$/ {print $1}' "$new_inspect" | /usr/bin/sort -u > "$new_ids"
while IFS= read -r bundle_id; do
    /usr/bin/grep -Fxq "$bundle_id" "$new_ids" || {
        echo "Rifiuto: la nuova KC non conserva $bundle_id."
        exit 1
    }
done < "$old_ids"
/usr/bin/grep -Fxq 'com.nullmoth.NMXAudio' "$new_ids" || {
    echo 'Rifiuto: kmutil non ha inserito com.nullmoth.NMXAudio nella nuova KC.'
    exit 1
}
new_kc_hash=$(/usr/bin/shasum -a 256 "$new_kc" | /usr/bin/awk '{print $1}')
echo "Nuova Auxiliary KC verificata: $new_kc_hash"

echo '3/5 — Verifico la ESP e creo backup persistenti.'
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
/bin/mkdir "$mount_point"
/sbin/mount_msdos -u "$caller_uid" -g "$caller_gid" "$device" "$mount_point"
mounted=1
live_oc="$mount_point/EFI/OC"
live_config="$live_oc/config.plist"
live_efi_nmx="$live_oc/Kexts/NMXAudio.kext"
[[ -f "$live_config" && -d "$live_efi_nmx" ]] || {
    echo 'Rifiuto: profilo EFI combinato non presente.'
    exit 1
}
live_config_hash=$(/usr/bin/shasum -a 256 "$live_config" | /usr/bin/awk '{print $1}')
live_info_hash=$(/usr/bin/shasum -a 256 "$live_efi_nmx/Contents/Info.plist" | /usr/bin/awk '{print $1}')
live_binary_hash=$(/usr/bin/shasum -a 256 "$live_efi_nmx/Contents/MacOS/NMXAudio" | /usr/bin/awk '{print $1}')
[[ "$live_config_hash" == "$expected_live_config_hash" ]] || {
    echo "Rifiuto: config EFI attivo inatteso ($live_config_hash)."
    exit 1
}
[[ "$live_info_hash" == "$expected_nmx_info_hash" && "$live_binary_hash" == "$expected_nmx_binary_hash" ]] || {
    echo 'Rifiuto: NMXAudio sulla EFI non coincide con il payload verificato.'
    exit 1
}
live_tree_diff="$temporary_root/live-efi-tree.diff"
/usr/bin/rsync -rcni --delete --exclude '._*' "$current_efi_oc/" "$live_oc/" | \
    /usr/bin/awk '$1 !~ /^\.[fd]\.\.[Tt]/ { print }' > "$live_tree_diff"
[[ ! -s "$live_tree_diff" ]] || {
    echo 'Rifiuto: EFI/OC attivo non coincide con il profilo combinato verificato.'
    /bin/cat "$live_tree_diff"
    exit 1
}

/bin/mkdir -p "$local_backup"
/usr/bin/ditto "$live_oc" "$local_backup/OC"
/usr/bin/rsync -rcni --delete --exclude '._*' "$live_oc/" "$local_backup/OC/" | \
    /usr/bin/awk '$1 !~ /^\.[fd]\.\.[Tt]/ { print }' > "$temporary_root/local-backup.diff"
[[ ! -s "$temporary_root/local-backup.diff" ]] || {
    echo 'Rifiuto: backup locale EFI non verificabile.'
    exit 1
}
/bin/mkdir -p "$system_backup"
/usr/bin/ditto "$system_kc" "$system_backup/AuxiliaryKernelExtensions.kc"
backup_kc_hash=$(/usr/bin/shasum -a 256 "$system_backup/AuxiliaryKernelExtensions.kc" | /usr/bin/awk '{print $1}')
[[ "$backup_kc_hash" == "$expected_current_kc_hash" ]] || {
    echo 'Rifiuto: backup della Auxiliary KC non coincide.'
    exit 1
}
/usr/bin/ditto "$old_inspect" "$system_backup/auxkc-before-inspect.txt"
/usr/bin/ditto "$new_inspect" "$system_backup/auxkc-after-inspect.txt"
/usr/bin/ditto "$kmutil_log" "$system_backup/kmutil-create.log"
/usr/bin/printf '%s\n' 'NMXAudio.kext was absent before this installation.' > "$system_backup/NMXAudio-before.txt"
/usr/bin/printf '%s\n' "$system_backup" > "$local_backup/system-backup-path.txt"
/usr/bin/shasum -a 256 "$live_config" > "$local_backup/active-config-before.sha256"
/usr/bin/shasum -a 256 "$system_kc" > "$local_backup/auxkc-before.sha256"
/usr/sbin/chown -R "$caller_uid:$caller_gid" "$local_backup"
echo "Backup EFI verificato: $local_backup"
echo "Backup KC verificato: $system_backup"

stage_config="$mount_point/EFI/config.S540-HDMI-BRIGHTNESS-AUXAUDIO-STAGE-$timestamp.plist"
/usr/bin/ditto "$candidate_config" "$stage_config"
stage_config_hash=$(/usr/bin/shasum -a 256 "$stage_config" | /usr/bin/awk '{print $1}')
[[ "$stage_config_hash" == "$expected_candidate_config_hash" ]] || {
    echo 'Rifiuto: hash config EFI in staging differente.'
    exit 1
}
"$validator_release" "$stage_config"

echo '4/5 — Pubblico NMXAudio e la nuova Auxiliary KC.'
/bin/mv "$private_nmx" "$system_nmx"
system_nmx_installed=1
/usr/sbin/chown -R root:wheel "$system_nmx"
/bin/chmod -R go-w,a+rX "$system_nmx"
live_new_kc="$temporary_root/AuxiliaryKernelExtensions-live.kc"
live_inspect="$temporary_root/live-kc-inspect.txt"
live_ids="$temporary_root/live-kc-ids.txt"
live_kmutil_log="$temporary_root/kmutil-create-live.log"
if ! /usr/bin/kmutil create -n aux --volume-root / "${kargs[@]}" \
    -B "$boot_kc" -S "$system_base_kc" --repository "$system_extensions" \
    -A "$live_new_kc" -z > "$live_kmutil_log" 2>&1; then
    /usr/bin/tail -n 80 "$live_kmutil_log"
    echo 'Rifiuto: costruzione della Auxiliary KC dai percorsi di sistema fallita.'
    exit 1
fi
/usr/bin/kmutil inspect -a x86_64 -A "$live_new_kc" > "$live_inspect"
/usr/bin/awk -F '\t' '$1 ~ /^[A-Za-z0-9_.-]+$/ {print $1}' "$live_inspect" | /usr/bin/sort -u > "$live_ids"
while IFS= read -r bundle_id; do
    /usr/bin/grep -Fxq "$bundle_id" "$live_ids" || {
        echo "Rifiuto: la KC finale non conserva $bundle_id."
        exit 1
    }
done < "$old_ids"
/usr/bin/grep -Fxq 'com.nullmoth.NMXAudio' "$live_ids" || {
    echo 'Rifiuto: NMXAudio assente dalla KC finale.'
    exit 1
}
/usr/bin/grep -q $'^com\\.nullmoth\\.NMXAudio\t1\\.0\\.0\t/Library/Extensions/NMXAudio\\.kext' "$live_inspect" || {
    echo 'Rifiuto: la KC finale non registra il percorso reale di NMXAudio.'
    exit 1
}
/usr/bin/ditto "$live_inspect" "$system_backup/auxkc-live-inspect.txt"
/usr/bin/ditto "$live_kmutil_log" "$system_backup/kmutil-create-live.log"
live_new_kc_hash=$(/usr/bin/shasum -a 256 "$live_new_kc" | /usr/bin/awk '{print $1}')
/usr/bin/ditto "$live_new_kc" "$system_kc_stage"
/usr/sbin/chown root:wheel "$system_kc_stage"
/bin/chmod "$(/usr/bin/stat -f '%Lp' "$system_kc")" "$system_kc_stage"
stage_kc_hash=$(/usr/bin/shasum -a 256 "$system_kc_stage" | /usr/bin/awk '{print $1}')
[[ "$stage_kc_hash" == "$live_new_kc_hash" ]] || {
    echo 'Verifica hash della KC di sistema in staging fallita.'
    exit 1
}
/bin/mv -f "$system_kc_stage" "$system_kc"
system_kc_replaced=1

echo '5/5 — Tolgo la copia EFI duplicata e attivo il config finale.'
/bin/mv "$live_efi_nmx" "$mount_point/EFI/$previous_kext_name"
efi_kext_moved=1
/bin/mv "$live_config" "$mount_point/EFI/$previous_config_name"
efi_config_moved=1
/bin/mv "$stage_config" "$live_config"

final_config_hash=$(/usr/bin/shasum -a 256 "$live_config" | /usr/bin/awk '{print $1}')
final_info_hash=$(/usr/bin/shasum -a 256 "$system_nmx/Contents/Info.plist" | /usr/bin/awk '{print $1}')
final_binary_hash=$(/usr/bin/shasum -a 256 "$system_nmx/Contents/MacOS/NMXAudio" | /usr/bin/awk '{print $1}')
final_kc_hash=$(/usr/bin/shasum -a 256 "$system_kc" | /usr/bin/awk '{print $1}')
[[ "$final_config_hash" == "$expected_candidate_config_hash" ]] || {
    echo 'Verifica finale config EFI fallita.'
    exit 1
}
[[ "$final_info_hash" == "$expected_nmx_info_hash" && "$final_binary_hash" == "$expected_nmx_binary_hash" ]] || {
    echo 'Verifica finale NMXAudio di sistema fallita.'
    exit 1
}
[[ "$final_kc_hash" == "$live_new_kc_hash" ]] || {
    echo 'Verifica finale Auxiliary KC fallita.'
    exit 1
}
[[ ! -e "$live_oc/Kexts/NMXAudio.kext" ]] || {
    echo 'Verifica finale: copia EFI NMXAudio ancora presente.'
    exit 1
}
"$validator_release" "$live_config"
"$validator_debug" "$live_config"
/usr/bin/kmutil inspect -a x86_64 -A "$system_kc" > "$temporary_root/final-kc-inspect.txt"
/usr/bin/grep -q '^com\.nullmoth\.NMXAudio[[:space:]]' "$temporary_root/final-kc-inspect.txt" || {
    echo 'Verifica finale: NMXAudio assente dalla Auxiliary KC pubblicata.'
    exit 1
}
/bin/sync
success=1

policy='non ancora approvato o record non leggibile'
if [[ -x /usr/bin/sqlite3 && -f /var/db/SystemPolicyConfiguration/KextPolicy ]]; then
    allowed=$(/usr/bin/sqlite3 /var/db/SystemPolicyConfiguration/KextPolicy \
        "select allowed from kext_policy where ifnull(team_id,'')='' and bundle_id='com.nullmoth.NMXAudio'" 2>/dev/null || true)
    [[ "$allowed" != 1 ]] || policy='già approvato'
fi
echo "INSTALLAZIONE_NMXAUDIO_AUXKC_OK config_sha256=$final_config_hash"
echo "AUXKC_SHA256=$final_kc_hash"
echo "NMXAUDIO_INFO_SHA256=$final_info_hash"
echo "NMXAUDIO_BINARY_SHA256=$final_binary_hash"
echo "KEXT_POLICY=$policy"
echo "ROLLBACK_CONFIG_ESP=EFI/$previous_config_name"
echo "ROLLBACK_KEXT_ESP=EFI/$previous_kext_name"
echo "BACKUP_EFI_LOCALE=$local_backup"
echo "BACKUP_SISTEMA=$system_backup"
echo 'Installazione verificata. Se macOS lo richiede, autorizza NMXAudio in Privacy e Sicurezza.'
echo 'Salva il lavoro e riavvia con il televisore HDMI acceso e collegato.'
