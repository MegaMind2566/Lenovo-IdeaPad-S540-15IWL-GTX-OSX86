#!/bin/zsh

set -euo pipefail

result_file='/tmp/s540-nmxaudio-live-paths-result.txt'
if [[ "$(id -u)" -ne 0 ]]; then
    /bin/rm -f "$result_file"
    exec > >(tee "$result_file") 2>&1
    echo 'Correzione metadati Auxiliary KC: ricostruzione da /Library/Extensions.'
    echo 'EFI e boot-args non verranno modificati. Non verrà eseguito alcun riavvio.'
    echo 'Inserisci la password amministratore quando richiesta.'
    exec sudo /bin/zsh "$0" --root
fi
[[ "${1:-}" == '--root' ]] || {
    echo 'Rifiuto: esecuzione root non autenticata dal wrapper.'
    exit 1
}

system_extensions='/Library/Extensions'
system_nmx="$system_extensions/NMXAudio.kext"
system_kc='/Library/KernelCollections/AuxiliaryKernelExtensions.kc'
boot_kc='/System/Library/KernelCollections/BootKernelExtensions.kc'
system_base_kc='/System/Library/KernelCollections/SystemKernelExtensions.kc'
kernel='/System/Library/Kernels/kernel'
system_backup='/Library/NullMoth/backup-nmxaudio-s540-20261108-171234'
expected_current_kc_hash='ea6c418058d4d140dd2553d436a54c1eaa78d22499a28a72994420b72f9d2ae9'
expected_original_kc_hash='9b8b03683bf356e254c93e449b89f6bf16adc27a91db0b98be7a382b40d8f7a9'
expected_info_hash='ebff8ac2ea5b57f7d6ccbb764f56025213a22a4156df8dd3b8c9c9e64f126d4a'
expected_binary_hash='77e19e244978ce64e4505c4701069edfe609379f91a9c76313b4a27ded4ab07a'
timestamp=$(date '+%Y%m%d-%H%M%S')
temporary_root=$(/usr/bin/mktemp -d /var/tmp/s540-nmxaudio-live-paths.XXXXXX)
stage_kc="$system_kc.s540-live-paths-$timestamp"
published=0
success=0

cleanup() {
    local exit_code=$?
    trap - EXIT HUP INT TERM
    if (( success == 0 && published == 1 )); then
        echo 'Correzione non completata: ripristino la KC precedente.'
        if [[ -f "$system_backup/AuxiliaryKernelExtensions.pre-live-path-rebuild.kc" ]]; then
            /usr/bin/ditto "$system_backup/AuxiliaryKernelExtensions.pre-live-path-rebuild.kc" \
                "$system_kc.restore-$timestamp"
            /usr/sbin/chown root:wheel "$system_kc.restore-$timestamp"
            /bin/chmod "$(/usr/bin/stat -f '%Lp' "$system_backup/AuxiliaryKernelExtensions.pre-live-path-rebuild.kc")" \
                "$system_kc.restore-$timestamp"
            /bin/mv -f "$system_kc.restore-$timestamp" "$system_kc" || true
        fi
    fi
    [[ ! -e "$stage_kc" ]] || /bin/rm -f "$stage_kc" || true
    case "$temporary_root" in
        /var/tmp/s540-nmxaudio-live-paths.*) /bin/rm -rf "$temporary_root" ;;
        *) echo "ATTENZIONE: directory temporanea inattesa non rimossa: $temporary_root" ;;
    esac
    exit "$exit_code"
}
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

[[ -f "$system_kc" && -d "$system_nmx" && -d "$system_backup" ]] || {
    echo 'Rifiuto: stato installato o backup incompleto.'
    exit 1
}
current_hash=$(/usr/bin/shasum -a 256 "$system_kc" | /usr/bin/awk '{print $1}')
original_hash=$(/usr/bin/shasum -a 256 "$system_backup/AuxiliaryKernelExtensions.kc" | /usr/bin/awk '{print $1}')
info_hash=$(/usr/bin/shasum -a 256 "$system_nmx/Contents/Info.plist" | /usr/bin/awk '{print $1}')
binary_hash=$(/usr/bin/shasum -a 256 "$system_nmx/Contents/MacOS/NMXAudio" | /usr/bin/awk '{print $1}')
[[ "$current_hash" == "$expected_current_kc_hash" ]] || {
    echo "Rifiuto: KC corrente inattesa ($current_hash)."
    exit 1
}
[[ "$original_hash" == "$expected_original_kc_hash" ]] || {
    echo "Rifiuto: backup originale KC inatteso ($original_hash)."
    exit 1
}
[[ "$info_hash" == "$expected_info_hash" && "$binary_hash" == "$expected_binary_hash" ]] || {
    echo 'Rifiuto: NMXAudio installato non coincide con il payload verificato.'
    exit 1
}

echo 'Costruisco la KC finale dalla directory reale delle estensioni.'
old_inspect="$temporary_root/current-inspect.txt"
new_inspect="$temporary_root/live-inspect.txt"
old_ids="$temporary_root/current-ids.txt"
new_ids="$temporary_root/live-ids.txt"
new_kc="$temporary_root/AuxiliaryKernelExtensions.kc"
kmutil_log="$temporary_root/kmutil-create-live.log"
/usr/bin/kmutil inspect -a x86_64 -A "$system_kc" > "$old_inspect"
kargs=(--allow-missing-kdk)
[[ ! -f "$kernel" ]] || kargs+=(--kernel "$kernel")
if ! /usr/bin/kmutil create -n aux --volume-root / "${kargs[@]}" \
    -B "$boot_kc" -S "$system_base_kc" --repository "$system_extensions" \
    -A "$new_kc" -z > "$kmutil_log" 2>&1; then
    /usr/bin/tail -n 100 "$kmutil_log"
    echo 'Rifiuto: kmutil non ha costruito la KC finale.'
    exit 1
fi
[[ -s "$new_kc" ]] || {
    echo 'Rifiuto: KC finale vuota.'
    exit 1
}
/usr/bin/kmutil inspect -a x86_64 -A "$new_kc" > "$new_inspect"
/usr/bin/awk -F '\t' '$1 ~ /^[A-Za-z0-9_.-]+$/ {print $1}' "$old_inspect" | /usr/bin/sort -u > "$old_ids"
/usr/bin/awk -F '\t' '$1 ~ /^[A-Za-z0-9_.-]+$/ {print $1}' "$new_inspect" | /usr/bin/sort -u > "$new_ids"
while IFS= read -r bundle_id; do
    /usr/bin/grep -Fxq "$bundle_id" "$new_ids" || {
        echo "Rifiuto: la KC finale non conserva $bundle_id."
        exit 1
    }
done < "$old_ids"
/usr/bin/grep -Fxq 'com.nullmoth.NMXAudio' "$new_ids" || {
    echo 'Rifiuto: NMXAudio assente dalla KC finale.'
    exit 1
}
/usr/bin/grep -q $'^com\\.nullmoth\\.NMXAudio\t1\\.0\\.0\t/Library/Extensions/NMXAudio\\.kext' "$new_inspect" || {
    echo 'Rifiuto: il percorso NMXAudio nella KC finale non è quello reale.'
    exit 1
}

echo 'Salvo la KC intermedia e pubblico atomicamente quella definitiva.'
/usr/bin/ditto "$system_kc" "$system_backup/AuxiliaryKernelExtensions.pre-live-path-rebuild.kc"
backup_hash=$(/usr/bin/shasum -a 256 "$system_backup/AuxiliaryKernelExtensions.pre-live-path-rebuild.kc" | /usr/bin/awk '{print $1}')
[[ "$backup_hash" == "$expected_current_kc_hash" ]] || {
    echo 'Rifiuto: backup della KC intermedia non coincide.'
    exit 1
}
/usr/bin/ditto "$new_inspect" "$system_backup/auxkc-live-inspect.txt"
/usr/bin/ditto "$kmutil_log" "$system_backup/kmutil-create-live.log"
new_hash=$(/usr/bin/shasum -a 256 "$new_kc" | /usr/bin/awk '{print $1}')
/usr/bin/ditto "$new_kc" "$stage_kc"
/usr/sbin/chown root:wheel "$stage_kc"
/bin/chmod "$(/usr/bin/stat -f '%Lp' "$system_kc")" "$stage_kc"
stage_hash=$(/usr/bin/shasum -a 256 "$stage_kc" | /usr/bin/awk '{print $1}')
[[ "$stage_hash" == "$new_hash" ]] || {
    echo 'Rifiuto: KC finale in staging non coincide.'
    exit 1
}
/bin/mv -f "$stage_kc" "$system_kc"
published=1

final_hash=$(/usr/bin/shasum -a 256 "$system_kc" | /usr/bin/awk '{print $1}')
[[ "$final_hash" == "$new_hash" ]] || {
    echo 'Verifica finale hash KC fallita.'
    exit 1
}
/usr/bin/kmutil inspect -a x86_64 -A "$system_kc" > "$temporary_root/published-inspect.txt"
/usr/bin/grep -q $'^com\\.nullmoth\\.NMXAudio\t1\\.0\\.0\t/Library/Extensions/NMXAudio\\.kext' \
    "$temporary_root/published-inspect.txt" || {
    echo 'Verifica finale percorso NMXAudio fallita.'
    exit 1
}
/bin/sync
success=1
echo "RICOSTRUZIONE_NMXAUDIO_LIVE_PATHS_OK auxkc_sha256=$final_hash"
echo "BACKUP_ORIGINALE=$system_backup/AuxiliaryKernelExtensions.kc"
echo "BACKUP_INTERMEDIO=$system_backup/AuxiliaryKernelExtensions.pre-live-path-rebuild.kc"
echo 'KC definitiva verificata. Salva il lavoro e riavvia con HDMI collegato.'
