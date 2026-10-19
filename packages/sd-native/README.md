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
| Card Present before/after reinsertion | No -> Yes |
| Card Configured | No |
| Published IOMedia/BSD disk under the SD reader | None |
| User-reported card/file reading | Not working |

The driver detects insertion and creates its storage service but does not finish
card configuration or publish card media. This stops before partition/filesystem
mounting. The focused capture now contains a usable AppleSDXC initialization
trace: repeated `WaitForInterrupt` entries show `NIS=0`, `EIS=0`, followed by
`ConfigureSDMedia` error status `0xe00002bc`
(`kIOReturnError`, a generic IOKit error). The slot remains at 3.3 V and 396 kHz,
with `Card Configured = No` and no card media published.

A single CRC message does not distinguish a card fault from a controller/driver
problem. Repeated UHS-II register values do not prove UHS-II operation; the slot
reports `Host Supports UHS-II = No`. A zero command field can also represent
CMD0, so it does not establish that no command was issued. These observations do
not identify a particular O2 initialization quirk or justify an undocumented
property, register write or driver replacement.

The next useful baseline is whether this **same SD card** reads successfully in
Windows on this laptop or through another known-working reader. The existing
capture cannot distinguish a card fault from a controller/driver fault. Another
identical export or capture is not requested. Native card access,
eject/reinsertion and resume remain unverified.

## Source and delivery scope

A [same-ID Fujitsu implementation](https://github.com/KrzysiuWojcik/Fujitsu-Lifebook-U749-Hackintosh/blob/main/README.md)
reports `1217:8621` working through `14e4:16bc` plus CtlnaSDXC on archived
Monterey/Ventura setups. Its current Tahoe section explicitly says the SD reader
is untested. That historical result motivated the native matching trial; it does
not establish card access on this S540. The
[archived Ventura config](https://github.com/KrzysiuWojcik/Fujitsu-Lifebook-U749-Hackintosh/blob/7c703493a6d71ed426094e44ffd69abc049b5593/config.plist)
also sets software `vendor-id`, `device-id`, `IOName` and `name` properties, loads
CtlnaSDXC and blocks native AppleSDXC. It is therefore not evidence that a full
software ID spoof alone fixes native AppleSDXC 3.5.4.

The machine-readable scope is in
[sd-native-trial.json](../../config/profiles/sd-native-trial.json). The private
trial delivery contains one config, the previously working native Wi-Fi config
for recovery and short Italian instructions. CPU/panel/NVIDIA label edits are
retained and now confirmed in the subsequent export. Personal configs and raw
reports are excluded from this repository.

The internal PM981a is detected/readable and remains outside immediate fault
priorities. Its NVMe kernel block was removed in the delivered hardware v2
package, as requested.

There is no new evidence justifying USB, Bluetooth or battery patches. The lid
sensor is attached, fan telemetry needs verified firmware EC addresses/scaling,
and Goodix USB enumeration does not provide native Touch ID integration.


## Hardware v2 corrections and focused SD capture

The delivered hardware v2 config removes the IONVMeFamily block as requested and
changes SystemMemoryStatus from Auto to Upgradable. Lenovo's exact S540-15IWL GTX PSREF
specifies 4 GB soldered plus one SO-DIMM socket, populated with 8 GB here.
OpenCore 1.0.8 documents Upgradable as clearing the soldered-system-memory
PlatformFeature flag. No capacity, timing or CPU-frequency value is overridden;
MacBookPro16,2 and private identifiers remain unchanged. The displayed memory
status awaits the next boot.

The [hardware v2 profile](../../config/profiles/hardware-v2.json) records the exact
two config edits. Reversing both reproduces the complete prior config. The
private config passes OpenCore 1.0.8 ocvalidate. Recovery uses the preceding SD
trial config, including its former NVMe block and Auto memory status.

[RACCOGLI-ERRORE-SD.command](RACCOGLI-ERRORE-SD.command) performs one focused
read-only capture around card removal/reinsertion. It collects the SD subtree
before/after, filtered unified logs, card-reader output, disk list and installed
AppleSDXC Info.plist. It reads debug.SDXC if available and does not alter it.
Logging may contain no driver messages even with --debug/--level debug; those
options do not enable an undocumented driver debug mask. No new functional SD
patch or old driver is included. Personal diagnostic output remains private.

The original collector's job-status filter was incompatible with macOS Bash
3.2 and produced false timeout messages in the command-status files. That filter
has been corrected. The captured SD logs, installed driver plist and before/after
IORegistry data are valid and provide the findings above; rerunning the same
capture is unnecessary. The installed plist independently confirms both native
match names, `pci17a0,9755` and `pci14e4,16bc`.

The focused process-helper regression check passes on macOS with the system
Bash 3.2.57, including completed commands, nonzero exit status, timeouts and
independent cleanup of the log stream. This verifies the collector fix, not SD
hardware access.

Generic controller/API labels, the CPU speed field and the misleading NVIDIA
profiler Metal field are not changed through speculative capability injections.
