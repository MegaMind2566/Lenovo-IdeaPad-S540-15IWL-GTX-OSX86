#!/bin/bash
set -euo pipefail

export PATH=/usr/bin:/bin:/usr/sbin:/sbin

printf 'Riavvio verso A/B RPM sulla EFI esterna.\n'
printf 'Il test usa SMCSuperIO in sola lettura su CFSP 0x73.\n'
sudo /sbin/shutdown -r now
