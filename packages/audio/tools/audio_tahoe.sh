#!/bin/bash
# Native macOS, Bash 3.2. No changes to the sealed system volume.
set -euo pipefail
export LC_ALL=C
GUID=7C436110-AB2A-4BBB-A880-FE41995C9F82
GPU='DeviceProperties.Add.PciRoot(0x0)/Pci(0x2,0x0)'
SIP="NVRAM.Add.$GUID.csr-active-config"
ARGS="NVRAM.Add.$GUID.boot-args"
DELETE="NVRAM.Delete.$GUID"
PAYLOAD_MANIFEST_SHA='774e27e9997fe5b7c84366f2222f3244b589196158fe5542bf49e1bf659ad7fe'
HERE=$(cd "$(dirname "$0")/.." && pwd -P)
ASSETS="$HERE/assets/audio-tahoe"
MODE=${1:-verify}
[ "$#" -eq 0 ] || shift
[ "$#" -le 1 ] || { echo 'Indica al massimo il percorso del disco di avvio.'; exit 1; }
BOOTROOT=${1:-'/Volumes/240 GB'}
OC="$BOOTROOT/EFI/OC"
CONFIG="$OC/config.plist"
BACKUP="$OC/backup-audio-tahoe"
DRIVER=/Library/Extensions/VoodooHDA.kext
TEMP=''
DRAFT=''
STAGING=''
cleanup() {
    if [ -n "$STAGING" ] && [ -d "$STAGING" ]; then
        if [ ! -e "$DRIVER" ] && [ ! -L "$DRIVER" ] && [ -d "$STAGING/previous.kext" ]; then
            /usr/bin/sudo -n /bin/mv "$STAGING/previous.kext" "$DRIVER" || true
        fi
        /usr/bin/sudo -n /bin/rm -rf "$STAGING" || true
    fi
    if [ -n "$DRAFT" ] && [ -d "$DRAFT" ]; then /bin/rm -rf "$DRAFT"; fi
    if [ -n "$TEMP" ] && [ -d "$TEMP" ]; then /bin/rm -rf "$TEMP"; fi
}
trap cleanup EXIT
trap 'echo "Operazione non completata. Non riavviare durante una copia incompleta; conserva il backup audio." >&2' ERR
fail() { echo "Operazione annullata: $*" >&2; exit 1; }
readkey() { /usr/bin/plutil -extract "$2" raw -o - "$1" 2>/dev/null; }
hash() { /usr/bin/shasum -a 256 "$1" | /usr/bin/awk '{print $1}'; }
ordinary() { [ -e "$1" ] && [ ! -L "$1" ] || fail "Percorso assente o simbolico: $1"; }
no_links() { [ -z "$(/usr/bin/find "$1" -type l -print)" ] || fail 'La cartella contiene collegamenti simbolici.'; }
native() {
    [ "$(/usr/bin/uname -s)" = Darwin ] && [ "$(/usr/bin/uname -m)" = x86_64 ] || fail 'Serve macOS Intel.'
    case "$(/usr/bin/uname -r)" in 25.*) ;; *) fail 'Questa prova richiede macOS Tahoe (Darwin 25).';; esac
    [ -d /System/Volumes/Data ] && [ -d /Users ] || fail 'Esegui il comando dal desktop Tahoe, non dalla Recovery.'
    [ "$(/usr/bin/id -u)" -ne 0 ] || fail 'Apri il comando dal tuo account. La password viene richiesta solo quando serve.'
    for command in plutil shasum ditto codesign kmutil sudo base64; do
        [ -x "/usr/bin/$command" ] || fail "Manca il comando macOS $command."
    done
    for path in "$BOOTROOT" "$BOOTROOT/EFI" "$OC" "$OC/Kexts" "$CONFIG"; do ordinary "$path"; done
    [ -x /usr/sbin/nvram ] && [ -x /usr/sbin/ioreg ] && [ -x /usr/sbin/sysctl ] || fail 'Mancano nvram o ioreg.'
    /usr/bin/plutil -lint "$CONFIG" >/dev/null
}
kext_tree_hash() {
    no_links "$OC/Kexts"
    ( cd "$OC/Kexts"; /usr/bin/find . -type f -print | /usr/bin/sort | while IFS= read -r file; do
        [ -f "$file" ] || exit 1
        /usr/bin/shasum -a 256 "$file"
    done ) | /usr/bin/shasum -a 256 | /usr/bin/awk '{print $1}'
}
find_kext() {
    local i=0 entry
    while entry=$(readkey "$1" "Kernel.Add.$i.BundlePath"); do
        if [ "$entry" = "$2" ]; then printf '%s\n' "$i"; return 0; fi
        i=$((i+1))
    done
    return 1
}
append_csr_delete() {
    local file=$1 i=0 value found=0
    /usr/bin/plutil -extract "$DELETE" xml1 -o - "$file" | /usr/bin/grep -q '<array>' || fail 'NVRAM/Delete non contiene l’array previsto.'
    while value=$(readkey "$file" "$DELETE.$i"); do
        [ "$value" != csr-active-config ] || found=$((found+1))
        i=$((i+1))
    done
    [ "$found" -le 1 ] || fail 'csr-active-config compare più volte in NVRAM/Delete.'
    [ "$found" -ne 0 ] || /usr/bin/plutil -insert "$DELETE.$i" -string csr-active-config "$file"
}
validate_baseline() {
    local file=$1 args lilu
    [ "$(readkey "$file" "$SIP")" = AAAAAA== ] || fail 'Il SIP iniziale non è Data 00000000.'
    /usr/bin/plutil -extract "$SIP" xml1 -o - "$file" | /usr/bin/grep -q '<data>' || fail 'csr-active-config deve essere Data.'
    [ "$(readkey "$file" Misc.Security.SecureBootModel)" = Disabled ] || fail 'SecureBootModel non coincide con la EFI verificata.'
    [ "$(readkey "$file" "$GPU.AAPL,ig-platform-id")" = CQClPg== ] || fail 'La piattaforma Intel non è 0900A53E.'
    [ "$(readkey "$file" "$GPU.device-id")" = pT4AAA== ] || fail 'Il device-id Intel non è A53E0000.'
    [ "$(readkey "$file" "$GPU.framebuffer-patch-enable")" = AQAAAA== ] || fail 'Manca la correzione memoria Intel.'
    [ "$(readkey "$file" "$GPU.framebuffer-stolenmem")" = AAAwAQ== ] || fail 'framebuffer-stolenmem non coincide.'
    [ "$(readkey "$file" "$GPU.framebuffer-fbmem")" = AACQAA== ] || fail 'framebuffer-fbmem non coincide.'
    args=$(readkey "$file" "$ARGS")
    case " $args " in *' -igfxvesa '*|*' -x '*) fail 'Riparti dal desktop con accelerazione Intel attiva.';; esac
    case " $args " in *' voodoo-layout-id='*) fail 'È già presente un layout VoodooHDA. Nessuna modifica.';; esac
    ALC=$(find_kext "$file" AppleALC.kext) || fail 'AppleALC non è nella configurazione.'
    [ "$(readkey "$file" "Kernel.Add.$ALC.MaxKernel")" = 24.99.99 ] || fail 'Il limite Darwin di AppleALC non coincide.'
    [ "$(readkey "$file" "Kernel.Add.$ALC.Enabled")" = true ] || fail 'AppleALC non è nello stato iniziale previsto.'
    lilu=$(find_kext "$file" Lilu.kext) || fail 'Lilu non è nella configurazione.'
    [ "$(readkey "$file" "Kernel.Add.$lilu.Enabled")" = true ] || fail 'Lilu deve essere abilitato.'
    [ "$(readkey "$OC/Kexts/Lilu.kext/Contents/Info.plist" CFBundleVersion)" = 1.7.2 ] || fail 'La versione Lilu non coincide.'
}
accepted_original_sip() {
    case "$1" in AAAAAA==|ZwIAAA==) return 0;; *) fail 'Il SIP iniziale non è uno dei due stati verificati (00000000 o 67020000).';; esac
}
derive_states() {
    local before=$1 prepared=$2 restored=$3 original_sip=$4 args i=0 value
    accepted_original_sip "$original_sip"
    validate_baseline "$before"
    if [ "$original_sip" != AAAAAA== ]; then
        [ "$(readkey "$before" NVRAM.WriteFlash)" = true ] || fail 'Serve WriteFlash attivo per conservare il SIP originale dopo il ripristino.'
        [ "$(readkey "$before" NVRAM.LegacyOverwrite)" = false ] || fail 'La NVRAM legacy potrebbe sovrascrivere il SIP originale: nessuna modifica.'
        while value=$(readkey "$before" "$DELETE.$i"); do
            [ "$value" != csr-active-config ] || fail 'Il config originale cancella il SIP a ogni avvio: non è possibile conservare il SIP attivo originale senza cambiare quel config.'
            i=$((i+1))
        done
    fi
    /bin/cp -p "$before" "$prepared"
    /bin/cp -p "$before" "$restored"
    /usr/bin/plutil -replace "$SIP" -data AwAAAA== "$prepared"
    /usr/bin/plutil -replace "$SIP" -data "$original_sip" "$restored"
    /usr/bin/plutil -replace "Kernel.Add.$ALC.Enabled" -bool false "$prepared"
    args=$(readkey "$before" "$ARGS")
    /usr/bin/plutil -replace "$ARGS" -string "$args voodoo-layout-id=11" "$prepared"
    append_csr_delete "$prepared"
    append_csr_delete "$restored"
    /usr/bin/plutil -lint "$prepared" "$restored" >/dev/null
}
atomic_config() {
    local wanted=$1 expected=$2 temp expected_wanted
    [ "$(hash "$CONFIG")" = "$expected" ] || fail 'Il config è cambiato durante i controlli.'
    expected_wanted=$(hash "$wanted")
    temp=$(/usr/bin/mktemp "$OC/.audio-config.XXXXXX")
    /bin/cp -p "$wanted" "$temp"
    /usr/bin/plutil -lint "$temp" >/dev/null
    [ "$(hash "$temp")" = "$expected_wanted" ] || { /bin/rm -f "$temp"; fail 'Copia config incompleta.'; }
    [ "$(hash "$CONFIG")" = "$expected" ] || { /bin/rm -f "$temp"; fail 'Il config è cambiato durante la copia.'; }
    /bin/mv -f "$temp" "$CONFIG"
    if [ "$(hash "$CONFIG")" != "$expected_wanted" ]; then
        /bin/cp -p "$BACKUP/before.plist" "$CONFIG"
        fail 'Scrittura non verificata; config originale recuperato.'
    fi
}
state_set() {
    local key=$1 value=$2 temp
    temp=$(/usr/bin/mktemp "$BACKUP/.state.XXXXXX")
    /bin/cp -p "$BACKUP/state.plist" "$temp"
    if readkey "$temp" "$key" >/dev/null; then
        /usr/bin/plutil -replace "$key" -string "$value" "$temp"
    else
        /usr/bin/plutil -insert "$key" -string "$value" "$temp"
    fi
    /usr/bin/plutil -lint "$temp" >/dev/null
    /bin/mv -f "$temp" "$BACKUP/state.plist"
}
load_backup() {
    local f
    ordinary "$BACKUP"; no_links "$BACKUP"
    for f in before prepared restore-sip state; do ordinary "$BACKUP/$f.plist"; /usr/bin/plutil -lint "$BACKUP/$f.plist" >/dev/null; done
    case "$(readkey "$BACKUP/state.plist" Format)" in
        2) ;;
        1) fail 'Backup audio versione 1: nessuna modifica. Usa il pacchetto originale per ripristinare quella prova.';;
        *) fail 'Formato backup sconosciuto.';;
    esac
    ORIGINAL_SIP=$(readkey "$BACKUP/state.plist" OriginalSip) || fail 'Il backup non contiene il SIP originale.'
    accepted_original_sip "$ORIGINAL_SIP"
    /usr/bin/plutil -extract OriginalSip xml1 -o - "$BACKUP/state.plist" | /usr/bin/grep -q '<data>' || fail 'Il SIP originale salvato deve essere Data.'
    case "$(readkey "$BACKUP/state.plist" Phase)" in prepared|copying|installed|removal-pending|removal-requested|sip-pending|complete) ;; *) fail 'Fase del backup sconosciuta.';; esac
    for f in before prepared restore-sip; do
        [ "$(hash "$BACKUP/$f.plist")" = "$(readkey "$BACKUP/state.plist" "$f")" ] || fail 'Backup audio modificato.'
    done
    [ "$(kext_tree_hash)" = "$(readkey "$BACKUP/state.plist" EFI-Kexts)" ] || fail 'I kext della EFI sono cambiati dopo la prova.'
    /bin/mkdir -p "$TEMP/derived"
    derive_states "$BACKUP/before.plist" "$TEMP/derived/prepared.plist" "$TEMP/derived/restore-sip.plist" "$ORIGINAL_SIP"
    /usr/bin/cmp -s "$TEMP/derived/prepared.plist" "$BACKUP/prepared.plist" || fail 'Lo snapshot preparato non è la modifica prevista.'
    /usr/bin/cmp -s "$TEMP/derived/restore-sip.plist" "$BACKUP/restore-sip.plist" || fail 'Lo snapshot SIP non è la modifica prevista.'
    PHASE=$(readkey "$BACKUP/state.plist" Phase)
    BEFORE=$(hash "$BACKUP/before.plist")
    PREPARED=$(hash "$BACKUP/prepared.plist")
    RESTORE_SIP=$(hash "$BACKUP/restore-sip.plist")
    CURRENT=$(hash "$CONFIG")
    case "$CURRENT" in "$BEFORE"|"$PREPARED"|"$RESTORE_SIP") ;; *) fail 'Il config è stato modificato dopo la prova. Nessuna sovrascrittura.';; esac
}
active_sip() {
    local value normalized length
    /usr/sbin/nvram -x csr-active-config > "$TEMP/nvram.plist" || fail 'Impossibile leggere csr-active-config dalla NVRAM.'
    /usr/bin/plutil -lint "$TEMP/nvram.plist" >/dev/null || fail 'La lettura NVRAM non è un plist valido.'
    /usr/bin/plutil -extract csr-active-config xml1 -o - "$TEMP/nvram.plist" | /usr/bin/grep -q '<data>' || fail 'csr-active-config attivo non è Data.'
    value=$(readkey "$TEMP/nvram.plist" csr-active-config | /usr/bin/tr -d '[:space:]') || fail 'Impossibile estrarre il SIP attivo.'
    printf '%s' "$value" | /usr/bin/base64 -D > "$TEMP/sip.bin" || fail 'Il SIP attivo non è Base64 valido.'
    length=$(/usr/bin/wc -c < "$TEMP/sip.bin" | /usr/bin/tr -d '[:space:]')
    [ "$length" = 4 ] || fail 'csr-active-config attivo deve contenere esattamente quattro byte.'
    normalized=$(/usr/bin/base64 < "$TEMP/sip.bin" | /usr/bin/tr -d '[:space:]') || fail 'Impossibile normalizzare il SIP attivo.'
    printf '%s\n' "$normalized"
}
require_sip3() {
    [ "$(active_sip)" = AwAAAA== ] || fail 'Riavvia con la EFI preparata: il SIP attivo deve essere 03000000.'
}
runtime_bootargs() {
    local args
    args=$(/usr/sbin/sysctl -n kern.bootargs | /usr/bin/tr '[:space:]' ' ') || fail 'Impossibile leggere i boot-args della sessione attuale.'
    case " $args " in *' voodoo-layout-id=11 '*) ;; *) fail 'Riavvia dalla EFI preparata: manca il layout audio nei boot-args attivi.';; esac
    case " $args " in *' -igfxvesa '*|*' -x '*) fail 'La sessione attuale usa VESA o avvio sicuro.';; esac
}
boot_session() {
    local session
    session=$(/usr/sbin/sysctl -n kern.bootsessionuuid) || fail 'Impossibile identificare la sessione di avvio.'
    printf '%s' "$session" | /usr/bin/grep -Eq '^[A-Fa-f0-9]{8}(-[A-Fa-f0-9]{4}){3}-[A-Fa-f0-9]{12}$' || fail 'Identificativo della sessione non riconosciuto.'
    printf '%s\n' "$session"
}
audio_controller() {
    /usr/sbin/ioreg -r -n HDAS -l -w 0 > "$TEMP/controller.txt"
    /usr/bin/grep -qi 'HDAS@1F,3' "$TEMP/controller.txt" || fail 'Il controller HDAS non è sul percorso PCI verificato.'
    /usr/bin/grep -Eq '"vendor-id" = <86800000>|pci8086,' "$TEMP/controller.txt" || fail 'Il controller audio Intel HDAS non è stato rilevato.'
}
validate_payload() {
    ordinary "$ASSETS/SHA256SUMS"
    [ "$PAYLOAD_MANIFEST_SHA" != MANIFEST_SHA_PENDING ] || fail 'Il pacchetto audio non è completo.'
    [ "$(hash "$ASSETS/SHA256SUMS")" = "$PAYLOAD_MANIFEST_SHA" ] || fail 'Manifest audio non verificato.'
    ordinary "$ASSETS/VoodooHDA.kext"; no_links "$ASSETS/VoodooHDA.kext"
    [ "$(/usr/bin/find "$ASSETS/VoodooHDA.kext" -type f | /usr/bin/wc -l | /usr/bin/tr -d ' ')" = 3 ] || fail 'Il payload audio contiene file inattesi.'
    (cd "$ASSETS"; /usr/bin/shasum -a 256 -c SHA256SUMS) >/dev/null || fail 'Il driver audio non supera il controllo SHA256.'
    /usr/bin/codesign --verify --strict "$ASSETS/VoodooHDA.kext" || fail 'La firma del driver audio non è valida.'
}
original_driver_matches() {
    local destination=$1 path expected actual
    ordinary "$destination"; no_links "$destination"
    [ "$(/usr/bin/find "$destination" -type f | /usr/bin/wc -l | /usr/bin/tr -d ' ')" = 3 ] || return 1
    while IFS=' ' read -r expected path; do
        path=${path# }; path=${path#VoodooHDA.kext/}
        [ -f "$destination/$path" ] || return 1
        actual=$(hash "$destination/$path")
        [ "$actual" = "$expected" ] || return 1
    done < "$ASSETS/SHA256SUMS"
}
VOLUME_KEY=IOKitPersonalities.VoodooHDA.VoodooHDAEnableVolumeChangeFix
VOLUME="$BACKUP/volume-test"
bundle_manifest_matches() {
    local destination=$1 manifest=$2 expected path actual
    ordinary "$destination"; no_links "$destination"
    [ "$(/usr/bin/find "$destination" -type f | /usr/bin/wc -l | /usr/bin/tr -d ' ')" = 3 ] || return 1
    while IFS=' ' read -r expected path; do
        path=${path# }
        case "$path" in Contents/Info.plist|Contents/MacOS/VoodooHDA|Contents/_CodeSignature/CodeResources) ;; *) return 1;; esac
        [ -f "$destination/$path" ] || return 1
        actual=$(hash "$destination/$path")
        [ "$actual" = "$expected" ] || return 1
    done < "$manifest"
}
validate_volume_backup() {
    local manifest_hash draft
    manifest_hash=$(readkey "$BACKUP/state.plist" VolumeManifestHash) || fail 'Manca il riferimento al backup volume.'
    if [ ! -e "$VOLUME" ] && [ ! -L "$VOLUME" ]; then
        draft=$(readkey "$BACKUP/state.plist" VolumeDraftPath) || fail 'Il backup volume è incompleto.'
        case "$draft" in "$BACKUP"/.volume-draft.*) ;; *) fail 'Percorso temporaneo volume non valido.';; esac
        ordinary "$draft"; no_links "$draft"
        ordinary "$draft/SHA256SUMS"
        [ "$(hash "$draft/SHA256SUMS")" = "$manifest_hash" ] || fail 'Il manifest volume temporaneo non coincide.'
        original_driver_matches "$draft/original/VoodooHDA.kext" || fail 'Il backup driver originale non coincide.'
        bundle_manifest_matches "$draft/modified/VoodooHDA.kext" "$draft/SHA256SUMS" || fail 'Il driver volume temporaneo non coincide.'
        /bin/mv "$draft" "$VOLUME"
    fi
    ordinary "$VOLUME"; no_links "$VOLUME"
    ordinary "$VOLUME/SHA256SUMS"
    [ "$(hash "$VOLUME/SHA256SUMS")" = "$manifest_hash" ] || fail 'Il manifest volume è stato modificato.'
    [ "$(/usr/bin/wc -l < "$VOLUME/SHA256SUMS" | /usr/bin/tr -d ' ')" = 3 ] || fail 'Il manifest volume non contiene tre file.'
    original_driver_matches "$VOLUME/original/VoodooHDA.kext" || fail 'Il backup driver originale è stato modificato.'
    bundle_manifest_matches "$VOLUME/modified/VoodooHDA.kext" "$VOLUME/SHA256SUMS" || fail 'Il backup driver volume è stato modificato.'
    /bin/cp "$VOLUME/original/VoodooHDA.kext/Contents/Info.plist" "$TEMP/expected-volume.plist"
    [ "$(readkey "$TEMP/expected-volume.plist" "$VOLUME_KEY")" = false ] || fail 'Il valore volume originario non coincide.'
    /usr/bin/plutil -replace "$VOLUME_KEY" -bool true "$TEMP/expected-volume.plist"
    /usr/bin/plutil -convert xml1 "$TEMP/expected-volume.plist"
    /usr/bin/plutil -convert xml1 -o "$TEMP/actual-volume.plist" "$VOLUME/modified/VoodooHDA.kext/Contents/Info.plist"
    /usr/bin/cmp -s "$TEMP/expected-volume.plist" "$TEMP/actual-volume.plist" || fail 'Il plist volume contiene altre modifiche.'
    /usr/bin/codesign --verify --strict "$VOLUME/modified/VoodooHDA.kext" || fail 'La firma del backup volume non è valida.'
}
driver_matches() {
    if original_driver_matches "$1"; then return 0; fi
    if readkey "$BACKUP/state.plist" VolumeManifestHash >/dev/null; then
        validate_volume_backup
        bundle_manifest_matches "$1" "$VOLUME/SHA256SUMS"
    else
        return 1
    fi
}
make_volume_backup() {
    local draft manifest_hash state_temp path
    if readkey "$BACKUP/state.plist" VolumeManifestHash >/dev/null; then
        validate_volume_backup; return
    fi
    [ ! -e "$VOLUME" ] && [ ! -L "$VOLUME" ] || fail 'Esiste un backup volume senza riferimento verificato.'
    original_driver_matches "$DRIVER" || fail 'Il driver iniziale volume non è il payload originale verificato.'
    DRAFT=$(/usr/bin/mktemp -d "$BACKUP/.volume-draft.XXXXXX")
    draft=$DRAFT
    /bin/mkdir "$draft/original" "$draft/modified"
    /usr/bin/ditto --norsrc --noextattr --noacl --noqtn "$DRIVER" "$draft/original/VoodooHDA.kext"
    original_driver_matches "$draft/original/VoodooHDA.kext" || fail 'Backup driver originale incompleto.'
    # Sign on the running macOS volume; the EFI backup volume can be FAT/exFAT.
    /bin/mkdir -p "$TEMP/volume-build"
    /usr/bin/ditto --norsrc --noextattr --noacl --noqtn "$draft/original/VoodooHDA.kext" "$TEMP/volume-build/VoodooHDA.kext"
    [ "$(readkey "$TEMP/volume-build/VoodooHDA.kext/Contents/Info.plist" "$VOLUME_KEY")" = false ] || fail 'Il flag volume iniziale non è false.'
    /usr/bin/plutil -replace "$VOLUME_KEY" -bool true "$TEMP/volume-build/VoodooHDA.kext/Contents/Info.plist"
    /usr/bin/codesign --force --sign - "$TEMP/volume-build/VoodooHDA.kext"
    /usr/bin/codesign --verify --strict "$TEMP/volume-build/VoodooHDA.kext"
    /usr/bin/ditto --norsrc --noextattr --noacl --noqtn "$TEMP/volume-build/VoodooHDA.kext" "$draft/modified/VoodooHDA.kext"
    : > "$draft/SHA256SUMS"
    for path in Contents/Info.plist Contents/MacOS/VoodooHDA Contents/_CodeSignature/CodeResources; do
        printf '%s  %s\n' "$(hash "$draft/modified/VoodooHDA.kext/$path")" "$path" >> "$draft/SHA256SUMS"
    done
    manifest_hash=$(hash "$draft/SHA256SUMS")
    state_temp=$(/usr/bin/mktemp "$BACKUP/.state.XXXXXX")
    /bin/cp -p "$BACKUP/state.plist" "$state_temp"
    /usr/bin/plutil -insert VolumeManifestHash -string "$manifest_hash" "$state_temp"
    /usr/bin/plutil -insert VolumeDraftPath -string "$draft" "$state_temp"
    /usr/bin/plutil -insert VolumePhase -string ready "$state_temp"
    /usr/bin/plutil -insert VolumePrevious -string original "$state_temp"
    /usr/bin/plutil -insert VolumeTarget -string original "$state_temp"
    /usr/bin/plutil -lint "$state_temp" >/dev/null
    /bin/mv -f "$state_temp" "$BACKUP/state.plist"
    DRAFT=
    /bin/mv "$draft" "$VOLUME"
    validate_volume_backup
}
volume_source() {
    case "$1" in original|modified) printf '%s/%s/VoodooHDA.kext\n' "$VOLUME" "$1";; *) fail 'Stato driver volume sconosciuto.';; esac
}
stage_volume_driver() {
    local source=$1
    STAGING=$(/usr/bin/sudo /usr/bin/mktemp -d /Library/Extensions/.s540-audio.XXXXXX)
    /usr/bin/sudo /bin/chmod 755 "$STAGING"
    /usr/bin/sudo /usr/bin/ditto --norsrc --noextattr --noacl --noqtn "$source" "$STAGING/VoodooHDA.kext"
    /usr/bin/sudo /usr/sbin/chown -R root:wheel "$STAGING/VoodooHDA.kext"
    /usr/bin/sudo /usr/bin/find "$STAGING/VoodooHDA.kext" -type d -exec /bin/chmod 755 {} +
    /usr/bin/sudo /usr/bin/find "$STAGING/VoodooHDA.kext" -type f -exec /bin/chmod 644 {} +
    /usr/bin/sudo /bin/chmod 755 "$STAGING/VoodooHDA.kext/Contents/MacOS/VoodooHDA"
    driver_matches "$STAGING/VoodooHDA.kext" || fail 'Copia temporanea volume non verificata.'
    /usr/bin/codesign --verify --strict "$STAGING/VoodooHDA.kext"
}
resume_volume_swap() {
    local phase previous source
    if ! phase=$(readkey "$BACKUP/state.plist" VolumePhase); then return; fi
    case "$phase" in ready) return;; swapping) ;; *) fail 'Fase volume sconosciuta.';; esac
    validate_volume_backup
    if [ -e "$DRIVER" ] || [ -L "$DRIVER" ]; then
        driver_matches "$DRIVER" || fail 'Il driver è cambiato durante la sostituzione volume.'
    else
        previous=$(readkey "$BACKUP/state.plist" VolumePrevious)
        source=$(volume_source "$previous")
        /usr/bin/sudo -v
        stage_volume_driver "$source"
        /usr/bin/sudo /bin/mv "$STAGING/VoodooHDA.kext" "$DRIVER"
        /usr/bin/sudo /bin/rmdir "$STAGING"
        STAGING=
    fi
    state_set VolumePhase ready
}
volume_driver() {
    local wanted=$1 source previous result=0
    load_backup; validate_payload
    [ "$PHASE" = installed ] && [ "$CURRENT" = "$PREPARED" ] || fail 'La prova audio non è nello stato installato previsto.'
    require_sip3; runtime_bootargs
    if [ "$wanted" = modified ]; then
        make_volume_backup
    else
        validate_volume_backup
    fi
    resume_volume_swap
    driver_matches "$DRIVER" || fail 'Il driver installato non appartiene a questa prova.'
    source=$(volume_source "$wanted")
    if original_driver_matches "$DRIVER"; then previous=original; else previous=modified; fi
    if [ "$previous" != "$wanted" ]; then
        /usr/bin/sudo -v
        stage_volume_driver "$source"
        state_set VolumePrevious "$previous"
        state_set VolumeTarget "$wanted"
        state_set VolumePhase swapping
        /usr/bin/sudo /bin/mv "$DRIVER" "$STAGING/previous.kext"
        /usr/bin/sudo /bin/mv "$STAGING/VoodooHDA.kext" "$DRIVER"
        driver_matches "$DRIVER" || fail 'Sostituzione volume non verificata.'
        state_set VolumePhase ready
        /usr/bin/sudo /bin/rm -rf "$STAGING"
        STAGING=
    fi
    /usr/bin/sudo /usr/bin/kmutil rebuild || result=$?
    case "$result" in 0|27|28) ;; *) fail "Ricostruzione AuxKC non completata: codice $result. Il driver e il SIP della prova vengono conservati.";; esac
    if [ "$wanted" = modified ]; then
        echo 'Correzione volume preparata: solo VoodooHDAEnableVolumeChangeFix=true.'
    else
        echo 'Driver audio originale ripristinato byte per byte. Config e SIP della prova restano invariati.'
    fi
    echo 'Consenti la ricostruzione in Privacy e sicurezza se richiesto. Riavvia, poi prova volume e muto e apri VERIFICA-AUDIO.command.'
}
loaded_voodoo() {
    /usr/bin/kmutil showloaded > "$TEMP/runtime-kexts.txt" || fail 'Impossibile verificare i driver caricati. Il SIP della prova viene conservato.'
    /usr/bin/grep -qi 'org.voodoo.driver.VoodooHDA' "$TEMP/runtime-kexts.txt"
}
aux_without_voodoo() {
    /usr/bin/kmutil showloaded --collection aux --show all > "$TEMP/aux-kexts.txt" || fail 'Impossibile verificare la raccolta AuxKC. Il SIP della prova viene conservato.'
    /usr/bin/grep -qi 'org.voodoo.driver.VoodooHDA' "$TEMP/aux-kexts.txt" && fail 'VoodooHDA è ancora nella raccolta AuxKC. Completa approvazione e riavvio.'
    return 0
}
prepare() {
    validate_payload
    audio_controller
    if [ -e "$BACKUP" ] || [ -L "$BACKUP" ]; then
        load_backup
        [ "$PHASE" = prepared ] || fail 'Esiste già una prova audio in altra fase.'
        if [ "$CURRENT" = "$BEFORE" ]; then
            [ "$(active_sip)" = "$ORIGINAL_SIP" ] || fail 'Lo stato SIP non coincide con quello salvato prima della prova.'
            atomic_config "$BACKUP/prepared.plist" "$CURRENT"
        elif [ "$CURRENT" != "$PREPARED" ]; then
            fail 'Esiste già uno stato di ripristino SIP.'
        fi
        echo 'Preparazione già presente. Riavvia, poi apri INSTALLA-AUDIO.command.'; return
    fi
    validate_baseline "$CONFIG"
    ORIGINAL_SIP=$(active_sip)
    accepted_original_sip "$ORIGINAL_SIP"
    derive_states "$CONFIG" "$TEMP/prepared.plist" "$TEMP/restore-sip.plist" "$ORIGINAL_SIP"
    CURRENT=$(hash "$CONFIG")
    local final_backup=$BACKUP
    DRAFT=$(/usr/bin/mktemp -d "$OC/.backup-audio.XXXXXX")
    BACKUP=$DRAFT
    /bin/cp -p "$CONFIG" "$BACKUP/before.plist"
    /bin/cp -p "$TEMP/prepared.plist" "$BACKUP/prepared.plist"
    /bin/cp -p "$TEMP/restore-sip.plist" "$BACKUP/restore-sip.plist"
    cat > "$BACKUP/state.plist" <<STATE
<?xml version="1.0" encoding="UTF-8"?><!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd"><plist version="1.0"><dict>
<key>Format</key><string>2</string><key>Phase</key><string>prepared</string>
<key>OriginalSip</key><data>$ORIGINAL_SIP</data>
<key>before</key><string>$(hash "$BACKUP/before.plist")</string>
<key>prepared</key><string>$(hash "$BACKUP/prepared.plist")</string>
<key>restore-sip</key><string>$(hash "$BACKUP/restore-sip.plist")</string>
<key>EFI-Kexts</key><string>$(kext_tree_hash)</string>
</dict></plist>
STATE
    /usr/bin/plutil -lint "$BACKUP/state.plist" >/dev/null
    load_backup
    [ "$(hash "$CONFIG")" = "$CURRENT" ] || fail 'Il config è cambiato durante la preparazione.'
    [ "$(active_sip)" = "$ORIGINAL_SIP" ] || fail 'Il SIP attivo è cambiato durante la preparazione.'
    /bin/mv "$DRAFT" "$final_backup"
    DRAFT=
    BACKUP=$final_backup
    atomic_config "$BACKUP/prepared.plist" "$CURRENT"
    echo 'Preparazione completata. Riavvia con questa EFI, poi apri INSTALLA-AUDIO.command.'
    echo 'Sono cambiati solo SIP, NVRAM/Delete csr-active-config, AppleALC Enabled e il layout VoodooHDA.'
}
install_driver() {
    load_backup; validate_payload
    [ "$CURRENT" = "$PREPARED" ] || fail 'La EFI preparata non è attiva sul disco di avvio.'
    case "$PHASE" in prepared|copying|installed) ;; *) fail 'La prova è in fase di ripristino.';; esac
    require_sip3; runtime_bootargs; audio_controller
    /usr/bin/kmutil showloaded > "$TEMP/loaded.txt" || fail 'Impossibile verificare i driver già caricati.' 
    /usr/bin/grep -Eq 'com\.apple\.driver\.AppleHDA|as\.vit9696\.AppleALC' "$TEMP/loaded.txt" && fail 'È attivo un driver AppleHDA/AppleALC incompatibile.'
    [ ! -e /Library/Extensions/AppleHDA.kext ] && [ ! -L /Library/Extensions/AppleHDA.kext ] || fail 'AppleHDA è già installato in Library/Extensions.'
    if [ -e "$DRIVER" ] || [ -L "$DRIVER" ]; then
        [ "$PHASE" != prepared ] && driver_matches "$DRIVER" || fail 'È presente un VoodooHDA non appartenente a questa prova.'
    else
        case "$PHASE" in prepared|copying) ;; *) fail 'Il driver della prova è stato rimosso fuori dal ripristino.';; esac
        /usr/bin/sudo -v
        STAGING=$(/usr/bin/sudo /usr/bin/mktemp -d /Library/Extensions/.s540-audio.XXXXXX)
        /usr/bin/sudo /bin/chmod 755 "$STAGING"
        /usr/bin/sudo /usr/bin/ditto "$ASSETS/VoodooHDA.kext" "$STAGING/VoodooHDA.kext"
        /usr/bin/sudo /usr/sbin/chown -R root:wheel "$STAGING/VoodooHDA.kext"
        /usr/bin/sudo /usr/bin/find "$STAGING/VoodooHDA.kext" -type d -exec /bin/chmod 755 {} +
        /usr/bin/sudo /usr/bin/find "$STAGING/VoodooHDA.kext" -type f -exec /bin/chmod 644 {} +
        /usr/bin/sudo /bin/chmod 755 "$STAGING/VoodooHDA.kext/Contents/MacOS/VoodooHDA"
        driver_matches "$STAGING/VoodooHDA.kext" || fail 'Copia del driver incompleta. La copia temporanea viene rimossa.'
        /usr/bin/codesign --verify --strict "$STAGING/VoodooHDA.kext"
        state_set Phase copying
        /usr/bin/sudo /bin/mv "$STAGING/VoodooHDA.kext" "$DRIVER"
        /usr/bin/sudo /bin/rmdir "$STAGING"
        STAGING=
    fi
    state_set Phase installed
    local result=0
    /usr/bin/sudo /usr/bin/kmutil load -p "$DRIVER" || result=$?
    case "$result" in 0) echo 'Richiesta di caricamento completata.';; 27|28) echo 'macOS richiede l’approvazione del driver o un riavvio.';; *) fail "kmutil ha restituito $result. Non modificare il SIP ulteriormente.";; esac
    echo 'In Impostazioni di Sistema apri Privacy e sicurezza e consenti il driver, se richiesto. Poi riavvia e apri VERIFICA-AUDIO.command.'
}
verify() {
    /usr/sbin/system_profiler SPAudioDataType
    /usr/sbin/ioreg -r -c VoodooHDADevice -l -w 0 | /usr/bin/grep 'VoodooHDAEnableVolumeChangeFix' || true
    /usr/bin/kmutil showloaded 2>/dev/null | /usr/bin/grep -E 'AppleHDA|AppleALC|Lilu|VoodooHDA' || true
    echo 'Controlla altoparlanti, cuffie e microfono nelle impostazioni Audio. Nessuna modifica effettuata.'
}
restore() {
    load_backup; validate_payload
    case "$PHASE" in
        prepared)
            if [ "$CURRENT" = "$RESTORE_SIP" ] && [ "$RESTORE_SIP" != "$BEFORE" ]; then
                state_set Phase sip-pending
                restore; return
            fi
            if [ "$CURRENT" = "$BEFORE" ]; then
                [ "$(active_sip)" = "$ORIGINAL_SIP" ] || fail 'Riavvia prima di completare: il SIP deve coincidere con lo stato originale salvato.'
                [ ! -e "$DRIVER" ] && [ ! -L "$DRIVER" ] || fail 'È presente un driver non registrato.'
                loaded_voodoo && fail 'VoodooHDA risulta ancora caricato.'
                state_set Phase complete
                echo 'Config originale già presente; ripristino completato.'; return
            fi
            [ "$CURRENT" = "$PREPARED" ] || fail 'Lo stato preparato non coincide.'
            [ ! -e "$DRIVER" ] && [ ! -L "$DRIVER" ] || fail 'È presente un driver non registrato; non viene rimosso.'
            atomic_config "$BACKUP/restore-sip.plist" "$CURRENT"
            state_set Phase sip-pending
            echo 'SIP originale preparato. Riavvia, poi riapri RIPRISTINA-AUDIO.command per il ripristino byte per byte.'
            ;;
        copying)
            [ "$CURRENT" = "$PREPARED" ] || fail 'Lo stato preparato non coincide.'
            if [ -e "$DRIVER" ] || [ -L "$DRIVER" ]; then
                driver_matches "$DRIVER" || fail 'Il driver in copia non coincide.'
                state_set Phase installed
                restore
            else
                state_set Phase prepared
                restore
            fi
            ;;
        installed|removal-pending)
            [ "$CURRENT" = "$PREPARED" ] || fail 'Conserva la EFI della prova fino alla rimozione del driver.'
            require_sip3
            resume_volume_swap
            if [ "$PHASE" = installed ]; then
                driver_matches "$DRIVER" || fail 'Il driver installato è stato modificato; non viene rimosso.'
                [ ! -e "$BACKUP/removed-VoodooHDA.kext" ] && [ ! -L "$BACKUP/removed-VoodooHDA.kext" ] || fail 'Esiste già un driver spostato nel backup.'
                state_set Phase removal-pending
                /usr/bin/sudo /bin/mv "$DRIVER" "$BACKUP/removed-VoodooHDA.kext"
            elif [ -e "$DRIVER" ] || [ -L "$DRIVER" ]; then
                driver_matches "$DRIVER" || fail 'Il driver in rimozione non coincide.'
                [ ! -e "$BACKUP/removed-VoodooHDA.kext" ] || fail 'Sono presenti due copie del driver in rimozione.'
                /usr/bin/sudo /bin/mv "$DRIVER" "$BACKUP/removed-VoodooHDA.kext"
            fi
            driver_matches "$BACKUP/removed-VoodooHDA.kext" || fail 'Il driver spostato nel backup non coincide.'
            state_set RemovalBoot "$(boot_session)"
            if loaded_voodoo; then
                local result=0
                /usr/bin/sudo /usr/bin/kmutil rebuild || result=$?
                case "$result" in 0|27|28) ;; *) fail "Ricostruzione AuxKC non completata: codice $result. Il SIP della prova resta attivo.";; esac
                state_set Phase removal-requested
                echo 'Rimozione richiesta. Consenti la ricostruzione in Privacy e sicurezza se appare, poi riavvia e riapri RIPRISTINA-AUDIO.command.'
            else
                # A reboot/approval is still required to prove the rebuilt collection no longer includes the driver.
                local result=0
                /usr/bin/sudo /usr/bin/kmutil rebuild || result=$?
                case "$result" in 0|27|28) ;; *) fail "Ricostruzione AuxKC non completata: codice $result. Il SIP della prova resta attivo.";; esac
                state_set Phase removal-requested
                echo 'Riavvia, poi riapri RIPRISTINA-AUDIO.command. La EFI della prova resta attiva fino al controllo.'
            fi
            ;;
        removal-requested)
            if [ "$CURRENT" = "$RESTORE_SIP" ] && [ "$RESTORE_SIP" != "$BEFORE" ]; then
                state_set Phase sip-pending
                restore; return
            fi
            [ "$CURRENT" = "$PREPARED" ] || fail 'Il config è cambiato durante la rimozione.'
            [ "$(boot_session)" != "$(readkey "$BACKUP/state.plist" RemovalBoot)" ] || fail 'Riavvia prima di proseguire: la rimozione deve essere verificata in una nuova sessione.'
            [ ! -e "$DRIVER" ] && [ ! -L "$DRIVER" ] || fail 'Il driver risulta ancora installato.'
            loaded_voodoo && fail 'VoodooHDA è ancora caricato. Completa approvazione/riavvio prima di ripristinare il SIP.'
            aux_without_voodoo
            atomic_config "$BACKUP/restore-sip.plist" "$CURRENT"
            state_set Phase sip-pending
            echo 'Driver assente. SIP originale preparato. Riavvia e riapri RIPRISTINA-AUDIO.command per terminare.'
            ;;
        sip-pending)
            if [ "$CURRENT" = "$BEFORE" ]; then
                [ "$(active_sip)" = "$ORIGINAL_SIP" ] || fail 'Il SIP originale salvato non è ancora attivo.'
                loaded_voodoo && fail 'VoodooHDA risulta ancora caricato.'
                state_set Phase complete
                echo 'Config originale già ripristinato byte per byte.'; return
            fi
            [ "$CURRENT" = "$RESTORE_SIP" ] || fail 'Il config di ripristino SIP non coincide.'
            [ "$(active_sip)" = "$ORIGINAL_SIP" ] || fail 'Riavvia prima di terminare: il SIP attivo deve coincidere con quello originale salvato.'
            loaded_voodoo && fail 'VoodooHDA risulta ancora caricato.'
            atomic_config "$BACKUP/before.plist" "$CURRENT"
            state_set Phase complete
            echo 'Config originale ripristinato byte per byte. Il backup audio viene conservato.'
            ;;
        complete)
            [ "$CURRENT" = "$BEFORE" ] || fail 'Il config è cambiato dopo il ripristino.'
            [ "$(active_sip)" = "$ORIGINAL_SIP" ] || fail 'Il SIP attivo è cambiato dopo il ripristino.'
            echo 'Ripristino già completato. Nessuna modifica.'
            ;;
        *) fail 'Fase del backup sconosciuta.';;
    esac
}
native
TEMP=$(/usr/bin/mktemp -d /tmp/s540-audio.XXXXXX)
case "$MODE" in prepare) prepare;; install) install_driver;; verify) verify;; restore) restore;; volume) volume_driver modified;; volume-restore) volume_driver original;; *) fail 'Operazione sconosciuta.';; esac
