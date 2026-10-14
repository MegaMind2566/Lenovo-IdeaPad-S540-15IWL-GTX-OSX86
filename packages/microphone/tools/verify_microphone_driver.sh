#!/bin/bash
# Native macOS / Bash 3.2. Read-only ownership check for the audio diagnostic.
# stdout contains only the verified installed Mach-O SHA256.
set -euo pipefail
umask 077
export LC_ALL=C

TEMP=''
cleanup() { [ -z "$TEMP" ] || /bin/rm -rf "$TEMP"; }
trap cleanup EXIT
fail() { printf 'Verifica driver microfono: %s\n' "$*" >&2; exit 1; }

[ "$#" -eq 2 ] || fail 'Servono il percorso del bundle e quello del backup audio.'
DRIVER=$1
BACKUP=$2
VOLUME="$BACKUP/volume-test"
STATE="$BACKUP/state.plist"
KEY=IOKitPersonalities.VoodooHDA.VoodooHDAEnableVolumeChangeFix
ORIGINAL_INFO='21b886b5449b9a0739422b6720ea2bc04fdcc477f79e1e3cece021033a51bf1a'
ORIGINAL_MACHO='932a7c9e46a65fdab7c8729f599c1094b568ae4fc7f17dad9818c83e833a0973'
ORIGINAL_RESOURCES='6686de10a28a2fe11b36cbb86dcbacc827cfc4ea116b4dabf1845e5aee629e9b'

hash() { /usr/bin/shasum -a 256 "$1" | /usr/bin/awk '{print $1}'; }
ordinary_file() { [ -f "$1" ] && [ ! -L "$1" ]; }
readkey() { /usr/bin/plutil -extract "$2" raw -o - "$1" 2>/dev/null; }
safe_path() {
    local path=$1
    case "$path" in /*) ;; *) fail 'I percorsi devono essere assoluti.';; esac
    case "$path" in */../*|*/./*|*/..|*/.) fail 'Il percorso contiene componenti relative.';; esac
    while [ "$path" != / ]; do
        [ ! -L "$path" ] || fail 'Il percorso contiene un collegamento simbolico.'
        path=${path%/*}
        [ -n "$path" ] || path=/
    done
}
validate_bundle_shape() {
    local bundle=$1 links special count path
    safe_path "$bundle"
    [ -d "$bundle" ] && [ ! -L "$bundle" ] || fail 'Il bundle non è una cartella ordinaria.'
    links=$(/usr/bin/find "$bundle" -type l -print) || fail 'Impossibile controllare i collegamenti del bundle.'
    [ -z "$links" ] || fail 'Il bundle contiene collegamenti simbolici.'
    special=$(/usr/bin/find "$bundle" ! -type f ! -type d -print) || fail 'Impossibile controllare i file del bundle.'
    [ -z "$special" ] || fail 'Il bundle contiene file speciali.'
    count=$(/usr/bin/find "$bundle" -type f -print | /usr/bin/wc -l | /usr/bin/tr -d '[:space:]') || fail 'Impossibile contare i file del bundle.'
    [ "$count" = 3 ] || fail 'Il bundle deve contenere esattamente i tre file previsti.'
    for path in Contents/Info.plist Contents/MacOS/VoodooHDA Contents/_CodeSignature/CodeResources; do
        ordinary_file "$bundle/$path" || fail 'Manca un file ordinario del bundle.'
    done
}
original_matches() {
    [ "$(hash "$1/Contents/Info.plist")" = "$ORIGINAL_INFO" ] &&
    [ "$(hash "$1/Contents/MacOS/VoodooHDA")" = "$ORIGINAL_MACHO" ] &&
    [ "$(hash "$1/Contents/_CodeSignature/CodeResources")" = "$ORIGINAL_RESOURCES" ]
}
verify_signature() {
    if ! /usr/bin/codesign --verify --strict "$1" > /dev/null 2> "$TEMP/codesign-errors.txt"; then
        /bin/cat "$TEMP/codesign-errors.txt" >&2
        fail 'La firma del bundle non è valida.'
    fi
}
manifest_matches() {
    local bundle=$1 expected path
    while IFS=' ' read -r expected path; do
        path=${path# }
        [ "$(hash "$bundle/$path")" = "$expected" ] || return 1
    done < "$TEMP/manifest-checked.txt"
}

validate_bundle_shape "$DRIVER"
TEMP=$(/usr/bin/mktemp -d /tmp/s540-microphone-verify.XXXXXX) || fail 'Impossibile creare la cartella temporanea privata.'
if original_matches "$DRIVER"; then
    verify_signature "$DRIVER"
    original_matches "$DRIVER" || fail 'Il driver è cambiato durante la verifica.'
    printf '%s\n' "$ORIGINAL_MACHO"
    exit 0
fi

# This route reads only the V3 ownership metadata and driver copies. It neither
# reads config.plist nor uses the audio installer's state/draft recovery logic.
safe_path "$BACKUP"
safe_path "$STATE"
safe_path "$VOLUME"
[ -d "$BACKUP" ] && [ ! -L "$BACKUP" ] || fail 'Il backup audio V3 non è disponibile.'
[ -d "$VOLUME" ] && [ ! -L "$VOLUME" ] || fail 'Il backup volume V3 completo non è disponibile.'
ordinary_file "$STATE" || fail 'Manca lo stato ordinario del backup audio.'
/usr/bin/plutil -lint "$STATE" > /dev/null || fail 'Lo stato del backup non è un plist valido.'
STATE_HASH=$(hash "$STATE")
[ "$(readkey "$STATE" Format)" = 2 ] || fail 'Il formato del backup audio non è 2.'
[ "$(readkey "$STATE" Phase)" = installed ] || fail 'La prova audio non è nello stato installato.'
[ "$(readkey "$STATE" VolumePhase)" = ready ] || fail 'La sostituzione del driver volume non è completa.'
[ "$(readkey "$STATE" VolumeTarget)" = modified ] || fail 'Lo stato non identifica la variante volume V3.'
MANIFEST_HASH=$(readkey "$STATE" VolumeManifestHash) || fail 'Manca il riferimento al manifest volume.'
case "$MANIFEST_HASH" in ''|*[!0-9a-f]*) fail 'Il riferimento al manifest volume non è valido.';; esac
[ "${#MANIFEST_HASH}" -eq 64 ] || fail 'Il riferimento al manifest volume non ha 64 caratteri.'
MANIFEST="$VOLUME/SHA256SUMS"
ordinary_file "$MANIFEST" || fail 'Manca il manifest ordinario della variante volume.'
[ "$(hash "$MANIFEST")" = "$MANIFEST_HASH" ] || fail 'Il manifest volume non coincide con lo stato salvato.'

# Require exactly the canonical three ordered, unique entries, with lowercase
# 64-character SHA256 values and a final newline. Never evaluate manifest text.
index=0
: > "$TEMP/manifest-checked.txt"
while IFS= read -r line || [ -n "$line" ]; do
    index=$((index + 1))
    case "$index" in
        1) wanted=Contents/Info.plist;;
        2) wanted=Contents/MacOS/VoodooHDA;;
        3) wanted=Contents/_CodeSignature/CodeResources;;
        *) fail 'Il manifest contiene file aggiuntivi.';;
    esac
    expected=${line%% *}
    case "$expected" in ''|*[!0-9a-f]*) fail 'Un hash del manifest non è valido.';; esac
    [ "${#expected}" -eq 64 ] || fail 'Un hash del manifest non ha 64 caratteri.'
    [ "$line" = "$expected  $wanted" ] || fail 'Il manifest non contiene i tre percorsi previsti nel formato corretto.'
    printf '%s  %s\n' "$expected" "$wanted" >> "$TEMP/manifest-checked.txt"
    if [ "$index" -eq 2 ]; then VERIFIED_MACHO=$expected; fi
done < "$MANIFEST"
[ "$index" -eq 3 ] || fail 'Il manifest non contiene tutti e tre i file.'
/usr/bin/cmp -s "$MANIFEST" "$TEMP/manifest-checked.txt" || fail 'Il manifest non è nel formato canonico.'

ORIGINAL="$VOLUME/original/VoodooHDA.kext"
MODIFIED="$VOLUME/modified/VoodooHDA.kext"
validate_bundle_shape "$ORIGINAL"
validate_bundle_shape "$MODIFIED"
original_matches "$ORIGINAL" || fail 'La copia originale non coincide con il payload VoodooHDA 3.6.8 verificato.'
manifest_matches "$MODIFIED" || fail 'La variante V3 conservata non coincide con il manifest.'
manifest_matches "$DRIVER" || fail 'Il driver installato non coincide con la variante V3 conservata.'

[ "$(readkey "$ORIGINAL/Contents/Info.plist" "$KEY")" = false ] || fail 'Il valore volume originale non è false.'
/bin/cp "$ORIGINAL/Contents/Info.plist" "$TEMP/expected.plist" || fail 'Impossibile copiare il plist nella cartella temporanea.'
/usr/bin/plutil -replace "$KEY" -bool true "$TEMP/expected.plist" || fail 'Impossibile derivare il plist volume previsto.'
/usr/bin/plutil -convert xml1 "$TEMP/expected.plist" || fail 'Impossibile normalizzare il plist previsto.'
/usr/bin/plutil -convert xml1 -o "$TEMP/actual.plist" "$MODIFIED/Contents/Info.plist" || fail 'Il plist della variante non è valido.'
/usr/bin/cmp -s "$TEMP/expected.plist" "$TEMP/actual.plist" || fail 'Il plist della variante contiene altre modifiche oltre alla correzione volume.'
verify_signature "$ORIGINAL"
verify_signature "$MODIFIED"
verify_signature "$DRIVER"

# Catch changes made while validation was in progress. No writes occur outside
# our private /tmp directory, and no configuration or NVRAM data is read.
[ "$(hash "$STATE")" = "$STATE_HASH" ] || fail 'Lo stato è cambiato durante la verifica.'
[ "$(hash "$MANIFEST")" = "$MANIFEST_HASH" ] || fail 'Il manifest è cambiato durante la verifica.'
original_matches "$ORIGINAL" || fail 'La copia originale è cambiata durante la verifica.'
manifest_matches "$MODIFIED" || fail 'La variante conservata è cambiata durante la verifica.'
manifest_matches "$DRIVER" || fail 'Il driver installato è cambiato durante la verifica.'
printf '%s\n' "$VERIFIED_MACHO"
