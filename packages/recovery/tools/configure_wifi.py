#!/usr/bin/env python3
"""Save a local Wi-Fi profile in the extracted test EFI. No network requests."""
from pathlib import Path
import getpass
import plistlib


def main():
    root = Path(__file__).resolve().parents[1]
    path = root/'EFI/OC/Kexts/itlwm.kext/Contents/Info.plist'
    if not path.is_file():
        raise SystemExit('First extract the complete EFI package to a regular directory.')
    print('Enter the network to use in Recovery. The data stays on this PC.')
    ssid = input('Exact network name (SSID): ')
    if not ssid:
        raise SystemExit('Empty SSID; no changes made.')
    password = getpass.getpass('Wi-Fi password (hidden): ')
    info = plistlib.loads(path.read_bytes())
    info['IOKitPersonalities']['itlwm']['WiFiConfig'] = {
        'WiFi_1': {'ssid': ssid, 'password': password}}
    path.write_bytes(plistlib.dumps(info, sort_keys=False))
    print('Profile saved. Now copy the EFI directory to the USB drive.')
    print('The password is stored in the local plist; do not upload this copy to GitHub or the chat.')


if __name__ == '__main__':
    main()
