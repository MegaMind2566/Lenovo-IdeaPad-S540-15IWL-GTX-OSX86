#!/bin/zsh

set -euo pipefail

script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)"
workspace="$(CDPATH= cd -- "$script_dir/../.." && pwd -P)"
payload="$workspace/_candidates/NMXAudio-nvidia-exact-auxkc-preflight/pkgroot"
result_file='/tmp/s540-nmxaudio-auxkc-preflight-result.txt'
expected_info_hash='ebff8ac2ea5b57f7d6ccbb764f56025213a22a4156df8dd3b8c9c9e64f126d4a'
expected_binary_hash='77e19e244978ce64e4505c4701069edfe609379f91a9c76313b4a27ded4ab07a'

/bin/rm -f "$result_file"
exec > >(tee "$result_file") 2>&1

echo 'Preflight NMXAudio NVIDIA: costruzione temporanea della Auxiliary Kernel Collection.'
echo 'CHECK=1 garantisce l’uscita prima di backup, installazione e modifica dei boot-args.'
echo 'Inserisci la password amministratore quando richiesta.'

[[ -x "$payload/install.sh" && -f "$payload/SHA256SUMS" ]] || {
    echo 'Rifiuto: payload di preflight incompleto.'
    exit 1
}
info_hash=$(/usr/bin/shasum -a 256 "$payload/Library/Extensions/NMXAudio.kext/Contents/Info.plist" | /usr/bin/awk '{print $1}')
binary_hash=$(/usr/bin/shasum -a 256 "$payload/Library/Extensions/NMXAudio.kext/Contents/MacOS/NMXAudio" | /usr/bin/awk '{print $1}')
[[ "$info_hash" == "$expected_info_hash" && "$binary_hash" == "$expected_binary_hash" ]] || {
    echo "Rifiuto: hash NMXAudio inattesi ($info_hash, $binary_hash)."
    exit 1
}
(cd "$payload" && /usr/bin/shasum -a 256 --strict -c SHA256SUMS --quiet)

sudo -v
sudo /usr/bin/env CHECK=1 /bin/bash "$payload/install.sh"
echo 'PREFLIGHT_NMXAUDIO_AUXKC_OK'
