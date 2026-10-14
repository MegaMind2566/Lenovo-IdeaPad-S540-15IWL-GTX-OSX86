#!/usr/bin/env python3
"""Save a local Wi-Fi profile in the extracted test EFI. No network requests."""
from pathlib import Path
import getpass
import plistlib


def main():
    root = Path(__file__).resolve().parents[1]
    path = root/'EFI/OC/Kexts/itlwm.kext/Contents/Info.plist'
    if not path.is_file():
        raise SystemExit('Estrai prima tutto il pacchetto EFI in una cartella normale.')
    print('Inserisci la rete da usare durante la Recovery. I dati restano su questo PC.')
    ssid = input('Nome esatto della rete (SSID): ')
    if not ssid:
        raise SystemExit('SSID vuoto: nessuna modifica.')
    password = getpass.getpass('Password Wi-Fi (non viene mostrata): ')
    info = plistlib.loads(path.read_bytes())
    info['IOKitPersonalities']['itlwm']['WiFiConfig'] = {
        'WiFi_1': {'ssid': ssid, 'password': password}}
    path.write_bytes(plistlib.dumps(info, sort_keys=False))
    print('Profilo salvato. Copia ora la cartella EFI sulla chiavetta.')
    print('La password è nel plist locale: non caricare questa copia su GitHub o in chat.')


if __name__ == '__main__':
    main()
