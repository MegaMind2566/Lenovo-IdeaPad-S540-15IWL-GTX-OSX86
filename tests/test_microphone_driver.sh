#!/bin/bash
# CI-only regression check with real signed VoodooHDA bundles, no driver load.
set -euo pipefail
umask 077
export LC_ALL=C
[ "${GITHUB_ACTIONS:-}" = true ] || { echo 'Run this fixture in GitHub Actions.' >&2; exit 1; }
ROOT=$(cd -P "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
CHECK="$ROOT/packages/microphone/tools/verify_microphone_driver.sh"
FIXTURE=$(/usr/bin/mktemp -d "$RUNNER_TEMP/microphone-driver-fixture.XXXXXX")
trap '/bin/rm -rf "$FIXTURE"' EXIT

curl --fail --location --silent --show-error --max-time 60 'https://github.com/CloverHackyColor/VoodooHDA/releases/download/Release368/VoodooHDA.kext-368.zip' -o "$FIXTURE/upstream.zip"
test "$(/usr/bin/shasum -a 256 "$FIXTURE/upstream.zip" | /usr/bin/awk '{print $1}')" = 9aaa01b245f4827b2de5edfdc028700b9bc8823f03bfb1daf280b8571f88adb0
/usr/bin/unzip -q "$FIXTURE/upstream.zip" -d "$FIXTURE/upstream"
ORIGINAL="$FIXTURE/upstream/VoodooHDA.kext"
EXPECTED_ORIGINAL=932a7c9e46a65fdab7c8729f599c1094b568ae4fc7f17dad9818c83e833a0973
test "$(/bin/bash "$CHECK" "$ORIGINAL" "$FIXTURE/no-backup")" = "$EXPECTED_ORIGINAL"

BACKUP="$FIXTURE/audio-backup"
VOLUME="$BACKUP/volume-test"
MODIFIED="$VOLUME/modified/VoodooHDA.kext"
INSTALLED="$FIXTURE/installed/VoodooHDA.kext"
STATE="$BACKUP/state.plist"
KEY=IOKitPersonalities.VoodooHDA.VoodooHDAEnableVolumeChangeFix
/bin/mkdir -p "$VOLUME/original" "$VOLUME/modified" "$FIXTURE/installed"
/usr/bin/ditto --norsrc --noextattr --noacl --noqtn "$ORIGINAL" "$VOLUME/original/VoodooHDA.kext"
/usr/bin/ditto --norsrc --noextattr --noacl --noqtn "$ORIGINAL" "$MODIFIED"
/usr/bin/plutil -replace "$KEY" -bool true "$MODIFIED/Contents/Info.plist"
/usr/bin/codesign --force --sign - "$MODIFIED"
/usr/bin/codesign --verify --strict "$MODIFIED"
/usr/bin/ditto --norsrc --noextattr --noacl --noqtn "$MODIFIED" "$INSTALLED"
/usr/bin/plutil -create xml1 "$STATE"
/usr/bin/plutil -insert Format -integer 2 "$STATE"
/usr/bin/plutil -insert Phase -string installed "$STATE"
/usr/bin/plutil -insert VolumePhase -string ready "$STATE"
/usr/bin/plutil -insert VolumeTarget -string modified "$STATE"
/usr/bin/plutil -insert VolumeManifestHash -string pending "$STATE"
save_manifest() {
    local file
    : > "$VOLUME/SHA256SUMS"
    for file in Contents/Info.plist Contents/MacOS/VoodooHDA Contents/_CodeSignature/CodeResources; do
        printf '%s  %s\n' "$(/usr/bin/shasum -a 256 "$MODIFIED/$file" | /usr/bin/awk '{print $1}')" "$file" >> "$VOLUME/SHA256SUMS"
    done
    /usr/bin/plutil -replace VolumeManifestHash -string "$(/usr/bin/shasum -a 256 "$VOLUME/SHA256SUMS" | /usr/bin/awk '{print $1}')" "$STATE"
}
save_manifest
EXPECTED_MODIFIED=$(/usr/bin/shasum -a 256 "$INSTALLED/Contents/MacOS/VoodooHDA" | /usr/bin/awk '{print $1}')
test "$EXPECTED_MODIFIED" != "$EXPECTED_ORIGINAL"
test "$(/bin/bash "$CHECK" "$INSTALLED" "$BACKUP")" = "$EXPECTED_MODIFIED"
echo 'Original and re-signed V3 bundle accepted with distinct Mach-O hashes.'

/bin/cp "$STATE" "$FIXTURE/good-state.plist"
/usr/bin/plutil -replace VolumeManifestHash -string 0000000000000000000000000000000000000000000000000000000000000000 "$STATE"
if /bin/bash "$CHECK" "$INSTALLED" "$BACKUP" > "$FIXTURE/rejected.txt" 2> "$FIXTURE/rejected.stderr"; then
    echo 'Unbound manifest was incorrectly accepted.' >&2; exit 1
fi
/usr/bin/grep -F 'The volume manifest does not match the saved state.' "$FIXTURE/rejected.stderr"
/bin/cp "$FIXTURE/good-state.plist" "$STATE"

# A valid signature and updated manifest must not authorize another plist edit.
/usr/bin/plutil -insert UnexpectedDiagnosticFixture -bool true "$MODIFIED/Contents/Info.plist"
/usr/bin/codesign --force --sign - "$MODIFIED"
/usr/bin/codesign --verify --strict "$MODIFIED"
/usr/bin/ditto --norsrc --noextattr --noacl --noqtn "$MODIFIED" "$INSTALLED"
save_manifest
if /bin/bash "$CHECK" "$INSTALLED" "$BACKUP" > "$FIXTURE/rejected.txt" 2> "$FIXTURE/rejected.stderr"; then
    echo 'Unexpected plist edit was incorrectly accepted.' >&2; exit 1
fi
/usr/bin/grep -F 'The variant plist contains changes beyond the volume correction.' "$FIXTURE/rejected.stderr"
echo 'Manifest mismatch and additional signed plist edit rejected.'
