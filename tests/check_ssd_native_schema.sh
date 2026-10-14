#!/bin/bash
# Read-only validation of the diskutil plist fields used by the SSD helper.
# This check never mounts a partition, changes a disk, or prints disk values.
set -eu
set -o pipefail
export LC_ALL=C
umask 077

[[ $(/usr/bin/uname -s) == Darwin ]] || exit 0
schema_root=$(/usr/bin/mktemp -d "${TMPDIR:-/tmp}/ssd-native-schema-XXXXXX")
cleanup_schema() { /bin/rm -rf -- "$schema_root"; }
trap cleanup_schema EXIT
trap 'exit 130' INT TERM HUP

schema_failure() {
    printf 'Native diskutil plist schema check failed: %s.\n' "$1" >&2
    exit 1
}
schema_value() {
    /usr/libexec/PlistBuddy -c "Print :$2" "$1" 2>/dev/null
}
schema_required() {
    local value
    value=$(schema_value "$1" "$2") || schema_failure "missing $2"
    [[ -n "$value" ]] || schema_failure "empty $2"
}
schema_device() {
    [[ "$1" =~ ^disk[0-9]+(s[0-9]+)*$ ]] || schema_failure 'device identifier format'
}

/usr/sbin/diskutil info -plist / > "$schema_root/root.plist" 2>/dev/null || schema_failure 'root info'
schema_required "$schema_root/root.plist" APFSContainerReference
container=$(schema_value "$schema_root/root.plist" APFSContainerReference)
schema_device "$container"
/usr/sbin/diskutil apfs list -plist "$container" > "$schema_root/apfs.plist" 2>/dev/null || schema_failure 'APFS list'
schema_required "$schema_root/apfs.plist" Containers:0:ContainerReference
[[ $(schema_value "$schema_root/apfs.plist" Containers:0:ContainerReference) == "$container" ]] || schema_failure 'APFS container link'
schema_required "$schema_root/apfs.plist" Containers:0:PhysicalStores:0:DeviceIdentifier
store=$(schema_value "$schema_root/apfs.plist" Containers:0:PhysicalStores:0:DeviceIdentifier)
schema_device "$store"
/usr/sbin/diskutil info -plist "$store" > "$schema_root/store.plist" 2>/dev/null || schema_failure 'physical store info'
for key in DeviceIdentifier ParentWholeDisk Content DiskUUID WholeDisk Size APFSContainerReference; do
    schema_required "$schema_root/store.plist" "$key"
done
[[ $(schema_value "$schema_root/store.plist" DeviceIdentifier) == "$store" ]] || schema_failure 'physical store identifier link'
[[ $(schema_value "$schema_root/store.plist" APFSContainerReference) == "$container" ]] || schema_failure 'physical store APFS container link'
[[ $(schema_value "$schema_root/store.plist" WholeDisk) == false ]] || schema_failure 'physical store partition flag'
parent=$(schema_value "$schema_root/store.plist" ParentWholeDisk)
schema_device "$parent"
/usr/sbin/diskutil info -plist "$parent" > "$schema_root/parent.plist" 2>/dev/null || schema_failure 'whole disk info'
for key in DeviceIdentifier Internal WholeDisk Content Size VirtualOrPhysical WritableMedia; do
    schema_required "$schema_root/parent.plist" "$key"
done
[[ $(schema_value "$schema_root/parent.plist" DeviceIdentifier) == "$parent" ]] || schema_failure 'whole disk identifier link'
[[ $(schema_value "$schema_root/parent.plist" WholeDisk) == true ]] || schema_failure 'whole disk flag'
case $(schema_value "$schema_root/parent.plist" Internal) in true|false) :;; *) schema_failure 'internal flag format';; esac
[[ $(schema_value "$schema_root/parent.plist" Size) =~ ^[0-9]+$ ]] || schema_failure 'disk size format'
printf 'Native diskutil APFS and physical-disk plist schema passed.\n'
