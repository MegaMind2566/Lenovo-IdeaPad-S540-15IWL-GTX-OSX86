#!/bin/bash
# Native macOS / Bash 3.2. Guarded offline-on-reboot driver test.
# No config.plist, SIP, NVRAM, AMFI or live driver loading changes.
set -euo pipefail
umask 077
export LC_ALL=C

PAYLOAD_MANIFEST_SHA='MICROPHONE_MANIFEST_SHA_PENDING'
TEST_VERSION='3.6.9'
KEY='IOKitPersonalities.VoodooHDA.VoodooHDAEnableVolumeChangeFix'
CONFIG='/Volumes/240 GB/EFI/OC/config.plist'
AUDIO_BACKUP='/Volumes/240 GB/EFI/OC/backup-audio-tahoe'
BACKUP_REL='/Library/Application Support/S540-microfono'
TEMP=''
ROOT_DATA=''
RECOVERY=0
SYSTEM_ROOT=''
RECOVERY_GROUP_MATCH=0
MODE=${1:-}
cleanup() { [ -z "$TEMP" ] || /bin/rm -rf "$TEMP"; }
trap cleanup EXIT
fail() { printf 'Prova microfono: %s\n' "$*" >&2; exit 1; }
hash() {
    if [ -x /usr/bin/shasum ]; then /usr/bin/shasum -a 256 "$1" | /usr/bin/awk '{print $1}';
    elif [ -x /usr/bin/openssl ]; then /usr/bin/openssl dgst -sha256 "$1" | /usr/bin/awk '{print $NF}';
    else fail 'Non è disponibile un lettore SHA256 nativo.'; fi
}
ordinary_file() { [ -f "$1" ] && [ ! -L "$1" ]; }
readkey() { /usr/bin/plutil -extract "$2" raw -o - "$1" 2>/dev/null; }
safe_path() {
    local path=$1
    case "$path" in /*) ;; *) fail 'Serve un percorso assoluto.';; esac
    case "$path" in *$'\n'*|*/../*|*/./*|*/..|*/.) fail 'Il percorso contiene componenti non ammesse.';; esac
    while [ "$path" != / ]; do
        [ ! -L "$path" ] || fail 'Il percorso contiene un collegamento simbolico.'
        path=${path%/*}; [ -n "$path" ] || path=/
    done
}
validate_shape() {
    local bundle=$1 path count
    safe_path "$bundle"
    [ -d "$bundle" ] || fail "Bundle assente: $bundle"
    [ -z "$(/usr/bin/find "$bundle" ! -type f ! -type d -print)" ] || fail 'Il bundle contiene link o file speciali.'
    count=$(/usr/bin/find "$bundle" -type f -print | /usr/bin/wc -l | /usr/bin/tr -d '[:space:]')
    [ "$count" = 3 ] || fail 'Il bundle deve contenere soltanto i tre file previsti.'
    for path in Contents/Info.plist Contents/MacOS/VoodooHDA Contents/_CodeSignature/CodeResources; do
        ordinary_file "$bundle/$path" || fail 'Un file previsto del bundle manca o non è ordinario.'
    done
}
check_manifest() {
    local manifest=$1 index=0 line expected wanted
    ordinary_file "$manifest" || fail 'Manifest driver assente.'
    : > "$TEMP/manifest-canonical"
    while IFS= read -r line || [ -n "$line" ]; do
        index=$((index + 1))
        case "$index" in
            1) wanted=Contents/Info.plist;;
            2) wanted=Contents/MacOS/VoodooHDA;;
            3) wanted=Contents/_CodeSignature/CodeResources;;
            *) fail 'Il manifest contiene file aggiuntivi.';;
        esac
        expected=${line%% *}
        case "$expected" in ''|*[!0-9a-f]*) fail 'Hash del manifest non valido.';; esac
        [ "${#expected}" -eq 64 ] || fail 'Hash del manifest incompleto.'
        [ "$line" = "$expected  $wanted" ] || fail 'Percorsi o formato del manifest non validi.'
        printf '%s  %s\n' "$expected" "$wanted" >> "$TEMP/manifest-canonical"
    done < "$manifest"
    [ "$index" -eq 3 ] && /usr/bin/cmp -s "$manifest" "$TEMP/manifest-canonical" || fail 'Manifest non canonico.'
}
bundle_matches() {
    local bundle=$1 manifest=$2 expected path
    validate_shape "$bundle"
    check_manifest "$manifest"
    while IFS=' ' read -r expected path; do
        path=${path# }
        [ "$(hash "$bundle/$path")" = "$expected" ] || return 1
    done < "$manifest"
}
save_manifest() {
    local bundle=$1 destination=$2 path
    : > "$destination"
    for path in Contents/Info.plist Contents/MacOS/VoodooHDA Contents/_CodeSignature/CodeResources; do
        printf '%s  %s\n' "$(hash "$bundle/$path")" "$path" >> "$destination"
    done
}
verify_signature() {
    if [ ! -x /usr/bin/codesign ] && [ "$RECOVERY" -eq 1 ]; then
        printf 'Recovery: codesign assente; firma non riesaminata. Restano obbligatorie le impronte byte esatte del backup privato.\n' >&2
        return 0
    fi
    /usr/bin/codesign --verify --strict "$1" || fail 'Firma del driver non valida.'
}
check_owned_directory() {
    local path=$1 mode
    safe_path "$path"
    [ -d "$path" ] || fail "Cartella assente: $path"
    [ "$(/usr/bin/stat -f %u "$path")" = 0 ] || fail 'La cartella driver/backup non appartiene a root.'
    mode=$(/usr/bin/stat -f %Lp "$path")
    [ "$((8#$mode & 022))" -eq 0 ] || fail 'La cartella driver/backup è scrivibile da altri utenti.'
}
check_owned_backup() {
    local path mode
    check_owned_directory "$BACKUP"
    [ "$(/usr/bin/stat -f %Lp "$BACKUP")" = 700 ] || fail 'Il backup deve restare privato (permessi 700).'
    while IFS= read -r path; do
        [ ! -L "$path" ] && [ "$(/usr/bin/stat -f %u "$path")" = 0 ] || fail 'Una voce del backup non appartiene a root oppure è un link.'
        mode=$(/usr/bin/stat -f %Lp "$path")
        [ "$((8#$mode & 022))" -eq 0 ] || fail 'Una voce del backup è scrivibile da altri utenti.'
    done < <(/usr/bin/find "$BACKUP" -print)
}
verify_payload() {
    case "$PAYLOAD_MANIFEST_SHA" in ''|*[!0-9a-f]*) fail 'Questo pacchetto non contiene ancora il driver compilato e bloccato.';; esac
    [ "${#PAYLOAD_MANIFEST_SHA}" -eq 64 ] || fail 'Impronta payload incompleta.'
    [ "$(hash "$PAYLOAD_SUMS")" = "$PAYLOAD_MANIFEST_SHA" ] || fail 'Il manifest del nuovo driver non coincide con il pacchetto.'
    bundle_matches "$PAYLOAD" "$PAYLOAD_SUMS" || fail 'Il nuovo driver non coincide con il manifest.'
    [ "$(readkey "$PAYLOAD/Contents/Info.plist" CFBundleIdentifier)" = org.voodoo.driver.VoodooHDA ] || fail 'Identificatore del driver errato.'
    [ "$(readkey "$PAYLOAD/Contents/Info.plist" CFBundleVersion)" = "$TEST_VERSION" ] || fail 'Versione del nuovo driver errata.'
    [ "$(readkey "$PAYLOAD/Contents/Info.plist" "$KEY")" = true ] || fail 'La correzione volume deve restare attiva.'
    [ "$(readkey "$PAYLOAD/Contents/Info.plist" IOKitPersonalities.VoodooHDA.S540InputGainFix)" = true ] || fail 'La correzione microfono prevista non è abilitata nel payload.'
    if [ "$RECOVERY" -ne 1 ]; then
        [ "$(/usr/bin/lipo -archs "$PAYLOAD/Contents/MacOS/VoodooHDA")" = x86_64 ] || fail 'Il driver non è esclusivamente Intel x86_64.'
        /usr/bin/otool -hv "$PAYLOAD/Contents/MacOS/VoodooHDA" > "$TEMP/payload-header.txt"
        if ! /usr/bin/grep -Eq 'KEXT_?BUNDLE' "$TEMP/payload-header.txt"; then
            /bin/cat "$TEMP/payload-header.txt" >&2
            fail 'Il payload non è un bundle kernel.'
        fi
    fi
    verify_signature "$PAYLOAD"
}
volume_uuid() {
    local role
    /usr/sbin/diskutil info -plist "$ROOT_DATA" > "$TEMP/data-volume.plist" || fail 'Impossibile identificare il volume Data.'
    [ "$(readkey "$TEMP/data-volume.plist" FilesystemType)" = apfs ] || fail 'Il volume Data deve essere APFS.'
    [ "$(readkey "$TEMP/data-volume.plist" MountPoint)" = "$ROOT_DATA" ] || fail 'Il percorso Data deve essere il punto di montaggio del volume, non una sottocartella.'
    role=$(readkey "$TEMP/data-volume.plist" APFSVolumeRole.0) || role=$(readkey "$TEMP/data-volume.plist" APFSVolumeRole) || role=''
    [ -z "$role" ] || [ "$role" = Data ] || fail 'Il volume espone un ruolo APFS diverso da Data.'
    VOLUME_UUID=$(readkey "$TEMP/data-volume.plist" VolumeUUID) || fail 'UUID del volume Data assente.'
    case "$VOLUME_UUID" in ''|*[!A-Fa-f0-9-]*) fail 'UUID del volume Data non valido.';; esac
    [ "${#VOLUME_UUID}" -eq 36 ] || fail 'UUID del volume Data incompleto.'
}
recovery_system() {
    local data_group system_group role
    [ -n "$SYSTEM_ROOT" ] || return 0
    safe_path "$SYSTEM_ROOT"
    ordinary_file "$SYSTEM_ROOT/System/Library/CoreServices/SystemVersion.plist" || fail 'Il percorso System non contiene un sistema macOS.'
    /usr/sbin/diskutil info -plist "$SYSTEM_ROOT" > "$TEMP/system-volume.plist" || fail 'Impossibile identificare il volume System.'
    [ "$(readkey "$TEMP/system-volume.plist" FilesystemType)" = apfs ] || fail 'Il volume System deve essere APFS.'
    [ "$(readkey "$TEMP/system-volume.plist" MountPoint)" = "$SYSTEM_ROOT" ] || fail 'Il percorso System deve essere il punto di montaggio del volume.'
    role=$(readkey "$TEMP/system-volume.plist" APFSVolumeRole.0) || role=$(readkey "$TEMP/system-volume.plist" APFSVolumeRole) || role=''
    [ -z "$role" ] || [ "$role" = System ] || fail 'Il volume espone un ruolo APFS diverso da System.'
    data_group=$(readkey "$TEMP/data-volume.plist" APFSVolumeGroupUUID) || data_group=''
    system_group=$(readkey "$TEMP/system-volume.plist" APFSVolumeGroupUUID) || system_group=''
    if [ -n "$data_group" ] && [ -n "$system_group" ]; then
        [ "$data_group" = "$system_group" ] || fail 'System e Data appartengono a gruppi APFS diversi.'
        RECOVERY_GROUP_MATCH=1
    fi
}
runtime_sip() {
    /usr/sbin/nvram -x csr-active-config > "$TEMP/sip.plist" || fail 'Impossibile leggere il SIP attivo.'
    [ "$(readkey "$TEMP/sip.plist" csr-active-config)" = AwAAAA== ] || fail 'Il SIP attivo deve coincidere con quello della prova audio (03000000).'
}
write_phase() {
    local phase=$1 next="$BACKUP/state-next.plist"
    if [ -e "$next" ] || [ -L "$next" ]; then
        ordinary_file "$next" && [ "$(/usr/bin/stat -f %u "$next")" = 0 ] || fail 'Lo stato temporaneo non è un file ordinario di root.'
        /usr/bin/plutil -lint "$next" > /dev/null || fail 'Lo stato temporaneo non è valido.'
        /bin/cp "$next" "$TEMP/state-draft-check.plist"
        /usr/bin/plutil -replace Phase -string "$(readkey "$STATE" Phase)" "$TEMP/state-draft-check.plist"
        /usr/bin/plutil -convert xml1 "$TEMP/state-draft-check.plist"
        /usr/bin/plutil -convert xml1 -o "$TEMP/state-live-check.plist" "$STATE"
        /usr/bin/cmp -s "$TEMP/state-draft-check.plist" "$TEMP/state-live-check.plist" || fail 'Lo stato temporaneo contiene modifiche oltre alla fase: fermo la prova.'
        # An interrupted atomic write never became the committed state. Its
        # phase is discarded; actual driver fingerprints decide the next step.
        /bin/rm "$next"
    fi
    /bin/cp "$STATE" "$next"
    /usr/bin/plutil -replace Phase -string "$phase" "$next"
    /usr/bin/plutil -lint "$next" > /dev/null
    /bin/chmod 600 "$next"
    /bin/mv -f "$next" "$STATE"
    PHASE=$phase
}
load_state() {
    local item
    check_owned_backup
    ordinary_file "$STATE" || fail 'Stato della prova assente.'
    [ "$(/usr/bin/stat -f %u "$STATE")" = 0 ] || fail 'Lo stato della prova non appartiene a root.'
    /usr/bin/plutil -lint "$STATE" > /dev/null
    [ "$(readkey "$STATE" Format)" = 1 ] || fail 'Formato dello stato non riconosciuto.'
    [ "$(readkey "$STATE" VolumeUUID)" = "$VOLUME_UUID" ] || fail 'Questo backup appartiene a un altro volume Data.'
    [ "$(readkey "$STATE" PayloadManifestHash)" = "$PAYLOAD_MANIFEST_SHA" ] || fail 'Il backup appartiene a un altro pacchetto di prova.'
    [ "$(readkey "$STATE" OriginalManifestHash)" = "$(hash "$ORIGINAL_SUMS")" ] || fail 'Il manifest del backup è cambiato.'
    bundle_matches "$ORIGINAL" "$ORIGINAL_SUMS" || fail 'La copia del driver audio funzionante è cambiata.'
    verify_signature "$ORIGINAL"
    PHASE=$(readkey "$STATE" Phase)
    case "$PHASE" in staging|swapping|swapped|rebuildpending|approvalpending|rebootrequired|verified|restoring|restoreswapped|restorepending|restoreapprovalpending|restorerebootrequired|restored) ;; *) fail 'Fase della prova non riconosciuta.';; esac
    for item in OriginalBootSessionUUID ConfigHash; do
        [ -n "$(readkey "$STATE" "$item")" ] || fail 'Stato della prova incompleto.'
    done
}
backup_paths() {
    BACKUP=$1
    STATE="$BACKUP/state.plist"
    ORIGINAL="$BACKUP/original.kext"
    ORIGINAL_SUMS="$BACKUP/original-SHA256SUMS"
}
copy_driver() {
    local from=$1 to=$2 sums=$3
    [ ! -e "$to" ] && [ ! -L "$to" ] || fail 'Esiste una cartella di staging inattesa.'
    /usr/bin/ditto --norsrc --noextattr --noacl --noqtn "$from" "$to" || fail 'Copia del driver non completata.'
    /usr/sbin/chown -R root:wheel "$to"
    /bin/chmod -R go-w "$to"
    bundle_matches "$to" "$sums" || fail 'La copia di staging non è identica al driver previsto.'
    verify_signature "$to"
}
remove_known() {
    local target=$1 sums=$2
    [ -e "$target" ] || { [ ! -L "$target" ] || fail 'Link inatteso nel percorso di staging.'; return 0; }
    bundle_matches "$target" "$sums" || fail 'Una cartella temporanea contiene un driver sconosciuto: non viene eliminata.'
    /bin/rm -rf "$target"
}
rebuild() {
    local status volume_root=/
    if [ "$RECOVERY" -eq 1 ]; then
        write_phase restorepending
        if [ "$RECOVERY_GROUP_MATCH" -ne 1 ]; then
            printf '\nDriver originale ripristinato sul volume Data.\n'
            printf 'La raccolta kernel deve essere ricostruita sul volume System corrispondente prima del riavvio.\n'
            if [ -n "$SYSTEM_ROOT" ]; then
                printf 'Non è disponibile la prova del gruppo APFS comune. Comando da eseguire soltanto dopo aver confermato System:\n'
                printf 'kmutil rebuild --volume-root "%s"\n' "$SYSTEM_ROOT"
            else
                printf 'Ripeti ANNULLA con --recovery-data e --recovery-system dopo aver montato entrambi i volumi.\n'
            fi
            printf 'Stato lasciato in restorepending; il ripristino non è completato né verificato.\n'
            return 0
        fi
        volume_root=$SYSTEM_ROOT
    fi
    set +e
    if [ "$RECOVERY" -eq 1 ]; then
        /usr/bin/kmutil rebuild --volume-root "$volume_root" > "$BACKUP/kmutil-last.txt" 2>&1
    else
        /usr/bin/kmutil rebuild > "$BACKUP/kmutil-last.txt" 2>&1
    fi
    status=$?
    set -e
    /bin/cat "$BACKUP/kmutil-last.txt"
    case "$status" in
        0) ;;
        27|28)
            if [ "$RECOVERY" -eq 1 ]; then
                write_phase restorepending
                printf '\nDriver originale ripristinato. La ricostruzione dalla Recovery richiede un autorizzazione non disponibile qui (codice %s).\n' "$status"
                printf 'La raccolta kernel non è confermata: conserva restorepending e i dettagli in kmutil-last.txt.\n'
            else
                if [ "$MODE" = install ]; then write_phase approvalpending; else write_phase restoreapprovalpending; fi
                printf '\nRicostruzione in attesa di approvazione (codice %s). Apri Impostazioni di Sistema > Privacy e sicurezza.\n' "$status"
                printf 'Consenti il driver se viene richiesto; poi ripeti questo stesso comando prima del riavvio.\n'
            fi
            return 0;;
        *) fail "Ricostruzione kernel non completata (codice $status). Il driver è salvato; ripeti lo stesso comando per riprendere.";;
    esac
    if [ "$MODE" = install ]; then write_phase rebootrequired; else write_phase restorerebootrequired; fi
    printf '\nRicostruzione eseguita. Riavvia manualmente, poi esegui VERIFICA-MICROFONO.command.\n'
}
install_driver() {
    local path final_backup prepare_backup
    runtime_sip
    ordinary_file "$CONFIG" || fail 'Collega e monta 240 GB: config.plist non è disponibile.'
    safe_path "$CONFIG"
    if [ ! -e "$BACKUP" ]; then
        if ! /usr/bin/kmutil libraries --bundle-path "$PAYLOAD" --xml > "$TEMP/kernel-libraries.xml" 2> "$TEMP/kernel-libraries-errors.txt"; then
            /bin/cat "$TEMP/kernel-libraries-errors.txt" >&2
            fail 'Il nuovo driver non risolve tutti i simboli del kernel Tahoe attuale. Il driver funzionante non viene sostituito.'
        fi
        ordinary_file "$CHECK" || fail 'Il controllo della variante audio originale manca.'
        /bin/bash "$CHECK" "$DRIVER" "$AUDIO_BACKUP" > "$TEMP/original-verification.txt" || fail 'Il driver attuale non è la variante audio V3 verificata.'
        [ "$(readkey "$DRIVER/Contents/Info.plist" "$KEY")" = true ] || fail 'La correzione volume V3 non è attiva.'
        /usr/bin/kmutil showloaded > "$TEMP/loaded.txt"
        /usr/bin/grep -Eq 'org\.voodoo\.driver\.VoodooHDA[[:space:]]+\(3\.6\.8\)' "$TEMP/loaded.txt" || fail 'VoodooHDA 3.6.8 non è caricato: esegui la prova dal sistema funzionante.'
        for path in "$STAGE" "$PREVIOUS"; do [ ! -e "$path" ] && [ ! -L "$path" ] || fail 'Esiste una prova driver incompleta non riconosciuta.'; done
        final_backup=$BACKUP
        prepare_backup="$ROOT_DATA/Library/Application Support/.S540-microfono-prepare"
        [ ! -e "$prepare_backup" ] && [ ! -L "$prepare_backup" ] || fail 'Esiste una preparazione backup interrotta. Il driver attuale non è stato sostituito; conserva la cartella per la verifica.'
        backup_paths "$prepare_backup"
        /bin/mkdir "$BACKUP"
        /bin/chmod 700 "$BACKUP"
        /bin/chmod -RN "$BACKUP"
        save_manifest "$DRIVER" "$ORIGINAL_SUMS"
        copy_driver "$DRIVER" "$ORIGINAL" "$ORIGINAL_SUMS"
        /bin/bash "$CHECK" "$ORIGINAL" "$AUDIO_BACKUP" > "$BACKUP/original-verification.txt" || fail 'La copia originale non supera il controllo V3.'
        /usr/bin/plutil -create xml1 "$STATE"
        /usr/bin/plutil -insert Format -integer 1 "$STATE"
        /usr/bin/plutil -insert Phase -string staging "$STATE"
        /usr/bin/plutil -insert VolumeUUID -string "$VOLUME_UUID" "$STATE"
        /usr/bin/plutil -insert OriginalManifestHash -string "$(hash "$ORIGINAL_SUMS")" "$STATE"
        /usr/bin/plutil -insert PayloadManifestHash -string "$PAYLOAD_MANIFEST_SHA" "$STATE"
        /usr/bin/plutil -insert ConfigHash -string "$(hash "$CONFIG")" "$STATE"
        /usr/bin/plutil -insert OriginalBootSessionUUID -string "$BOOT_UUID" "$STATE"
        /usr/bin/plutil -insert RuntimeSipData -string 03000000 "$STATE"
        /bin/chmod 600 "$STATE"
        /usr/bin/plutil -lint "$STATE" > /dev/null
        bundle_matches "$ORIGINAL" "$ORIGINAL_SUMS" || fail 'La copia originale è cambiata durante la preparazione.'
        /bin/mv "$BACKUP" "$final_backup"
        backup_paths "$final_backup"
    fi
    load_state
    [ "$(readkey "$STATE" ConfigHash)" = "$(hash "$CONFIG")" ] || fail 'La configurazione EFI è cambiata dopo l inizio della prova: non viene toccata.'
    case "$PHASE" in
        staging|swapping)
            if [ -e "$DRIVER" ] && bundle_matches "$DRIVER" "$PAYLOAD_SUMS"; then
                write_phase swapped
            else
                if [ -e "$DRIVER" ]; then
                    bundle_matches "$DRIVER" "$ORIGINAL_SUMS" || fail 'Il driver installato non coincide con quello originale.'
                    [ ! -e "$PREVIOUS" ] && [ ! -L "$PREVIOUS" ] || fail 'Esiste già la precedente copia temporanea.'
                else
                    bundle_matches "$PREVIOUS" "$ORIGINAL_SUMS" || fail 'Il driver originale non è nel percorso temporaneo previsto.'
                fi
                if [ -e "$STAGE" ]; then bundle_matches "$STAGE" "$PAYLOAD_SUMS" || fail 'Staging non riconosciuto.'; else copy_driver "$PAYLOAD" "$STAGE" "$PAYLOAD_SUMS"; fi
                write_phase swapping
                if [ -e "$DRIVER" ]; then /bin/mv "$DRIVER" "$PREVIOUS"; fi
                /bin/mv "$STAGE" "$DRIVER"
                bundle_matches "$DRIVER" "$PAYLOAD_SUMS" || fail 'Il driver sostituito non coincide con il payload.'
                write_phase swapped
            fi
            ;;
        swapped|rebuildpending|approvalpending) bundle_matches "$DRIVER" "$PAYLOAD_SUMS" || fail 'Il driver della prova è cambiato.';;
        rebootrequired|verified) printf 'La prova è già installata. Riavvia se necessario ed esegui VERIFICA-MICROFONO.command.\n'; return 0;;
        *) fail 'La prova è in ripristino o già annullata. Non viene reinstallata automaticamente.';;
    esac
    remove_known "$PREVIOUS" "$ORIGINAL_SUMS"
    write_phase rebuildpending
    rebuild
    printf 'Per annullare usa soltanto ANNULLA-MICROFONO.command di questo pacchetto.\n'
}
restore_driver() {
    load_state
    case "$PHASE" in restored|restorerebootrequired) printf 'Il driver originale è già ripristinato. Riavvia se necessario e verifica.\n'; return 0;; esac
    if [ -e "$DRIVER" ] && bundle_matches "$DRIVER" "$ORIGINAL_SUMS"; then
        :
    else
        if [ -e "$DRIVER" ]; then bundle_matches "$DRIVER" "$PAYLOAD_SUMS" || fail 'Il driver installato è sconosciuto: il ripristino si ferma.'; fi
        remove_known "$STAGE" "$PAYLOAD_SUMS"
        remove_known "$PREVIOUS" "$ORIGINAL_SUMS"
        copy_driver "$ORIGINAL" "$PREVIOUS" "$ORIGINAL_SUMS"
        write_phase restoring
        if [ -e "$DRIVER" ]; then /bin/mv "$DRIVER" "$STAGE"; fi
        /bin/mv "$PREVIOUS" "$DRIVER"
    fi
    bundle_matches "$DRIVER" "$ORIGINAL_SUMS" || fail 'Il driver originale non è stato ripristinato esattamente.'
    verify_signature "$DRIVER"
    remove_known "$STAGE" "$PAYLOAD_SUMS"
    remove_known "$PREVIOUS" "$ORIGINAL_SUMS"
    write_phase restoreswapped
    rebuild
}
verify_driver() {
    local target_version expected_sums
    load_state
    runtime_sip
    case "$PHASE" in
        rebootrequired|verified) target_version=$TEST_VERSION; expected_sums=$PAYLOAD_SUMS;;
        restorerebootrequired|restored) target_version=3.6.8; expected_sums=$ORIGINAL_SUMS;;
        *) fail 'La sostituzione o la ricostruzione non è completa. Ripeti INSTALLA oppure ANNULLA secondo l operazione avviata.';;
    esac
    bundle_matches "$DRIVER" "$expected_sums" || fail 'Il driver installato non coincide con quello atteso.'
    [ "$BOOT_UUID" != "$(readkey "$STATE" OriginalBootSessionUUID)" ] || fail 'Serve un riavvio dopo la sostituzione del driver.'
    /usr/bin/kmutil showloaded > "$TEMP/loaded.txt"
    /usr/bin/grep -Eq "org\\.voodoo\\.driver\\.VoodooHDA[[:space:]]+\\(${target_version//./\\.}\\)" "$TEMP/loaded.txt" || fail 'La versione attesa del driver non è caricata.'
    if [ "$target_version" = "$TEST_VERSION" ]; then
        /usr/sbin/ioreg -r -c VoodooHDADevice -l -w 0 > "$TEMP/driver-ioreg.txt"
        /usr/bin/grep -Eq '"S540InputGainFixActive" = (Yes|true)' "$TEMP/driver-ioreg.txt" || fail 'Il driver è caricato ma la correzione ingresso non risulta attiva per questo codec.'
        /usr/sbin/ioreg -r -c IOAudioLevelControl -l -w 0 > "$TEMP/controls.txt"
        /usr/bin/awk '
            /\+-o IOAudioLevelControl[[:space:]]/ { usage=""; low=""; high="" }
            /"IOAudioLevelControlMinDB" =/ {low=$NF}
            /"IOAudioLevelControlMaxDB" =/ {high=$NF}
            /"IOAudioControlUsage" =/ {usage=$NF}
            /\}/ {if(usage=="1768845428") {count++; if(low!="-1130496" && low!="18446744073708421120") bad=1; if(high!="1966080") bad=1; usage=""}}
            END {exit (count!=2 || bad)}' "$TEMP/controls.txt" || fail 'I due controlli di ingresso non espongono la scala prevista (-17.25/+30 dB).'
        write_phase verified
        printf 'Driver 3.6.9 caricato; correzione microfono attiva; scala dei due ingressi verificata.\n'
        printf 'Ora prova una registrazione con il volume di ingresso al 50%% e controlla anche il volume degli altoparlanti.\n'
    else
        write_phase restored
        printf 'Ripristino verificato: VoodooHDA 3.6.8 originale della prova volume è caricato.\n'
    fi
}

case "$MODE" in install|restore|verify|payload-check) ;; *) fail 'Uso: install | restore [--recovery-data PERCORSO --recovery-system PERCORSO] | verify';; esac
shift
[ "$(/usr/bin/uname -s)" = Darwin ] && [ "$(/usr/bin/uname -m)" = x86_64 ] || fail 'Serve macOS Intel.'
PACKAGE=$(cd -P "$(/usr/bin/dirname "${BASH_SOURCE[0]}")/.." && pwd)
safe_path "$PACKAGE"
PAYLOAD="$PACKAGE/assets/microphone/VoodooHDA.kext"
PAYLOAD_SUMS="$PACKAGE/assets/microphone/SHA256SUMS"
CHECK="$PACKAGE/tools/verify_microphone_driver.sh"
if [ "$MODE" = payload-check ]; then
    [ "$#" -eq 0 ] || fail 'Il controllo payload non richiede argomenti.'
    TEMP=$(/usr/bin/mktemp -d /tmp/s540-microphone-payload.XXXXXX)
    verify_payload
    printf 'Payload 3.6.9 Intel: manifest, tre file, firma e formato kernel verificati.\n'
    exit 0
fi
case "$(/usr/bin/uname -r)" in 25.*) ;; *) fail 'Questo pacchetto è destinato a macOS Tahoe.';; esac
if [ "$#" -gt 0 ]; then
    [ "$MODE" = restore ] || fail 'Il volume Data esplicito è ammesso soltanto per il ripristino dalla Recovery.'
    [ "$(/usr/bin/id -u)" -eq 0 ] || fail 'Dalla Recovery serve il Terminale root.'
    [ ! -d /System/Volumes/Data ] || fail 'Dal desktop usa ANNULLA senza argomenti.'
    if [ "$#" -eq 1 ]; then
        ROOT_DATA=${1%/}
    else
        while [ "$#" -gt 0 ]; do
            [ "$#" -ge 2 ] || fail 'Manca il percorso di un volume Recovery.'
            case "$1" in
                --recovery-data) [ -z "$ROOT_DATA" ] || fail 'Il volume Data è stato indicato più volte.'; ROOT_DATA=${2%/};;
                --recovery-system) [ -z "$SYSTEM_ROOT" ] || fail 'Il volume System è stato indicato più volte.'; SYSTEM_ROOT=${2%/};;
                *) fail 'Argomento Recovery non riconosciuto.';;
            esac
            shift 2
        done
    fi
    [ -n "$ROOT_DATA" ] || fail 'Indica il volume Data con --recovery-data.'
    RECOVERY=1
    safe_path "$ROOT_DATA"
    [ -d "$ROOT_DATA/Users" ] && [ -d "$ROOT_DATA/private/var" ] && [ -d "$ROOT_DATA/Library/Extensions" ] || fail 'Il percorso non presenta le cartelle di un volume macOS Data.'
else
    [ -d /System/Volumes/Data ] && [ -d /Users ] || fail 'Dalla Recovery indica esplicitamente il volume Data per il ripristino.'
    ROOT_DATA='/System/Volumes/Data'
fi
if [ "$(/usr/bin/id -u)" -ne 0 ]; then
    printf 'Serve la password amministratore per la copia del driver e la ricostruzione kernel.\n'
    exec /usr/bin/sudo /bin/bash "$PACKAGE/tools/microphone_driver_test.sh" "$MODE"
fi
for utility in /usr/bin/awk /usr/bin/plutil /usr/bin/cmp /usr/bin/find /usr/bin/stat /usr/bin/ditto /usr/bin/kmutil /usr/sbin/diskutil; do
    [ -x "$utility" ] || fail "Utility necessaria assente: $utility. Nessun driver viene sostituito."
done
if [ "$RECOVERY" -ne 1 ]; then
    for utility in /usr/bin/codesign /usr/bin/lipo /usr/bin/otool; do
        [ -x "$utility" ] || fail "Utility necessaria assente: $utility. Nessun driver viene sostituito."
    done
fi
TEMP=$(/usr/bin/mktemp -d /tmp/s540-microphone-driver.XXXXXX) || fail 'Impossibile creare la cartella temporanea.'
if [ "$RECOVERY" -eq 1 ]; then DRIVER_PARENT="$ROOT_DATA/Library/Extensions"; else DRIVER_PARENT='/Library/Extensions'; fi
DRIVER="$DRIVER_PARENT/VoodooHDA.kext"
STAGE="$DRIVER_PARENT/.VoodooHDA-s540-microphone-stage.kext"
PREVIOUS="$DRIVER_PARENT/.VoodooHDA-s540-microphone-previous.kext"
backup_paths "$ROOT_DATA$BACKUP_REL"
check_owned_directory "$DRIVER_PARENT"
check_owned_directory "$ROOT_DATA/Library/Application Support"
volume_uuid
if [ "$RECOVERY" -eq 1 ]; then recovery_system; fi
BOOT_UUID=$(/usr/sbin/sysctl -n kern.bootsessionuuid) || fail 'Impossibile identificare questo avvio.'
verify_payload
case "$MODE" in install) install_driver;; restore) restore_driver;; verify) verify_driver;; esac
