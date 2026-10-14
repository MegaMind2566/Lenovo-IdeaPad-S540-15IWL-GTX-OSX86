#!/bin/bash
# Native macOS Intel, Bash 3.2. One reversible boot-argument test only.
set -euo pipefail
export LC_ALL=C
umask 077

GUID=7C436110-AB2A-4BBB-A880-FE41995C9F82
GPU='DeviceProperties.Add.PciRoot(0x0)/Pci(0x2,0x0)'
ARGS="NVRAM.Add.$GUID.boot-args"
SIP="NVRAM.Add.$GUID.csr-active-config"
FLAG=-igfxblr
WEG_RELEASE_SHA256=17944705056d6d929661da2b60dd859e753228aad3ea96a3e8d0d803bc30bd45
FRAMEBUFFER_UUID=7E294F0F-852E-3252-B54D-61D9A7BBE6B2
OWNER=it.s540.tahoe.backlight-boot-test
MODE=${1:-test}
[ "$#" -eq 0 ] || shift
[ "$#" -le 1 ] || { echo 'Indica al massimo il percorso del disco di avvio.' >&2; exit 1; }
BOOTROOT=${1:-'/Volumes/240 GB'}
OC="$BOOTROOT/EFI/OC"
CONFIG="$OC/config.plist"
BACKUP="$OC/backup-schermo-avvio"
TEMP=''
DRAFT=''
CONFIG_TEMP=''

cleanup() {
    if [ -n "$CONFIG_TEMP" ] && [ -f "$CONFIG_TEMP" ] && [ ! -L "$CONFIG_TEMP" ]; then /bin/rm -f "$CONFIG_TEMP"; fi
    if [ -n "$DRAFT" ] && [ -d "$DRAFT" ] && [ ! -L "$DRAFT" ]; then /bin/rm -rf "$DRAFT"; fi
    if [ -n "$TEMP" ] && [ -d "$TEMP" ] && [ ! -L "$TEMP" ]; then /bin/rm -rf "$TEMP"; fi
}
trap cleanup EXIT
trap 'echo "Operazione non completata. Conserva il backup schermo e leggi il messaggio precedente prima di riavviare." >&2' ERR
fail() { echo "Operazione annullata: $*" >&2; exit 1; }
readkey() { /usr/bin/plutil -extract "$2" raw -o - "$1" 2>/dev/null; }
hash() { /usr/bin/shasum -a 256 "$1" | /usr/bin/awk '{print $1}'; }
ordinary() { [ -e "$1" ] && [ ! -L "$1" ] || fail "Percorso assente o simbolico: $1"; }
no_links() { [ -z "$(/usr/bin/find "$1" -type l -print)" ] || fail 'La cartella contiene collegamenti simbolici.'; }
no_symlink_chain() {
    local path=$1 part='' component
    local old_ifs=$IFS
    case "$path" in /*) ;; *) fail 'Usa un percorso assoluto per il disco di avvio.';; esac
    case "$path" in *$'\n'*|*$'\r'*) fail 'Il percorso contiene caratteri non ammessi.';; esac
    IFS=/
    read -r -a components <<< "$path"
    IFS=$old_ifs
    for component in "${components[@]}"; do
        [ -n "$component" ] || continue
        case "$component" in .|..) fail 'Il percorso non deve contenere . o ..';; esac
        part="$part/$component"
        [ ! -L "$part" ] || fail "Collegamento simbolico nel percorso: $part"
    done
}
typed() {
    /usr/bin/plutil -extract "$2" xml1 -o - "$1" > "$TEMP/type.plist" 2>/dev/null || return 1
    /usr/bin/grep -Eq "<$3([ />])" "$TEMP/type.plist"
}
data_equals() {
    typed "$1" "$2" data || fail "La proprietà $2 deve essere Data."
    [ "$(readkey "$1" "$2" | /usr/bin/tr -d '[:space:]')" = "$3" ] || fail "La proprietà $2 non coincide con la EFI verificata."
}
string_value() {
    typed "$1" "$2" string || fail "La proprietà $2 deve essere una stringa."
    readkey "$1" "$2"
}
contains_flag() { case " $1 " in *" $2 "*) return 0;; *) return 1;; esac; }
reject_unsafe_args() {
    local args=$1
    case "$args" in *$'\n'*|*$'\r'*|*$'\t'*) fail 'I boot-args contengono separatori non previsti.';; esac
    contains_flag "$args" -igfxvesa && fail 'Riparti dal desktop con accelerazione Intel attiva: è presente -igfxvesa.'
    contains_flag "$args" -x && fail 'La configurazione usa l’avvio sicuro.'
    contains_flag "$args" -igfxblt && fail 'È già presente -igfxblt. Non combinare le due prove della retroilluminazione.'
    return 0
}
property_absent() {
    if /usr/bin/plutil -extract "$GPU.$2" xml1 -o - "$1" > "$TEMP/property.plist" 2>/dev/null; then
        fail "La proprietà $2 è già presente. Non combinare correzioni della retroilluminazione, anche se il valore è zero."
    fi
}
validate_config() {
    local file=$1 allow_flag=$2 args
    /usr/bin/plutil -lint "$file" >/dev/null
    data_equals "$file" "$GPU.AAPL,ig-platform-id" CQClPg==
    data_equals "$file" "$GPU.device-id" pT4AAA==
    data_equals "$file" "$GPU.framebuffer-patch-enable" AQAAAA==
    data_equals "$file" "$GPU.framebuffer-stolenmem" AAAwAQ==
    data_equals "$file" "$GPU.framebuffer-fbmem" AACQAA==
    data_equals "$file" "$SIP" AwAAAA==
    [ "$(string_value "$file" Misc.Security.SecureBootModel)" = Disabled ] || fail 'SecureBootModel non coincide con la EFI verificata.'
    args=$(string_value "$file" "$ARGS")
    reject_unsafe_args "$args"
    contains_flag "$args" voodoo-layout-id=11 || fail 'Manca il layout audio già funzionante.'
    if [ "$allow_flag" = no ]; then
        contains_flag "$args" "$FLAG" && fail 'Il flag -igfxblr è già presente senza un backup di questa prova.'
    fi
    property_absent "$file" enable-backlight-registers-fix
    property_absent "$file" enable-backlight-registers-alternative-fix
}
version_at_least_172() {
    local major minor patch rest
    case "$1" in *[!0-9.]*|*.*.*.*|'') return 1;; esac
    IFS=. read -r major minor patch rest <<< "$1"
    [ -n "$major" ] && [ -n "$minor" ] && [ -n "$patch" ] && [ -z "${rest:-}" ] || return 1
    [ "$((10#$major))" -gt 1 ] || { [ "$((10#$major))" -eq 1 ] && { [ "$((10#$minor))" -gt 7 ] || { [ "$((10#$minor))" -eq 7 ] && [ "$((10#$patch))" -ge 2 ]; }; }; }
}
kernel_limit_allows_256() {
    local value=$1 mode=$2 major minor patch rest
    [ -n "$value" ] || return 0
    case "$value" in *[!0-9.]*|*.*.*.*) return 1;; esac
    IFS=. read -r major minor patch rest <<< "$value"
    [ -n "$major" ] && [ -n "$minor" ] && [ -n "$patch" ] && [ -z "${rest:-}" ] || return 1
    if [ "$mode" = min ]; then
        [ "$((10#$major))" -lt 25 ] || { [ "$((10#$major))" -eq 25 ] && { [ "$((10#$minor))" -lt 6 ] || { [ "$((10#$minor))" -eq 6 ] && [ "$((10#$patch))" -eq 0 ]; }; }; }
    else
        [ "$((10#$major))" -gt 25 ] || { [ "$((10#$major))" -eq 25 ] && [ "$((10#$minor))" -ge 6 ]; }
    fi
}
validate_kext() {
    local file=$1 name=$2 expected_id=$3 i=0 path count=0 index='' value info binary
    typed "$file" Kernel.Add array || fail 'Kernel/Add non contiene l’array previsto.'
    while /usr/bin/plutil -extract "Kernel.Add.$i" xml1 -o - "$file" > "$TEMP/kernel-entry.plist" 2>/dev/null; do
        path=$(string_value "$file" "Kernel.Add.$i.BundlePath")
        if [ "$path" = "$name.kext" ]; then count=$((count+1)); index=$i; fi
        i=$((i+1))
    done
    [ "$count" = 1 ] || fail "$name deve comparire una sola volta in Kernel/Add."
    typed "$file" "Kernel.Add.$index.Enabled" true || fail "$name deve essere abilitato."
    case "$(string_value "$file" "Kernel.Add.$index.Arch")" in Any|x86_64) ;; *) fail "$name non è abilitato per macOS Intel.";; esac
    [ "$(string_value "$file" "Kernel.Add.$index.ExecutablePath")" = "Contents/MacOS/$name" ] || fail "Il percorso eseguibile di $name non coincide."
    [ "$(string_value "$file" "Kernel.Add.$index.PlistPath")" = Contents/Info.plist ] || fail "Il percorso plist di $name non coincide."
    value=$(string_value "$file" "Kernel.Add.$index.MinKernel")
    kernel_limit_allows_256 "$value" min || fail "$name non è abilitato per Darwin 25.6.0."
    value=$(string_value "$file" "Kernel.Add.$index.MaxKernel")
    kernel_limit_allows_256 "$value" max || fail "$name non è abilitato per Darwin 25.6.0."
    info="$OC/Kexts/$name.kext/Contents/Info.plist"
    binary="$OC/Kexts/$name.kext/Contents/MacOS/$name"
    for path in "$OC/Kexts/$name.kext" "$OC/Kexts/$name.kext/Contents" "$OC/Kexts/$name.kext/Contents/MacOS" "$info" "$binary"; do ordinary "$path"; done
    no_links "$OC/Kexts/$name.kext"
    [ -f "$info" ] && [ -f "$binary" ] || fail "Il bundle $name non contiene i file previsti."
    /usr/bin/plutil -lint "$info" >/dev/null
    [ "$(string_value "$info" CFBundleIdentifier)" = "$expected_id" ] || fail "Identificatore inatteso per $name."
    value=$(string_value "$info" CFBundleVersion)
    if [ "$name" = WhateverGreen ]; then
        [ "$value" = 1.7.1 ] || fail 'Questa prova è stata preparata per WhateverGreen 1.7.1.'
        [ "$(hash "$binary")" = "$WEG_RELEASE_SHA256" ] || fail 'Il binario WhateverGreen non coincide con la build RELEASE verificata.'
    else
        version_at_least_172 "$value" || fail 'Serve Lilu 1.7.2 o successivo.'
    fi
}
validate_runtime() {
    local lilu_version
    [ "$(/usr/bin/uname -r)" = 25.6.0 ] || fail 'Il kernel attivo non è Darwin 25.6.0. Raccogli prima la diagnosi aggiornata; nessuna modifica.'
    [ -x /usr/bin/kmutil ] || fail 'Manca kmutil.'
    /usr/bin/kmutil showloaded > "$TEMP/runtime-kexts.txt" 2> "$TEMP/runtime-kexts-errors.txt" || fail 'Impossibile leggere i driver caricati. Raccogli prima la diagnosi; nessuna modifica.'
    /usr/bin/grep -F 'com.apple.driver.AppleIntelCFLGraphicsFramebuffer' "$TEMP/runtime-kexts.txt" > "$TEMP/framebuffer-line.txt" || fail 'Il framebuffer CFL non è caricato. Raccogli prima la diagnosi; nessuna modifica.'
    /usr/bin/grep -Fiq "$FRAMEBUFFER_UUID" "$TEMP/framebuffer-line.txt" || fail 'Il framebuffer attivo ha un UUID diverso da quello analizzato. Raccogli prima la diagnosi; nessuna modifica.'
    /usr/bin/grep -Eq 'as\.vit9696\.WhateverGreen[[:space:]]+\(1\.7\.1\)' "$TEMP/runtime-kexts.txt" || fail 'WhateverGreen 1.7.1 non risulta caricato. Raccogli prima la diagnosi; nessuna modifica.'
    lilu_version=$(/usr/bin/awk '{ for (i=1;i<=NF;i++) if ($i=="as.vit9696.Lilu") print $(i+1) }' "$TEMP/runtime-kexts.txt")
    lilu_version=${lilu_version#(}; lilu_version=${lilu_version%)}
    version_at_least_172 "$lilu_version" || fail 'Lilu 1.7.2 o successivo non risulta caricato. Raccogli prima la diagnosi; nessuna modifica.'
}
native() {
    local path runtime_args
    [ "$(/usr/bin/uname -s)" = Darwin ] && [ "$(/usr/bin/uname -m)" = x86_64 ] || fail 'Serve macOS Intel.'
    case "$(/usr/bin/uname -r)" in 25.*) ;; *) fail 'Questa prova richiede macOS Tahoe (Darwin 25).';; esac
    if [ "$MODE" = test ]; then
        [ -d /System/Volumes/Data ] && [ -d /Users ] || fail 'Esegui la prova dal desktop Tahoe, non dalla Recovery.'
        [ "$(/usr/bin/id -u)" -ne 0 ] || fail 'Apri la prova dal tuo account.'
    fi
    for command in plutil shasum awk grep tr find mktemp cmp; do
        [ -x "/usr/bin/$command" ] || fail "Manca il comando macOS $command."
    done
    no_symlink_chain "$BOOTROOT"
    for path in "$BOOTROOT" "$BOOTROOT/EFI" "$OC" "$CONFIG"; do ordinary "$path"; done
    [ -f "$CONFIG" ] || fail 'config.plist non è un file ordinario.'
    [ -w "$OC" ] && [ -w "$CONFIG" ] || fail 'Il disco di avvio non è scrivibile dal tuo account.'
    /usr/bin/plutil -lint "$CONFIG" >/dev/null
    if [ "$MODE" = test ]; then
        ordinary "$OC/Kexts"
        [ -x /usr/sbin/sysctl ] || fail 'Manca sysctl.'
        runtime_args=$(/usr/sbin/sysctl -n kern.bootargs) || fail 'Impossibile leggere i boot-args attivi.'
        reject_unsafe_args "$runtime_args"
    fi
}
derive_tested() {
    local before=$1 tested=$2 args
    validate_config "$before" no
    args=$(string_value "$before" "$ARGS")
    /bin/cp -p "$before" "$tested"
    /usr/bin/plutil -replace "$ARGS" -string "$args $FLAG" "$tested"
    /usr/bin/plutil -lint "$tested" >/dev/null
    validate_config "$tested" yes
}
make_state() {
    local before=$1 tested=$2 state=$3
    printf '%s\n' '<?xml version="1.0" encoding="UTF-8"?>' '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">' '<plist version="1.0"><dict/></plist>' > "$state"
    /usr/bin/plutil -insert Format -integer 1 "$state"
    /usr/bin/plutil -insert Owner -string "$OWNER" "$state"
    /usr/bin/plutil -insert BeforeSHA256 -string "$(hash "$before")" "$state"
    /usr/bin/plutil -insert TestedSHA256 -string "$(hash "$tested")" "$state"
    /usr/bin/plutil -insert DeltaKey -string "$ARGS" "$state"
    /usr/bin/plutil -insert AddedBootArg -string "$FLAG" "$state"
    /usr/bin/plutil -lint "$state" >/dev/null
}
load_backup() {
    local file expected_dir="$TEMP/expected"
    ordinary "$BACKUP"; [ -d "$BACKUP" ] || fail 'Il percorso backup non è una cartella.'
    no_links "$BACKUP"
    for file in before tested state; do
        ordinary "$BACKUP/$file.plist"
        [ -f "$BACKUP/$file.plist" ] || fail 'Il backup contiene un percorso non ordinario.'
        /usr/bin/plutil -lint "$BACKUP/$file.plist" >/dev/null
    done
    [ "$(readkey "$BACKUP/state.plist" Format)" = 1 ] && [ "$(string_value "$BACKUP/state.plist" Owner)" = "$OWNER" ] || fail 'La cartella backup non appartiene a questa prova.'
    [ "$(hash "$BACKUP/before.plist")" = "$(string_value "$BACKUP/state.plist" BeforeSHA256)" ] || fail 'Il backup originale è stato modificato.'
    [ "$(hash "$BACKUP/tested.plist")" = "$(string_value "$BACKUP/state.plist" TestedSHA256)" ] || fail 'Il backup della prova è stato modificato.'
    /bin/mkdir -p "$expected_dir"
    derive_tested "$BACKUP/before.plist" "$expected_dir/tested.plist"
    /usr/bin/cmp -s "$expected_dir/tested.plist" "$BACKUP/tested.plist" || fail 'Lo snapshot della prova non contiene soltanto il flag previsto.'
    make_state "$BACKUP/before.plist" "$expected_dir/tested.plist" "$expected_dir/state.plist"
    /usr/bin/plutil -convert xml1 -o "$expected_dir/stored-state.plist" "$BACKUP/state.plist"
    /usr/bin/plutil -convert xml1 "$expected_dir/state.plist"
    /usr/bin/cmp -s "$expected_dir/state.plist" "$expected_dir/stored-state.plist" || fail 'Il manifest del backup non coincide con questa prova.'
    BEFORE=$(hash "$BACKUP/before.plist")
    TESTED=$(hash "$BACKUP/tested.plist")
    CURRENT=$(hash "$CONFIG")
    case "$CURRENT" in "$BEFORE"|"$TESTED") ;; *) fail 'Il config è cambiato dopo questa prova. Nessuna sovrascrittura.';; esac
}
atomic_config() {
    local wanted=$1 expected=$2 wanted_hash
    ordinary "$CONFIG"
    [ "$(hash "$CONFIG")" = "$expected" ] || fail 'Il config è cambiato durante i controlli.'
    wanted_hash=$(hash "$wanted")
    CONFIG_TEMP=$(/usr/bin/mktemp "$OC/.schermo-config.XXXXXX")
    /bin/cp -p "$wanted" "$CONFIG_TEMP"
    /usr/bin/plutil -lint "$CONFIG_TEMP" >/dev/null
    [ "$(hash "$CONFIG_TEMP")" = "$wanted_hash" ] || fail 'Copia config incompleta.'
    ordinary "$CONFIG"
    [ "$(hash "$CONFIG")" = "$expected" ] || fail 'Il config è cambiato durante la copia.'
    /bin/mv -f "$CONFIG_TEMP" "$CONFIG"
    CONFIG_TEMP=''
    [ "$(hash "$CONFIG")" = "$wanted_hash" ] || fail 'Scrittura non verificata. Non riavviare: conserva before.plist nel backup schermo.'
}
test_backlight() {
    local final_backup=$BACKUP original_hash
    validate_runtime
    validate_kext "$CONFIG" WhateverGreen as.vit9696.WhateverGreen
    validate_kext "$CONFIG" Lilu as.vit9696.Lilu
    if [ -e "$BACKUP" ] || [ -L "$BACKUP" ]; then
        load_backup
    else
        validate_config "$CONFIG" no
        original_hash=$(hash "$CONFIG")
        DRAFT=$(/usr/bin/mktemp -d "$OC/.backup-schermo.XXXXXX")
        /bin/cp -p "$CONFIG" "$DRAFT/before.plist"
        [ "$(hash "$DRAFT/before.plist")" = "$original_hash" ] || fail 'Il config è cambiato durante la lettura.'
        derive_tested "$DRAFT/before.plist" "$DRAFT/tested.plist"
        make_state "$DRAFT/before.plist" "$DRAFT/tested.plist" "$DRAFT/state.plist"
        BACKUP=$DRAFT
        load_backup
        [ "$(hash "$CONFIG")" = "$original_hash" ] || fail 'Il config è cambiato durante la preparazione.'
        [ ! -e "$final_backup" ] && [ ! -L "$final_backup" ] || fail 'È comparso un backup durante i controlli.'
        /bin/mv "$DRAFT" "$final_backup"
        DRAFT=''
        BACKUP=$final_backup
    fi
    if [ "$CURRENT" = "$TESTED" ]; then
        echo 'La prova -igfxblr è già preparata. Nessuna ulteriore modifica.'
    else
        atomic_config "$BACKUP/tested.plist" "$CURRENT"
        echo 'Prova preparata: aggiunto soltanto -igfxblr ai boot-args.'
    fi
    echo 'Riavvia dalla stessa EFI e misura il tempo dello schermo nero prima del login.'
    echo 'Confrontalo con i circa due minuti precedenti. Questa prova non garantisce la correzione.'
    echo 'Il backup originale è conservato in EFI/OC/backup-schermo-avvio.'
    echo 'Per annullare usa ANNULLA-SCHERMO-AVVIO.command prima di altre modifiche EFI o del ripristino audio completo.'
    echo 'Il comando di annullamento funziona anche dal Terminale della Recovery, specificando il disco di avvio se il nome è diverso.'
}
restore_backlight() {
    [ -e "$BACKUP" ] || [ -L "$BACKUP" ] || fail 'Non esiste un backup di questa prova. Nessuna modifica.'
    load_backup
    if [ "$CURRENT" = "$BEFORE" ]; then
        echo 'Il config originale è già presente. Nessuna modifica.'
    else
        atomic_config "$BACKUP/before.plist" "$CURRENT"
        echo 'Config precedente alla prova ripristinato byte per byte.'
        echo 'Riavvia dalla stessa EFI. Il backup viene conservato.'
    fi
    echo 'Ora puoi procedere con altre modifiche EFI o con il ripristino audio completo.'
}

case "$MODE" in test|restore) ;; *) fail 'Modalità non riconosciuta: usa test o restore.';; esac
native
TEMP=$(/usr/bin/mktemp -d /private/tmp/s540-schermo-avvio.XXXXXX)
if [ "$MODE" = test ]; then test_backlight; else restore_backlight; fi
