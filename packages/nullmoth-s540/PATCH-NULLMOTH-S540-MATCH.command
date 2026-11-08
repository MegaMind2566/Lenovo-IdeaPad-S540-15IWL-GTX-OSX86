#!/bin/bash
set -euo pipefail

PATH=/usr/bin:/bin:/usr/sbin:/sbin
export PATH

if [ "$(id -u)" != 0 ]; then
  exec sudo /bin/bash "$0" "$@"
fi

STAMP=$(date +%Y%m%d-%H%M%S)
BACKUP="/Library/NullMoth/s540-match-backup-$STAMP"
EXT=/Library/Extensions
KC=/Library/KernelCollections/AuxiliaryKernelExtensions.kc
NEW="$KC.s540-match-new"
COMMITTED=0

restore() {
  [ "$COMMITTED" = 0 ] || return 0
  [ -d "$BACKUP" ] || return 0
  printf 'Ripristino i file precedenti dopo un errore...\n' >&2
  for name in NVRM NVAccel; do
    [ ! -d "$BACKUP/$name.kext" ] || { rm -rf "$EXT/$name.kext"; ditto "$BACKUP/$name.kext" "$EXT/$name.kext"; }
  done
  for target in 15 26; do
    [ ! -d "$BACKUP/cache-$target" ] || {
      rm -rf "/Library/NullMoth/kexts/$target"
      ditto "$BACKUP/cache-$target" "/Library/NullMoth/kexts/$target"
    }
  done
  rm -f "$NEW"
}
trap restore EXIT

for path in "$EXT/NVRM.kext" "$EXT/NVAccel.kext" \
            /Library/NullMoth/kexts/15/NVAccel.kext \
            /Library/NullMoth/kexts/26/NVAccel.kext "$KC"; do
  [ -e "$path" ] || { printf 'Manca: %s\n' "$path" >&2; exit 1; }
done

mkdir -m 700 "$BACKUP"
ditto "$EXT/NVRM.kext" "$BACKUP/NVRM.kext"
ditto "$EXT/NVAccel.kext" "$BACKUP/NVAccel.kext"
ditto /Library/NullMoth/kexts/15 "$BACKUP/cache-15"
ditto /Library/NullMoth/kexts/26 "$BACKUP/cache-26"
cp -p "$KC" "$BACKUP/AuxiliaryKernelExtensions.kc"

set_match() {
  local bundle=$1 personality=$2
  /usr/libexec/PlistBuddy -c "Set :IOKitPersonalities:$personality:IOPCIPrimaryMatch 0x1f9110de" \
    "$bundle/Contents/Info.plist"
  codesign --force --sign - "$bundle"
  codesign --verify --strict "$bundle"
}

set_match "$EXT/NVRM.kext" NVRM
set_match "$EXT/NVAccel.kext" NVAccel
for target in 15 26; do
  directory="/Library/NullMoth/kexts/$target"
  set_match "$directory/NVAccel.kext" NVAccel
  (cd "$directory" && find NVAccel.kext -type f -exec shasum -a 256 '{}' \;) > "$directory/SHA256SUMS"
done
chown -R root:wheel "$EXT/NVRM.kext" "$EXT/NVAccel.kext" /Library/NullMoth/kexts/15 /Library/NullMoth/kexts/26
chmod -R go-w "$EXT/NVRM.kext" "$EXT/NVAccel.kext" /Library/NullMoth/kexts/15 /Library/NullMoth/kexts/26

rm -f "$NEW"
args=(--allow-missing-kdk)
[ ! -f /System/Library/Kernels/kernel ] || args+=(--kernel /System/Library/Kernels/kernel)
kmutil create -n aux --volume-root / "${args[@]}" \
  -B /System/Library/KernelCollections/BootKernelExtensions.kc \
  -S /System/Library/KernelCollections/SystemKernelExtensions.kc \
  --repository "$EXT" -A "$NEW" -z

inspect=$(kmutil inspect -a x86_64 -A "$NEW" 2>&1)
for identifier in com.nullmoth.NVRM com.nullmoth.NVAccel com.nullmoth.NVRMFB com.nullmoth.NVRMAGDC; do
  printf '%s\n' "$inspect" | grep -q "$identifier" || {
    printf 'La nuova AuxKC non contiene %s\n' "$identifier" >&2
    exit 1
  }
done

mv -f "$NEW" "$KC"
chmod 744 "$KC"
chown root:wheel "$KC"
printf '%s\n' "$BACKUP" > /Library/NullMoth/s540-match-backup-current
chmod 600 /Library/NullMoth/s540-match-backup-current
COMMITTED=1
printf 'PASS_MATCH_S540 backup=%s\n' "$BACKUP"
