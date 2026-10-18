# AC9560 native Wi-Fi for macOS Tahoe

Development trial for **Lenovo IdeaPad S540-15IWL GTX 81SW**, Intel Wireless-AC
9560 **8086:9DF0**, macOS Tahoe 26 / Darwin 25, x86_64, OpenCore 1.0.8.

The existing itlwm 2.3.0 / HeliPort connection is confirmed working. This component
starts the requested migration to the native macOS Wi-Fi interface. It uses
[laobamac's AirportItlwm Tahoe source](https://github.com/laobamac/itlwm), derived
from OpenIntelWireless and OpenBSD, at commit
`738d4c61b5a64433b27c1ab09dba94916ab77d8d`. It is an integration of that driver,
not a new implementation of Intel's radio stack. Laptop operation is **pending**.

## First milestone

- Compile the actual `AirportItlwm-Tahoe` Release target on Intel macOS.
- Verify the AC9560 PCI match, its `iwm-9000-46` firmware, native Airport
  personalities, IO80211/Skywalk dependencies and x86_64 kernel executable.
- Sign the extension ad hoc, verify the signature and hash every package file.
- Prepare a separate private EFI copy and validate its OpenCore configuration.
- Observe the native interface and connection with one filtered laptop report.

The source uses Tahoe WCL / IO80211 / Skywalk, with the upstream VT-d path. This
trial does not install old Apple Wi-Fi extensions, root patches or frameworks,
change SIP, AMFI, SecureBootModel, IOMapper settings, Bluetooth or NVIDIA.

The selected fork describes scanning, joining, switching and private addresses.
It supports WPA2-Personal and WPA2/WPA3 transition networks with optional PMF.
WPA3-only, mandatory PMF, AWDL/AirDrop and MLO are unsupported. All adapter-specific
behavior still needs verification on this AC9560. No speed or Continuity result
is claimed. Wi-Fi 6 settings are not relevant to this 802.11ac adapter.

## Build

From the project repository on Intel macOS with Xcode and Python 3.10 or newer:

```sh
python3 builders/build_wifi_native.py --output-dir build/wifi-native
python3 packages/wifi-native/tests/test_wifi_native.py \
  --ocvalidate build/wifi-native/S540-wifi-native-v1/tools/ocvalidate
```

Use a new output directory for each build. The builder downloads immutable,
size- and SHA256-locked source archives and the original OpenCore 1.0.8 validator.
It uses MacKernelSDK `3f750085caa17ec3a7880f11c11bf4f48cd6a164` and preserves the
upstream driver source unchanged. The build creates `S540-wifi-native-v1.zip`,
`package-result.json` and the complete compiler log. The ZIP includes the complete
corresponding driver and SDK source archives, build script and licenses.

On other hosts, source inspection is available with `--audit-only`; it neither
compiles a driver nor establishes laptop operation. A successful macOS build also
does not prove kernel loadability or radio operation on Tahoe.

## Prepare one offline EFI trial

These commands refer to the **built, extracted package**, not the source folder.
Python 3 is required on the laptop. Keep the current working boot route available.
From the extracted `S540-wifi-native-v1` directory:

The delivery includes `LEGGIMI-PRIMA.txt` in Italian and two double-click launchers.
`PREPARA-WIFI-NATIVO.command` asks for the current EFI folder and creates a new
Desktop trial copy. `RACCOGLI-WIFI-NATIVO.command` saves one new filtered report
on the Desktop. The equivalent terminal commands are below.

```sh
python3 tools/stage_wifi_native.py \
  --efi /path/to/current-private/EFI \
  --output "$HOME/Desktop/S540-native-WiFi/EFI"
```

The program verifies the package, checks the existing config with the bundled
`ocvalidate`, then copies the complete current EFI. In the copy it makes only:

1. `Kernel/Add/itlwm.kext/Enabled = false`.
2. One new `AirportItlwm.kext` entry restricted to Darwin `25.0.0–25.99.99`.
3. The new `OC/Kexts/AirportItlwm.kext` payload.

The original itlwm payload, including any private recovery profile, remains in
both copies. All other EFI files and settings are retained. The prepared config
is checked again before publishing the offline copy. Existing output folders,
symlinks, incomplete EFIs, duplicate Airport entries and configured legacy-stack
injection/blocking are refused. Output under `/Volumes` is refused: this helper
does not install to a mounted boot partition. Use this copy only for Tahoe.

The output contains the laptop's identity and potentially saved Wi-Fi credentials.
Keep it private. Do not upload it or add it to Git. No network connection is used
during staging. EFI deployment and the first laptop boot remain a separate step.

## One combined laptop checkpoint

After explicitly booting the trial EFI, use the macOS Wi-Fi menu to scan, join a
WPA2 network, disconnect/reconnect and switch networks. HeliPort is not used by
AirportItlwm. Keep these observations together; a separate boot for each is not
needed. Then create a new report:

```sh
python3 tools/collect_wifi_native.py \
  --output "$HOME/Desktop/S540-wifi-native-report.json"
```

The report records macOS/Darwin versions, loaded Intel drivers, native Wi-Fi
interface names, radio power, link state and whether the default route uses the
interface. It excludes SSIDs, BSSIDs, MAC/IP addresses, keys and the private EFI.
Command failures remain explicit. An interface or active link alone does not
prove scanning, authentication, switching or sleep recovery; include the observed
results with the report. Do not run both Intel drivers together.

For rollback, boot the unchanged original EFI and use HeliPort as before. Nothing
in this package installs to the system volume or changes persistent network
preferences. Bluetooth and the ongoing NVIDIA work retain their existing state.
