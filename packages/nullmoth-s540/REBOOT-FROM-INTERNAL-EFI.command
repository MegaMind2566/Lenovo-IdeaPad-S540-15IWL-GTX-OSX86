#!/bin/zsh

set -euo pipefail

if /usr/sbin/diskutil list external | /usr/bin/grep -q '^/dev/disk'; then
    echo 'Rifiuto: è ancora collegato un disco esterno.'
    /usr/sbin/diskutil list external
    exit 1
fi

location=$(/usr/sbin/diskutil info disk0s1 | /usr/bin/awk -F: '/Device Location/ {gsub(/^[[:space:]]+/, "", $2); print $2}')
partition_type=$(/usr/sbin/diskutil info disk0s1 | /usr/bin/awk -F: '/Partition Type/ {gsub(/^[[:space:]]+/, "", $2); print $2}')
[[ "$location" == 'Internal' && "$partition_type" == 'EFI' ]] || {
    echo 'Rifiuto: disk0s1 non corrisponde alla ESP interna attesa.'
    exit 1
}

echo 'Riavvio dalla sola EFI interna. Inserisci la password se richiesta.'
sudo /sbin/shutdown -r now
