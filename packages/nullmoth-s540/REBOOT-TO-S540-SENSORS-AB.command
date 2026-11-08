#!/bin/bash
set -euo pipefail

export PATH=/usr/bin:/bin:/usr/sbin:/sbin

printf 'Riavvio verso A/B S540Sensors sulla EFI esterna.\n'
printf 'Il plugin pubblica soltanto la temperatura NVIDIA TG0D.\n'
sudo /sbin/shutdown -r now
