#!/bin/bash
# Native macOS / Bash 3.2. Add one EFI driver entry, then reboot manually.
# The original personalized config remains in a private, byte-exact backup.
set -euo pipefail
export LC_ALL=C
umask 077

PAYLOAD_MANIFEST_SHA='BRIGHTNESS_KEYS_MANIFEST_SHA_PENDING'
IDENTIFIER='as.acidanthera.BrightnessKeys'
VERSION='1.0.3'
OWNER='s540-brightness-keys-v1'
ARGS='NVRAM.Add.7C436110-AB2A-4BBB-A880-FE41995C9F82.boot-args'
TEMP=''
CONFIG_TEMP=''
DRAFT=''
RUNTIME_BRIGHTNESS_LOADED=0

fail() { printf 'Brightness-key test: %s\n' "$*" >&2; exit 1; }
hash() { /usr/bin/shasum -a 256 "$1" | /usr/bin/awk '{print $1}'; }
readkey() { /usr/bin/plutil -extract "$2" raw -o - "$1" 2>/dev/null; }
ordinary_file() { [ -f "$1" ] && [ ! -L "$1" ]; }
exists() { [ -e "$1" ] || [ -L "$1" ]; }
safe_path() {
    local path=$1
    case "$path" in /*) ;; *) fail 'Use an absolute boot-disk path.';; esac
    case "$path" in *$'\n'*|*$'\r'*|*/../*|*/./*|*/..|*/.) fail 'The path contains unsupported components.';; esac
    while [ "$path" != / ]; do
        [ ! -L "$path" ] || fail "Symbolic link in path: $path"
        path=${path%/*}; [ -n "$path" ] || path=/
    done
}
cleanup() {
    # Only names allocated by this invocation are eligible for cleanup.
    if [ -n "$CONFIG_TEMP" ] && ordinary_file "$CONFIG_TEMP"; then /bin/rm -f "$CONFIG_TEMP"; fi
    if [ -n "$DRAFT" ] && [ -d "$DRAFT" ] && [ ! -L "$DRAFT" ]; then
        local name
        for name in before.plist tested.plist state.plist manifest.plist; do
            if ordinary_file "$DRAFT/$name"; then /bin/rm -f "$DRAFT/$name"; fi
        done
        /bin/rmdir "$DRAFT" 2>/dev/null || true
    fi
    if [ -n "$TEMP" ] && [ -d "$TEMP" ] && [ ! -L "$TEMP" ]; then /bin/rm -rf "$TEMP"; fi
}
trap cleanup EXIT
trap 'printf "The operation did not finish. Keep backup-function-keys and read the previous error before restarting.\n" >&2' ERR

typed() {
    /usr/bin/plutil -extract "$2" xml1 -o - "$1" > "$TEMP/type.plist" 2>/dev/null || return 1
    /usr/bin/awk -v wanted="$3" '
        /<plist[^>]*>/ { sub(/^.*<plist[^>]*>/, ""); inside=1 }
        inside { sub(/^[[:space:]]+/, ""); if(length($0)) { seen=1; exit !($0 ~ ("^<" wanted "([ />])")) } }
        END { if(!seen) exit 1 }
    ' "$TEMP/type.plist"
}
empty_plist() {
    printf '%s\n' '<?xml version="1.0" encoding="UTF-8"?>' '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">' '<plist version="1.0"><dict/></plist>' > "$1"
}
string_value() {
    typed "$1" "$2" string || fail "Property $2 must be a string."
    readkey "$1" "$2"
}
valid_hash() {
    case "$1" in ''|*[!0-9a-f]*) return 1;; esac
    [ "${#1}" -eq 64 ]
}
contains_flag() { case " $1 " in *" $2 "*) return 0;; *) return 1;; esac; }
backlight_args() {
    local args=$1
    case "$args" in *$'\n'*|*$'\r'*|*$'\t'*) fail 'boot-args contain unsupported separators.';; esac
    contains_flag "$args" -igfxblr || fail 'The working -igfxblr backlight correction is required.'
    if contains_flag "$args" -igfxvesa || contains_flag "$args" -x; then
        fail 'Run the test with Intel acceleration enabled, outside safe boot.'
    fi
}

runtime_guard() {
    local args
    [ "$(/usr/bin/uname -s)" = Darwin ] && [ "$(/usr/bin/uname -m)" = x86_64 ] || fail 'Intel macOS is required.'
    case "$(/usr/bin/uname -r)" in 25.*) ;; *) fail 'This package requires macOS Tahoe (Darwin 25).';; esac
    if [ "$MODE" = test ]; then
        [ "$(/usr/bin/uname -r)" = 25.6.0 ] || fail 'Collect new diagnostics before testing on a kernel other than Darwin 25.6.0.'
        [ -d /System/Volumes/Data ] && [ -d /Users ] || fail 'Run the test from the Tahoe desktop, not Recovery.'
        [ "$(/usr/bin/id -u)" -ne 0 ] || fail 'Open the test from your own account.'
        args=$(/usr/sbin/sysctl -n kern.bootargs) || fail 'Cannot read the active boot arguments.'
        backlight_args "$args"
        /usr/sbin/ioreg -r -c AppleBacklightDisplay -l -w 0 > "$TEMP/panel.txt" || fail 'Cannot inspect the active panel.'
        /usr/bin/grep -Fq '<class AppleBacklightDisplay,' "$TEMP/panel.txt" || fail 'The working AppleBacklightDisplay panel is not active.'
        /usr/bin/grep -Eq '"brightness"[[:space:]]*=' "$TEMP/panel.txt" || fail 'The active panel does not expose brightness control.'
        /usr/bin/kmutil showloaded > "$TEMP/loaded.txt" 2> "$TEMP/loaded-errors.txt" || fail 'Cannot inspect loaded drivers.'
        /usr/bin/grep -Eq 'as\.vit9696\.Lilu[[:space:]]+\(1\.7\.2\)' "$TEMP/loaded.txt" || fail 'This pilot requires loaded Lilu 1.7.2. Collect updated diagnostics if the active version differs.'
        if /usr/bin/grep -Fq "$IDENTIFIER" "$TEMP/loaded.txt"; then
            /usr/bin/grep -Eq 'as\.acidanthera\.BrightnessKeys[[:space:]]+\(1\.0\.3\)' "$TEMP/loaded.txt" || fail 'A different BrightnessKeys version is already loaded.'
            RUNTIME_BRIGHTNESS_LOADED=1
        fi
    fi
}

verify_thin_header() {
    /usr/bin/od -An -j "$2" -N16 -v -tx1 "$1" | /usr/bin/awk '
        { for (i=1; i<=NF; i++) b[++n]=$i }
        END { exit !(n==16 && b[1]=="cf" && b[2]=="fa" && b[3]=="ed" && b[4]=="fe" &&
            b[5]=="07" && b[6]=="00" && b[7]=="00" && b[8]=="01" &&
            b[13]=="0b" && b[14]=="00" && b[15]=="00" && b[16]=="00") }'
}
verify_macho() {
    local binary=$1 magic offset
    magic=$(/usr/bin/od -An -N4 -v -tx1 "$binary" | /usr/bin/awk '{for(i=1;i<=NF;i++)printf "%s",$i}')
    if [ "$magic" = cffaedfe ]; then
        verify_thin_header "$binary" 0 || fail 'The driver is not a complete x86_64 MH_KEXT_BUNDLE.'
        return 0
    fi
    case "$magic" in cafebabe|bebafeca|cafebabf|bfbafeca) ;; *) fail 'The driver has an unsupported Mach-O header.';; esac
    # Read a universal architecture table without Xcode command shims.
    offset=$(/usr/bin/od -An -N264 -v -tx1 "$binary" | /usr/bin/awk -v magic="$magic" '
        function dec(s, i,v,c) { v=0; for(i=1;i<=length(s);i++) { c=index("0123456789abcdef",substr(s,i,1))-1; if(c<0)exit 1; v=v*16+c } return v }
        function word(p, s,j) { s=""; if(le)for(j=3;j>=0;j--)s=s b[p+j]; else for(j=0;j<4;j++)s=s b[p+j]; return dec(s) }
        { for(i=1;i<=NF;i++) b[++total]=$i }
        END {
            le=(magic=="bebafeca" || magic=="bfbafeca"); wide=(magic=="cafebabf" || magic=="bfbafeca"); stride=wide?32:20;
            count=word(5); if(count<1 || count>8 || total<8+count*stride)exit 1;
            for(a=0;a<count;a++) { p=9+a*stride; if(word(p)==16777223) {
                if(wide) { hi=word(p+(le?12:8)); lo=word(p+(le?8:12)); if(hi!=0)exit 1; off=lo }
                else off=word(p+8);
                if(off<8+count*stride || off>2147483647)exit 1;
                printf "%.0f\n",off; found++; break
            } }
            if(!found)exit 1
        }') || fail 'The universal driver does not contain a valid x86_64 slice.'
    verify_thin_header "$binary" "$offset" || fail 'The universal driver x86_64 slice is not an MH_KEXT_BUNDLE.'
}

validate_payload() {
    local i=0 path expected line
    valid_hash "$PAYLOAD_MANIFEST_SHA" || fail 'Download the built package: this source copy has no locked driver manifest.'
    safe_path "$MANIFEST"; safe_path "$VALIDATOR"; safe_path "$PAYLOAD"
    ordinary_file "$MANIFEST" || fail 'The package manifest is missing.'
    [ "$(hash "$MANIFEST")" = "$PAYLOAD_MANIFEST_SHA" ] || fail 'The package manifest was modified.'
    /usr/bin/plutil -lint "$MANIFEST" > /dev/null || fail 'The package manifest is invalid.'
    typed "$MANIFEST" schema integer && [ "$(readkey "$MANIFEST" schema)" = 1 ] || fail 'Unsupported manifest schema.'
    [ "$(string_value "$MANIFEST" identifier)" = "$IDENTIFIER" ] || fail 'Unexpected manifest identifier.'
    [ "$(string_value "$MANIFEST" version)" = "$VERSION" ] || fail 'Unexpected manifest version.'
    typed "$MANIFEST" files array || fail 'The manifest file list is missing.'
    VALIDATOR_SHA=$(string_value "$MANIFEST" validator_sha256)
    OPENCORE_SHA=$(string_value "$MANIFEST" opencore_sha256)
    valid_hash "$VALIDATOR_SHA" && valid_hash "$OPENCORE_SHA" || fail 'Invalid validator or OpenCore hash.'
    ordinary_file "$VALIDATOR" && [ -x "$VALIDATOR" ] || fail 'The native OpenCore validator is missing or not executable.'
    [ "$(hash "$VALIDATOR")" = "$VALIDATOR_SHA" ] || fail 'The native OpenCore validator was modified.'
    : > "$TEMP/manifest-files.txt"
    while /usr/bin/plutil -extract "files.$i" xml1 -o - "$MANIFEST" > "$TEMP/manifest-entry.plist" 2>/dev/null; do
        [ "$i" -lt 32 ] || fail 'The manifest contains too many files.'
        typed "$MANIFEST" "files.$i" dict || fail 'Invalid manifest file entry.'
        path=$(string_value "$MANIFEST" "files.$i.path")
        expected=$(string_value "$MANIFEST" "files.$i.sha256")
        valid_hash "$expected" || fail 'Invalid driver-file hash.'
        case "$path" in BrightnessKeys.kext/Contents/*) ;; *) fail 'The manifest path is outside BrightnessKeys.kext/Contents.';; esac
        case "$path" in *[!A-Za-z0-9._/-]*|*//*|*/./*|*/../*|*/.|*/..|*/) fail 'Invalid manifest path.';; esac
        /usr/bin/grep -Fxq "$path" "$TEMP/manifest-files.txt" && fail 'Duplicate manifest path.'
        printf '%s\n' "$path" >> "$TEMP/manifest-files.txt"
        i=$((i+1))
    done
    [ "$i" -ge 2 ] || fail 'The manifest is incomplete.'
    /usr/bin/sort "$TEMP/manifest-files.txt" > "$TEMP/manifest-files-sorted.txt"
    bundle_matches "$PAYLOAD"
    [ "$(string_value "$PAYLOAD/Contents/Info.plist" CFBundleIdentifier)" = "$IDENTIFIER" ] || fail 'Unexpected driver identifier.'
    [ "$(string_value "$PAYLOAD/Contents/Info.plist" CFBundleVersion)" = "$VERSION" ] || fail 'Unexpected driver version.'
    [ "$(string_value "$PAYLOAD/Contents/Info.plist" CFBundleExecutable)" = BrightnessKeys ] || fail 'Unexpected driver executable name.'
    [ "$(string_value "$PAYLOAD/Contents/Info.plist" CFBundlePackageType)" = KEXT ] || fail 'The payload is not a kernel extension.'
    verify_macho "$PAYLOAD/Contents/MacOS/BrightnessKeys"
}
metadata_header() {
    /usr/bin/od -An -N8 -v -tx1 "$1" | /usr/bin/awk '{for(i=1;i<=NF;i++)printf "%s",$i}'
}
appledouble_file() {
    local path=$1 size
    ordinary_file "$path" || return 1
    size=$(/usr/bin/stat -f '%z' "$path") || return 1
    case "$size" in ''|*[!0-9]*) return 1;; esac
    [ "$size" -ge 26 ] || return 1
    /usr/bin/od -An -N794 -v -tx1 "$path" | /usr/bin/awk -v size="$size" '
        function dec(s, i,v,c) { v=0; for(i=1;i<=length(s);i++) { c=index("0123456789abcdef",substr(s,i,1))-1; if(c<0)return -1; v=v*16+c } return v }
        function word(p, n,s,j) { s=""; for(j=0;j<n;j++)s=s b[p+j]; return dec(s) }
        { for(i=1;i<=NF;i++)b[++total]=$i }
        END {
            if(total<26 || word(1,4)!=333319 || word(5,4)!=131072)exit 1;
            count=word(25,2); limit=26+12*count;
            if(count<1 || count>64 || total<limit || size<limit)exit 1;
            for(i=0;i<count;i++) {
                p=27+12*i; id=word(p,4); offset=word(p+4,4); length=word(p+8,4);
                if(id<1 || ids[id]++ || offset<limit || offset>size || length>size-offset)exit 1;
            }
            exit 0
        }'
}
finder_store_file() {
    ordinary_file "$1" || return 1
    [ "$(metadata_header "$1")" = 0000000142756431 ] || return 1
    [ "$(/usr/bin/stat -f '%z' "$1")" -ge 32 ]
}
backup_metadata() {
    local path=$1 name target
    name=${path##*/}
    if [ "$name" = .DS_Store ]; then finder_store_file "$path"; return; fi
    case "$name" in ._*) target=${name#._};; *) return 1;; esac
    case "$target" in before.plist|tested.plist|state.plist|state-next.plist|manifest.plist)
        ordinary_file "$BACKUP/$target" || return 1;;
        removed-BrightnessKeys.kext)
        [ -d "$BACKUP/$target" ] && [ ! -L "$BACKUP/$target" ] || return 1;;
        *) return 1;;
    esac
    appledouble_file "$path"
}
bundle_metadata() {
    local bundle=$1 relative=$2 path target name directory owned
    path="$bundle/$relative"; name=${relative##*/}; directory=${relative%/*}
    [ "$directory" != "$relative" ] || directory=''
    if [ "$name" = .DS_Store ]; then finder_store_file "$path"; return; fi
    case "$name" in ._*) target=${name#._};; *) return 1;; esac
    if [ -n "$directory" ]; then target="$directory/$target"; fi
    owned="BrightnessKeys.kext/$target"
    if ! /usr/bin/grep -Fxq "$owned" "$TEMP/manifest-files.txt" && ! /usr/bin/grep -Fq "$owned/" "$TEMP/manifest-files.txt"; then return 1; fi
    if [ ! -e "$bundle/$target" ] || [ -L "$bundle/$target" ]; then return 1; fi
    appledouble_file "$path"
}

bundle_matches() {
    local bundle=$1 i=0 path expected
    safe_path "$bundle"
    [ -d "$bundle" ] && [ ! -L "$bundle" ] || fail "Missing driver bundle: $bundle"
    [ -z "$(/usr/bin/find "$bundle" ! -type f ! -type d -print)" ] || fail 'The driver bundle contains links or special files.'
    : > "$TEMP/bundle-files-raw.txt"
    while IFS= read -r path; do
        path=${path#./}
        safe_path "$bundle/$path"
        if bundle_metadata "$bundle" "$path"; then continue; fi
        printf 'BrightnessKeys.kext/%s\n' "$path" >> "$TEMP/bundle-files-raw.txt"
    done < <(cd "$bundle" && /usr/bin/find . -type f -print)
    /usr/bin/sort "$TEMP/bundle-files-raw.txt" > "$TEMP/bundle-files.txt"
    /usr/bin/cmp -s "$TEMP/bundle-files.txt" "$TEMP/manifest-files-sorted.txt" || fail 'The driver bundle file list differs from the locked manifest.'
    while /usr/bin/plutil -extract "files.$i" xml1 -o - "$MANIFEST" > /dev/null 2>&1; do
        path=$(readkey "$MANIFEST" "files.$i.path"); path=${path#BrightnessKeys.kext/}
        expected=$(readkey "$MANIFEST" "files.$i.sha256")
        ordinary_file "$bundle/$path" || fail 'A manifest file is missing or is a link.'
        [ "$(hash "$bundle/$path")" = "$expected" ] || fail 'A driver file differs from the locked manifest.'
        i=$((i+1))
    done
}
validate_oc() {
    local config=$1
    /usr/bin/plutil -lint "$config" > /dev/null || fail 'config.plist is invalid.'
    safe_path "$VALIDATOR"
    ordinary_file "$VALIDATOR" && [ "$(hash "$VALIDATOR")" = "$VALIDATOR_SHA" ] || fail 'The native validator changed before execution.'
    if ! "$VALIDATOR" "$config" > "$TEMP/ocvalidate.txt" 2>&1; then
        /bin/cat "$TEMP/ocvalidate.txt" >&2
        fail 'OpenCore validation failed. If macOS blocks this bundled validator, review the blocked-app message in Privacy & Security; no EFI change was made by this validation.'
    fi
}
kernel_allows_runtime() {
    local value=$1 limit=$2 a b c extra
    [ -n "$value" ] || return 0
    case "$value" in *[!0-9.]*|*.*.*.*) return 1;; esac
    IFS=. read -r a b c extra <<< "$value"
    [ -n "$a" ] && [ -n "$b" ] && [ -n "$c" ] && [ -z "${extra:-}" ] || return 1
    if [ "$limit" = min ]; then
        [ "$((10#$a))" -lt 25 ] || { [ "$((10#$a))" -eq 25 ] && { [ "$((10#$b))" -lt 6 ] || { [ "$((10#$b))" -eq 6 ] && [ "$((10#$c))" -eq 0 ]; }; }; }
    else
        [ "$((10#$a))" -gt 25 ] || { [ "$((10#$a))" -eq 25 ] && [ "$((10#$b))" -ge 6 ]; }
    fi
}
validate_config_base() {
    local file=$1 i=0 lilu=0 path index='' info binary args
    validate_oc "$file"
    [ "$(string_value "$file" PlatformInfo.Generic.SystemProductName)" = MacBookPro16,2 ] || fail 'The config model differs from the analyzed MacBookPro16,2 baseline.'
    args=$(string_value "$file" "$ARGS"); backlight_args "$args"
    typed "$file" Kernel.Add array || fail 'Kernel/Add must be an array.'
    while /usr/bin/plutil -extract "Kernel.Add.$i" xml1 -o - "$file" > /dev/null 2>&1; do
        [ "$i" -lt 128 ] || fail 'Kernel/Add contains too many entries.'
        typed "$file" "Kernel.Add.$i" dict || fail 'Kernel/Add contains a malformed entry.'
        path=$(string_value "$file" "Kernel.Add.$i.BundlePath")
        case "$path" in *BrightnessKeys*) fail 'A BrightnessKeys entry already exists; do not combine installations.';; esac
        if [ "$path" = Lilu.kext ]; then lilu=$((lilu+1)); index=$i; fi
        i=$((i+1))
    done
    [ "$lilu" -eq 1 ] || fail 'Lilu must appear exactly once in Kernel/Add.'
    typed "$file" "Kernel.Add.$index.Enabled" true || fail 'The working Lilu entry must remain enabled.'
    case "$(string_value "$file" "Kernel.Add.$index.Arch")" in Any|x86_64) ;; *) fail 'Lilu is not enabled for Intel macOS.';; esac
    [ "$(string_value "$file" "Kernel.Add.$index.ExecutablePath")" = Contents/MacOS/Lilu ] || fail 'Unexpected Lilu executable path.'
    [ "$(string_value "$file" "Kernel.Add.$index.PlistPath")" = Contents/Info.plist ] || fail 'Unexpected Lilu plist path.'
    kernel_allows_runtime "$(string_value "$file" "Kernel.Add.$index.MinKernel")" min || fail 'Lilu is excluded from Darwin 25.6.0.'
    kernel_allows_runtime "$(string_value "$file" "Kernel.Add.$index.MaxKernel")" max || fail 'Lilu is excluded from Darwin 25.6.0.'
    info="$OC/Kexts/Lilu.kext/Contents/Info.plist"; binary="$OC/Kexts/Lilu.kext/Contents/MacOS/Lilu"
    safe_path "$info"; safe_path "$binary"
    ordinary_file "$info" && ordinary_file "$binary" || fail 'The working Lilu bundle is incomplete.'
    [ "$(string_value "$info" CFBundleIdentifier)" = as.vit9696.Lilu ] || fail 'Unexpected Lilu bundle identifier.'
    [ "$(string_value "$info" CFBundleVersion)" = 1.7.2 ] || fail 'This pilot requires Lilu 1.7.2 in the EFI. Collect updated diagnostics if the bundle version differs.'
    ADD_COUNT=$i
}
derive_test_config() {
    local before=$1 destination=$2 entry="$TEMP/brightness-entry.plist"
    validate_config_base "$before"
    empty_plist "$entry"
    /usr/bin/plutil -insert Arch -string Any "$entry"
    /usr/bin/plutil -insert BundlePath -string BrightnessKeys.kext "$entry"
    /usr/bin/plutil -insert Comment -string 'S540 brightness-key test' "$entry"
    /usr/bin/plutil -insert Enabled -bool true "$entry"
    /usr/bin/plutil -insert ExecutablePath -string Contents/MacOS/BrightnessKeys "$entry"
    /usr/bin/plutil -insert MaxKernel -string 25.99.99 "$entry"
    /usr/bin/plutil -insert MinKernel -string 25.0.0 "$entry"
    /usr/bin/plutil -insert PlistPath -string Contents/Info.plist "$entry"
    /bin/cp -Xp "$before" "$destination"
    /usr/bin/plutil -insert "Kernel.Add.$ADD_COUNT" -xml "$(/bin/cat "$entry")" "$destination"
    validate_oc "$destination"
}

valid_phase() { case "$1" in prepared|staged|copied|installed|restoring|restored) return 0;; *) return 1;; esac; }
make_state() {
    local before=$1 tested=$2 destination=$3 phase=$4
    valid_phase "$phase" || fail 'Invalid journal phase.'
    empty_plist "$destination"
    /usr/bin/plutil -insert Format -integer 1 "$destination"
    /usr/bin/plutil -insert Owner -string "$OWNER" "$destination"
    /usr/bin/plutil -insert BeforeSHA256 -string "$(hash "$before")" "$destination"
    /usr/bin/plutil -insert TestedSHA256 -string "$(hash "$tested")" "$destination"
    /usr/bin/plutil -insert PayloadManifestSHA256 -string "$PAYLOAD_MANIFEST_SHA" "$destination"
    /usr/bin/plutil -insert ValidatorSHA256 -string "$VALIDATOR_SHA" "$destination"
    /usr/bin/plutil -insert OpenCoreSHA256 -string "$OPENCORE_SHA" "$destination"
    /usr/bin/plutil -insert Phase -string "$phase" "$destination"
}
canonical_equal() {
    /usr/bin/plutil -convert xml1 -o "$TEMP/canonical-a.plist" "$1"
    /usr/bin/plutil -convert xml1 -o "$TEMP/canonical-b.plist" "$2"
    /usr/bin/cmp -s "$TEMP/canonical-a.plist" "$TEMP/canonical-b.plist"
}
check_next_state() {
    local next="$BACKUP/state-next.plist" phase
    exists "$next" || return 0
    ordinary_file "$next" || fail 'The journal draft is not a regular file.'
    phase=$(string_value "$next" Phase); valid_phase "$phase" || fail 'Invalid draft journal phase.'
    /bin/cp -X "$next" "$TEMP/next-state-check.plist"
    /usr/bin/plutil -replace Phase -string "$PHASE" "$TEMP/next-state-check.plist"
    canonical_equal "$STATE" "$TEMP/next-state-check.plist" || fail 'The journal draft changes fields beyond the phase.'
}
load_backup() {
    local name path phase
    safe_path "$BACKUP"
    [ -d "$BACKUP" ] && [ ! -L "$BACKUP" ] || fail 'The backup path is not a regular directory.'
    [ -z "$(/usr/bin/find "$BACKUP" ! -type f ! -type d -print)" ] || fail 'The backup contains links or special files.'
    while IFS= read -r path; do
        name=${path##*/}
        case "$name" in before.plist|tested.plist|state.plist|state-next.plist|manifest.plist) ordinary_file "$path" || fail 'An expected backup file is not regular.';;
            removed-BrightnessKeys.kext) [ -d "$path" ] && [ ! -L "$path" ] || fail 'The removed bundle is not a regular directory.';;
            *) backup_metadata "$path" || fail "The backup contains an unexpected top-level item: $name";; esac
    done < <(/usr/bin/find "$BACKUP" -mindepth 1 -maxdepth 1 -print)
    for name in before.plist tested.plist state.plist manifest.plist; do
        ordinary_file "$BACKUP/$name" || fail 'The private backup is incomplete.'
    done
    STATE="$BACKUP/state.plist"
    typed "$STATE" Format integer && [ "$(readkey "$STATE" Format)" = 1 ] || fail 'Unsupported backup format.'
    [ "$(string_value "$STATE" Owner)" = "$OWNER" ] || fail 'The backup belongs to a different operation.'
    [ "$(hash "$BACKUP/manifest.plist")" = "$PAYLOAD_MANIFEST_SHA" ] || fail 'The backup manifest was modified or belongs to a different package.'
    BEFORE=$(string_value "$STATE" BeforeSHA256); TESTED=$(string_value "$STATE" TestedSHA256)
    valid_hash "$BEFORE" && valid_hash "$TESTED" || fail 'Invalid config hashes in the journal.'
    [ "$(hash "$BACKUP/before.plist")" = "$BEFORE" ] || fail 'The original config backup was modified.'
    [ "$(hash "$BACKUP/tested.plist")" = "$TESTED" ] || fail 'The tested config backup was modified.'
    PHASE=$(string_value "$STATE" Phase); valid_phase "$PHASE" || fail 'Invalid journal phase.'
    make_state "$BACKUP/before.plist" "$BACKUP/tested.plist" "$TEMP/expected-state.plist" "$PHASE"
    canonical_equal "$STATE" "$TEMP/expected-state.plist" || fail 'The journal does not match this package and its config snapshots.'
    derive_test_config "$BACKUP/before.plist" "$TEMP/expected-config.plist"
    canonical_equal "$BACKUP/tested.plist" "$TEMP/expected-config.plist" || fail 'The tested snapshot changes more than the one BrightnessKeys entry.'
    check_next_state
    STATE_HASH=$(hash "$STATE")
    CURRENT=$(hash "$CONFIG")
    case "$CURRENT" in "$BEFORE"|"$TESTED") ;; *) fail 'The config changed after this test. It will not be overwritten.';; esac
}
write_phase() {
    local phase=$1 next="$BACKUP/state-next.plist"
    valid_phase "$phase" || fail 'Invalid new journal phase.'
    safe_path "$BACKUP"; safe_path "$CONFIG"
    ordinary_file "$STATE" && [ "$(hash "$STATE")" = "$STATE_HASH" ] || fail 'The journal changed during the operation.'
    ordinary_file "$BACKUP/before.plist" && ordinary_file "$BACKUP/tested.plist" && ordinary_file "$BACKUP/manifest.plist" || fail 'A private backup file was replaced by a link or special file.'
    [ "$(hash "$BACKUP/before.plist")" = "$BEFORE" ] && [ "$(hash "$BACKUP/tested.plist")" = "$TESTED" ] || fail 'A config snapshot changed during the operation.'
    [ "$(hash "$BACKUP/manifest.plist")" = "$PAYLOAD_MANIFEST_SHA" ] || fail 'The backup manifest changed during the operation.'
    ordinary_file "$CONFIG" && [ "$(hash "$CONFIG")" = "$CURRENT" ] || fail 'The config changed during the operation; the journal will not be advanced.'
    safe_path "$OC/OpenCore.efi"
    ordinary_file "$OC/OpenCore.efi" && [ "$(hash "$OC/OpenCore.efi")" = "$OPENCORE_SHA" ] || fail 'OpenCore changed during the operation.'
    check_next_state
    if exists "$next"; then /bin/rm -f "$next"; fi
    make_state "$BACKUP/before.plist" "$BACKUP/tested.plist" "$next" "$phase"
    /usr/bin/plutil -lint "$next" > /dev/null
    /bin/mv -f "$next" "$STATE"
    PHASE=$phase
    STATE_HASH=$(hash "$STATE")
}
create_backup() {
    local original_hash
    exists "$BACKUP" && fail 'A backup already exists. Use the restore command or inspect the existing journal.'
    exists "$ACTIVE" && fail 'A BrightnessKeys bundle already exists without this test backup.'
    exists "$STAGE" && fail 'A staging bundle already exists without this test backup.'
    original_hash=$(hash "$CONFIG")
    /bin/cp -Xp "$CONFIG" "$TEMP/before.plist"
    [ "$(hash "$TEMP/before.plist")" = "$original_hash" ] && [ "$(hash "$CONFIG")" = "$original_hash" ] || fail 'The config changed during reading.'
    derive_test_config "$TEMP/before.plist" "$TEMP/tested.plist"
    # Both original and candidate have passed the matching native validator.
    [ "$(hash "$CONFIG")" = "$original_hash" ] || fail 'The config changed during validation.'
    safe_path "$OC"
    DRAFT=$(/usr/bin/mktemp -d "$OC/.backup-function-keys.XXXXXX")
    /bin/cp -Xp "$TEMP/before.plist" "$DRAFT/before.plist"
    /bin/cp -Xp "$TEMP/tested.plist" "$DRAFT/tested.plist"
    /bin/cp -X "$MANIFEST" "$DRAFT/manifest.plist"
    make_state "$DRAFT/before.plist" "$DRAFT/tested.plist" "$DRAFT/state.plist" prepared
    /bin/chmod 700 "$DRAFT"
    /bin/chmod 600 "$DRAFT/before.plist" "$DRAFT/tested.plist" "$DRAFT/state.plist" "$DRAFT/manifest.plist"
    [ "$(hash "$CONFIG")" = "$original_hash" ] || fail 'The config changed during backup preparation.'
    exists "$BACKUP" && fail 'The backup path appeared during preparation.'
    /bin/mv "$DRAFT" "$BACKUP"
    DRAFT=''
    load_backup
}
atomic_config_replace() {
    local wanted=$1 expected=$2 wanted_hash=$3
    ordinary_file "$wanted" && [ "$(hash "$wanted")" = "$wanted_hash" ] || fail 'The requested config snapshot changed during the operation.'
    safe_path "$CONFIG"
    ordinary_file "$CONFIG" && [ "$(hash "$CONFIG")" = "$expected" ] || fail 'The config changed before replacement.'
    CONFIG_TEMP=$(/usr/bin/mktemp "$OC/.brightness-config.XXXXXX")
    /bin/cp -Xp "$wanted" "$CONFIG_TEMP"
    [ "$(hash "$CONFIG_TEMP")" = "$wanted_hash" ] || fail 'The staged config copy is incomplete.'
    validate_oc "$CONFIG_TEMP"
    ordinary_file "$CONFIG" && [ "$(hash "$CONFIG")" = "$expected" ] || fail 'The config changed during replacement preparation.'
    /bin/mv -f "$CONFIG_TEMP" "$CONFIG"
    CONFIG_TEMP=''
    [ "$(hash "$CONFIG")" = "$wanted_hash" ] || fail 'Config verification failed. Keep the backup and do not restart.'
    CURRENT=$wanted_hash
}
apply_test() {
    if [ "$RUNTIME_BRIGHTNESS_LOADED" -eq 1 ] && ! exists "$BACKUP"; then fail 'BrightnessKeys is already loaded without this test backup; do not combine installations.'; fi
    if exists "$BACKUP"; then load_backup; else create_backup; fi
    if [ "$RUNTIME_BRIGHTNESS_LOADED" -eq 1 ] && [ "$CURRENT" != "$TESTED" ]; then fail 'BrightnessKeys is already loaded outside this installed test configuration.'; fi
    [ "$PHASE" != restored ] && [ "$PHASE" != restoring ] || fail 'This journal belongs to a completed or interrupted restore. Finish restoring before preparing another test.'
    exists "$REMOVED" && fail 'A previously removed bundle exists; do not restart the test from this backup.'
    if [ "$CURRENT" = "$TESTED" ]; then
        exists "$STAGE" && fail 'Unexpected staging bundle beside the installed driver.'
        bundle_matches "$ACTIVE"
        write_phase installed
    else
        if exists "$ACTIVE"; then
            exists "$STAGE" && fail 'Both an active and a staging bundle exist.'
            bundle_matches "$ACTIVE"
        else
            if exists "$STAGE"; then
                bundle_matches "$STAGE"
            else
                safe_path "$STAGE"
                /usr/bin/ditto --norsrc --noextattr --noacl --noqtn "$PAYLOAD" "$STAGE"
                bundle_matches "$STAGE"
            fi
            write_phase staged
            [ "$(hash "$CONFIG")" = "$BEFORE" ] || fail 'The config changed before driver placement.'
            exists "$ACTIVE" && fail 'The active driver path appeared during staging.'
            bundle_matches "$STAGE"
            /bin/mv "$STAGE" "$ACTIVE"
        fi
        write_phase copied
        bundle_matches "$ACTIVE"
        atomic_config_replace "$BACKUP/tested.plist" "$BEFORE" "$TESTED"
        write_phase installed
    fi
    printf 'BrightnessKeys %s is staged for the next boot. Restart manually, then test F11/F12 and Fn+F11/F12.\n' "$VERSION"
    printf 'The existing Fn shortcut path and all other EFI settings remain unchanged.\n'
    printf 'Private rollback backup: %s\nUse RESTORE-BRIGHTNESS-KEYS.command from this same package to undo the test.\n' "$BACKUP"
}
restore_test() {
    exists "$BACKUP" || fail 'No backup from this test exists; nothing was changed.'
    load_backup
    if exists "$REMOVED"; then
        bundle_matches "$REMOVED"
        exists "$ACTIVE" && fail 'Both active and previously removed bundles exist.'
        exists "$STAGE" && fail 'Both staging and previously removed bundles exist.'
    elif exists "$ACTIVE"; then
        exists "$STAGE" && fail 'Both active and staging bundles exist.'
        bundle_matches "$ACTIVE"
    elif exists "$STAGE"; then
        bundle_matches "$STAGE"
    elif [ "$CURRENT" = "$TESTED" ]; then
        fail 'The tested config references a missing driver. Keep the backup and inspect the EFI before restarting.'
    fi
    if [ "$CURRENT" = "$TESTED" ] && exists "$REMOVED"; then
        fail 'The tested config still references a previously removed driver. Keep the backup and inspect the interrupted operation.'
    fi
    write_phase restoring
    if [ "$CURRENT" = "$TESTED" ]; then atomic_config_replace "$BACKUP/before.plist" "$TESTED" "$BEFORE"; fi
    [ "$(hash "$CONFIG")" = "$BEFORE" ] || fail 'The original config was not restored exactly.'
    if exists "$ACTIVE"; then
        bundle_matches "$ACTIVE"
        exists "$REMOVED" && fail 'The removed-driver destination appeared during restore.'
        /bin/mv "$ACTIVE" "$REMOVED"
    elif exists "$STAGE"; then
        bundle_matches "$STAGE"
        exists "$REMOVED" && fail 'The removed-driver destination appeared during restore.'
        /bin/mv "$STAGE" "$REMOVED"
    fi
    write_phase restored
    printf 'The original config was restored byte for byte. The added driver is no longer in EFI/OC/Kexts.\n'
    printf 'Restart manually. The private backup and any removed driver remain at: %s\n' "$BACKUP"
}

main() {
    local command path
    MODE=${1:-}
    [ "$#" -eq 0 ] || shift
    case "$MODE" in test|restore) ;; *) fail 'Usage: brightness_keys_test.sh test|restore [absolute boot-disk path]';; esac
    [ "$#" -le 1 ] || fail 'Specify at most the boot-disk path.'
    BOOTROOT=${1:-'/Volumes/240 GB'}
    safe_path "$BOOTROOT"
    PACKAGE=$(cd "$(/usr/bin/dirname "$0")/.." && pwd -P)
    PAYLOAD="$PACKAGE/payload/BrightnessKeys.kext"
    MANIFEST="$PACKAGE/payload/manifest.plist"
    VALIDATOR="$PACKAGE/bin/ocvalidate"
    OC="$BOOTROOT/EFI/OC"; CONFIG="$OC/config.plist"
    BACKUP="$OC/backup-function-keys"; STATE="$BACKUP/state.plist"
    ACTIVE="$OC/Kexts/BrightnessKeys.kext"
    STAGE="$OC/Kexts/.BrightnessKeys-s540-stage.kext"
    REMOVED="$BACKUP/removed-BrightnessKeys.kext"
    for command in plutil shasum awk grep find mktemp cmp sort od stat ditto dirname; do
        [ -x "/usr/bin/$command" ] || fail "Required macOS system command is missing: $command."
    done
    TEMP=$(/usr/bin/mktemp -d "${TMPDIR:-/tmp}/s540-brightness-keys.XXXXXX")
    runtime_guard
    for path in "$BOOTROOT" "$BOOTROOT/EFI" "$OC" "$OC/Kexts"; do
        safe_path "$path"; [ -d "$path" ] && [ ! -L "$path" ] || fail "Missing or unsafe directory: $path"
    done
    safe_path "$CONFIG"; ordinary_file "$CONFIG" || fail 'config.plist is missing or is a link.'
    [ -w "$OC" ] && [ -w "$OC/Kexts" ] && [ -w "$CONFIG" ] || fail 'Your account cannot write to the boot disk.'
    validate_payload
    safe_path "$OC/OpenCore.efi"
    ordinary_file "$OC/OpenCore.efi" && [ "$(hash "$OC/OpenCore.efi")" = "$OPENCORE_SHA" ] || fail 'The active OpenCore binary does not match the packaged validator.'
    validate_oc "$CONFIG"
    if [ "$MODE" = test ]; then apply_test; else restore_test; fi
}
main "$@"
