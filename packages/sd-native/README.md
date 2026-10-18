# O2Micro SD reader: native-driver trial

Prepared, **not laptop-confirmed**, for the S540-15IWL GTX 81SW and its external
240 GB test EFI. The operating system remains on the separate USB Samsung SSD.

The October 19 System Information/IORegistry export identifies the O2Micro
`1217:8621`, subsystem `17AA:3803`, SDHCI class `080501`, under
`PciRoot(0x0)/Pci(0x1C,0x0)/Pci(0x0,0x0)`. No SD child driver is attached.
Apple's native `AppleSDXC` 3.5.4 is already loaded as x86_64 on Darwin 25.6.0;
being loaded does not establish attachment or support for this reader.

## Exact scope

The private trial config prepends the NUL-terminated ASCII `pci14e4,16bc` to the
reader's existing `compatible` Data property. It preserves all original entries,
including `pci1217,8621`, the subsystem identifier, class and ACPI name. The real
vendor/device IDs are not changed. There is no additional kext, old Apple binary,
root patch, PCI configuration-register write or O2-specific clock/power sequence.

This is a **matching hypothesis**, not a new driver or established SD support.
The installed AppleSDXC 3.5.4 personality has not been read back, so its acceptance
of this compatible name remains unverified. A no-effect result is possible.

The motivation is a [same-ID Fujitsu implementation](https://github.com/KrzysiuWojcik/Fujitsu-Lifebook-U749-Hackintosh/blob/main/README.md):
its archived Monterey/Ventura setup reports `1217:8621` working through
`14e4:16bc` plus CtlnaSDXC. Its current Tahoe section explicitly says the SD
reader is untested. That result does not validate this native-only trial.

The machine-readable scope and acceptance criteria are in
[sd-native-trial.json](../../config/profiles/sd-native-trial.json).

## Delivery and acceptance

The private delivery contains one ready config, the previously working native
Wi-Fi config for recovery, and short Italian instructions. It also retains the
previously prepared CPU/panel/NVIDIA label edits, whose displayed results remain
pending. Personal configs and reports are not committed here.

Replace only `EFI/OC/config.plist` on the 240 GB test EFI. Boot that EFI, insert a
test SD card, check mounting and file reading, eject it normally and reinsert it.
Do not format or repartition any disk for this test. A successful config
validation is separate from driver attachment and actual card operation.

If the native trial does not attach, obtain the installed AppleSDXC Info.plist
and a new System Information export before selecting another matching or driver
strategy. Do not stack CtlnaSDXC, arbitrary ID changes or unrelated ACPI tables.

## Other hardware scope

The internal PM981a is detected and readable, including capacity/free space, and
is removed from immediate fix priorities by the user. There is no new symptom
justifying USB, Bluetooth or battery changes. The lid device is attached; the
clamshell policy needs further analysis before a sleep patch. Fan telemetry
requires verified EC addresses/scaling. Goodix enumeration does not supply native
Touch ID support. These areas are not silently modified by the SD trial.
