#!/bin/bash
set -euo pipefail

export PATH=/usr/bin:/bin:/usr/sbin:/sbin

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)"
S540_ROOT="$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd -P)"
S540_OC="/Volumes/240 GB/EFI/OC"
S540_BACKUP="/Volumes/240 GB/EFI/OC-BEFORE-FAN-RPM-AB-20261107"
S540_ARCHIVE="$S540_ROOT/_external/VirtualSMC-1.3.8-RELEASE.zip"
S540_OCVALIDATE="$S540_ROOT/_external/opencore-1.0.8/extracted/Utilities/ocvalidate/ocvalidate"
S540_EXPECTED_ARCHIVE="2e29a8aaf91b4eb0bcdf5913ed17e70f5cf76531122acd4132eff7813a54de8b"
S540_TMP="$(mktemp -d /tmp/s540-fan-rpm.XXXXXX)"
trap 'rm -rf "$S540_TMP"' EXIT

[ -d "$S540_OC" ] || { printf 'EFI esterna non montata: %s\n' "$S540_OC" >&2; exit 1; }
[ ! -e "$S540_BACKUP" ] || { printf 'Backup gia presente: %s\n' "$S540_BACKUP" >&2; exit 1; }
[ -x "$S540_OCVALIDATE" ] || { printf 'ocvalidate non disponibile.\n' >&2; exit 1; }

S540_ACTUAL_ARCHIVE="$(shasum -a 256 "$S540_ARCHIVE" | awk '{print $1}')"
[ "$S540_ACTUAL_ARCHIVE" = "$S540_EXPECTED_ARCHIVE" ] || {
  printf 'Hash archivio VirtualSMC inatteso: %s\n' "$S540_ACTUAL_ARCHIVE" >&2
  exit 1
}

ditto "$S540_OC" "$S540_BACKUP"
unzip -q "$S540_ARCHIVE" 'Kexts/SMCSuperIO.kext/*' -d "$S540_TMP"
ditto "$S540_TMP/Kexts/SMCSuperIO.kext" "$S540_OC/Kexts/SMCSuperIO.kext"

S540_PLIST="$S540_OC/config.plist"
S540_PCI_PATH='PciRoot(0x0)/Pci(0x1F,0x0)'

/usr/libexec/PlistBuddy -c 'Add :Kernel:Add: dict' "$S540_PLIST"
S540_INDEX="$(/usr/libexec/PlistBuddy -c 'Print :Kernel:Add' "$S540_PLIST" | awk '/Dict \{/{count++} END{print count-1}')"
/usr/libexec/PlistBuddy -c "Add :Kernel:Add:$S540_INDEX:Arch string x86_64" "$S540_PLIST"
/usr/libexec/PlistBuddy -c "Add :Kernel:Add:$S540_INDEX:BundlePath string SMCSuperIO.kext" "$S540_PLIST"
/usr/libexec/PlistBuddy -c "Add :Kernel:Add:$S540_INDEX:Comment string 'S540 read-only EC fan RPM probe at CFSP 0x73'" "$S540_PLIST"
/usr/libexec/PlistBuddy -c "Add :Kernel:Add:$S540_INDEX:Enabled bool true" "$S540_PLIST"
/usr/libexec/PlistBuddy -c "Add :Kernel:Add:$S540_INDEX:ExecutablePath string Contents/MacOS/SMCSuperIO" "$S540_PLIST"
/usr/libexec/PlistBuddy -c "Add :Kernel:Add:$S540_INDEX:MaxKernel string 25.99.99" "$S540_PLIST"
/usr/libexec/PlistBuddy -c "Add :Kernel:Add:$S540_INDEX:MinKernel string ''" "$S540_PLIST"
/usr/libexec/PlistBuddy -c "Add :Kernel:Add:$S540_INDEX:PlistPath string Contents/Info.plist" "$S540_PLIST"

/usr/libexec/PlistBuddy -c "Add :DeviceProperties:Add:$S540_PCI_PATH dict" "$S540_PLIST"
/usr/libexec/PlistBuddy -c "Add :DeviceProperties:Add:$S540_PCI_PATH:ec-device string generic" "$S540_PLIST"
plutil -insert "DeviceProperties.Add.$S540_PCI_PATH.fan-count" -data AQAAAA== "$S540_PLIST"
plutil -insert "DeviceProperties.Add.$S540_PCI_PATH.fan0-addr" -data cwAAAA== "$S540_PLIST"
plutil -insert "DeviceProperties.Add.$S540_PCI_PATH.fan0-size" -data AgAAAA== "$S540_PLIST"
plutil -insert "DeviceProperties.Add.$S540_PCI_PATH.fan0-big" -data AAAAAA== "$S540_PLIST"

plutil -lint "$S540_PLIST"
"$S540_OCVALIDATE" "$S540_PLIST"

if codesign --verify --deep --strict "$S540_OC/Kexts/SMCSuperIO.kext"; then
  printf 'Firma kext verificata.\n'
else
  printf 'Release ufficiale non firmata; verifica tramite hash esatti.\n'
fi
file "$S540_OC/Kexts/SMCSuperIO.kext/Contents/MacOS/SMCSuperIO"
shasum -a 256 \
  "$S540_OC/Kexts/SMCSuperIO.kext/Contents/Info.plist" \
  "$S540_OC/Kexts/SMCSuperIO.kext/Contents/MacOS/SMCSuperIO" \
  "$S540_PLIST"

printf 'A/B RPM pronto sulla EFI esterna. Backup: %s\n' "$S540_BACKUP"
