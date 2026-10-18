# O2Micro SD reader: native-driver trial

Current result: **native driver attached and card present, but card not
configured**. The card remains unreadable. Target: S540-15IWL GTX 81SW and the
external 240 GB test EFI; macOS remains on the separate USB Samsung SSD.

## Verified hardware and driver

The initial October 19 System Information/IORegistry export identifies O2Micro
`1217:8621`, subsystem `17AA:3803`, SDHCI class `080501`, under
`PciRoot(0x0)/Pci(0x1C,0x0)/Pci(0x0,0x0)`, without an attached SD driver.
Native AppleSDXC 3.5.4 was already loaded as x86_64 on Darwin 25.6.0.

The trial prepends NUL-terminated ASCII `pci14e4,16bc` to the reader's compatible
Data property and preserves all its original compatibility entries and real
vendor/device IDs. No extra kext, older Apple binary or root patch is distributed.
No O2-specific PCI register/clock/power initialization was implemented here.

The subsequent export with the SD inserted now confirms this exact chain:

`1217:8621 -> AppleSDXC -> AppleSDXCSlot@1 -> AppleSDXCBlockStorageDevice -> IOBlockStorageDriver`

AppleSDXC's actual IONameMatch includes `pci17a0,9755` and `pci14e4,16bc`;
IONameMatched is `pci14e4,16bc`. The matching hypothesis is therefore verified on
this laptop. The actual driver attachment is more than a new System Information
label, but does not establish working card access.

## Remaining failure

| Observation | Result |
|---|---|
| Card Present | Yes |
| Card Configured | No |
| Published IOMedia/BSD disk under the SD reader | None |
| User-reported card/file reading | Not working |

The driver detects insertion and creates its storage service but does not finish
card configuration or publish card media. This stops before partition/filesystem
mounting. The exported slot clock/voltage values are not sufficient to identify
the failing command or attribute the fault to a particular O2 quirk. The provided
logs do not contain a usable SD initialization trace.

The next investigation concerns card initialization, including whether the card
was present at boot or inserted later, before selecting any driver/register
change. Another identical System Information export is not requested. Native
card access, eject/reinsertion and resume remain unverified.

## Source and delivery scope

A [same-ID Fujitsu implementation](https://github.com/KrzysiuWojcik/Fujitsu-Lifebook-U749-Hackintosh/blob/main/README.md)
reports `1217:8621` working through `14e4:16bc` plus CtlnaSDXC on archived
Monterey/Ventura setups. Its current Tahoe section explicitly says the SD reader
is untested. That historical result motivated the native matching trial; it does
not establish card access on this S540.

The machine-readable scope is in
[sd-native-trial.json](../../config/profiles/sd-native-trial.json). The private
trial delivery contains one config, the previously working native Wi-Fi config
for recovery and short Italian instructions. CPU/panel/NVIDIA label edits are
retained and now confirmed in the subsequent export. Personal configs and raw
reports are excluded from this repository.

The internal PM981a is detected/readable and remains outside immediate fault
priorities. The user explicitly requested removing its NVMe kernel block in the
**next package**, not as an immediate separate change. That removal remains queued;
no new private package has been generated from this audit.

There is no new evidence justifying USB, Bluetooth or battery patches. The lid
sensor is attached, fan telemetry needs verified firmware EC addresses/scaling,
and Goodix USB enumeration does not provide native Touch ID integration.
