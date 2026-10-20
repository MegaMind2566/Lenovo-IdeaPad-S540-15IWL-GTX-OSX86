# O2Micro SD reader: native-driver trial

Latest result: **BigSurSDXC 1.9.0 loaded on Tahoe, but no card media published**.
The earlier native-driver trial detected the card without completing configuration. The card remains unreadable. Target: S540-15IWL GTX 81SW and the
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

The user has now confirmed that this same SD card reads successfully in Windows.
This supports investigating the macOS driver path next. Another identical export
or native-driver capture is not requested. Native card access, eject/reinsertion
and resume remain unverified.

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
read-only capture around card removal/reinsertion. It collects AppleSDXC,
BgSurSDXC and CtlnaSDXC subtrees before/after, filtered unified logs, card-reader
output, disk list and installed AppleSDXC Info.plist. It reads debug.SDXC if
available and does not alter it.
Logging may contain no driver messages even with --debug/--level debug; those
options do not enable an undocumented driver debug mask. Hardware v2 includes
no new functional SD patch or old driver. Personal diagnostic output remains
private.

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

## Historical S540 driver: isolated compatibility test

The [mandresve S540 project](https://github.com/mandresve/Lenovo-IdeaPad-S540-Hackintosh)
and its [original card-reader issue](https://github.com/lietxia/XiaoXinAir14IML_2019_hackintosh/issues/29)
provide a more specific precedent. The original IORegistry screenshot shows
`vendor-id = 1217`, `device-id = 8621` and attached CtlnaSDXC storage services,
with the real vendor/device IDs retained. The subsystem and PCI path differ
from this S540, so its complete EFI must not be copied. The author reports
successful CtlnaSDXC testing on two S540 machines and BigSurSDXC on Ventura 13.5.
These are historical reports, not proof of Tahoe support.

The reference CtlnaSDXC 1.9.0 executable is byte-for-byte identical to the
[official OCLP BigSurSDXC payload](https://github.com/dortania/OpenCore-Legacy-Patcher/blob/f1d67923c827be2deebb1172333e7f0afb340583/payloads/Kexts/Misc/BigSurSDXC-v1.0.0.zip)
after replacing only the same-length class-name text `CtlnaSDXC` with
`BgSurSDXC`. This is a repackaged Apple Big Sur 11.6.1 driver with renamed
classes, not a new open-source O2 driver or a Catalina source port. The test
uses the official BigSurSDXC payload unchanged.

Its personality has `IOProbeScore = 6000`, compared with `0` on the attached
native driver in the user's capture. This gives a concrete basis for trying
the older driver through matching priority, without adding an AppleSDXC block.
It does not establish that VT-d caused the native failure or prove Darwin 25
ABI compatibility.

The [legacy trial profile](../../config/profiles/sd-legacy-trial.json) limits
the experiment to x86_64/Darwin 25 and the external 240 GB test EFI. Relative to
hardware v2, the private config adds exactly one Kernel/Add entry and preserves
all other settings, including the existing compatible property, native Wi-Fi,
labels, memory description and NVMe unblock. Recovery contains the exact
hardware v2 config. The package includes the kext, config and collector; there
is no system-volume installation. A successful test requires actual file
reading, not merely a new System Information entry. If reading works, another
diagnostic capture is unnecessary; if it fails, the updated collector can
distinguish the BgSurSDXC and native driver subtrees.

Generic controller/API labels, the CPU speed field and the misleading NVIDIA
profiler Metal field are not changed through speculative capability injections.

## October 20 compatibility-test result

The new focused capture confirms `com.apple.driver.BigSurSDXC`, class
`BgSurSDXC`, active on macOS 26.7.1/Darwin 25.6.0 with probe score 6000.
The AppleSDXC and CtlnaSDXC controller subtrees are absent. The intended driver
replacement therefore took effect; another native-driver block is not justified
by a claim that the wrong driver won matching.

The BgSurSDXC slot and block-storage service exist, but neither IOMedia nor a
new BSD disk appears. All storage I/O counters remain zero. The card-reader
profiler section is empty, which alone is inconclusive for renamed legacy
classes; the missing media is the relevant failure. `Card Configured` is not
exposed by this driver and must not be reported as an observed false value.

`Card Present` is Yes in both snapshots. This does not establish whether
removal was missed, whether the property is cached, or whether the card was
already present. Block-device power state changes from 1 to 3; a 2000 ms
`pmDriverCallout(0x2)` waiting message is not an SD command error or proof of
a power fault. `Clock Divisor = 0` does not prove a disabled card clock.

The collector's capture commands all return 0, stderr files are empty and
the log stream exits with the expected 143. The previous false-timeout bug
is resolved. There is no detailed command-initialization trace comparable to
the native-driver capture; fewer errors in these logs do not establish success.

This test verifies loading and matching, not working SD access. Before another
configuration or driver change, clarify whether the card was present at boot
or inserted only after macOS started. A controlled startup with the card present,
or a direct Windows-to-macOS reboot if needed, can distinguish startup and
hot-insertion behavior. Both remain hypotheses for the next hardware check.
Personal reports, serial numbers and volume identifiers are excluded.

## Startup with SD already inserted also fails

The user clarified that the captured legacy-driver test used insertion after
macOS started, then tested a full power-off/startup with the SD already inserted.
Card access still failed. The latter is a user-reported functional result;
no additional registry or command trace was provided for that startup.
This makes an exclusively hot-insertion failure less likely, but does not
identify the failing initialization step or prove an interrupt/power fault.

Inspection of the legacy binary confirms that its `IONameMatched` compatibility
branch is already selected on this machine. No consumer was identified for
the cosmetic properties or Apple subvendor injection that differ in a working
reference config. These differences do not justify another property-only test.

The Linux [SEABIRD1 fix](https://github.com/torvalds/linux/commit/cdd2b769789ae1a030e1a26f6c37c5833cabcb34)
and [O2 PLL/card-detection fix](https://github.com/torvalds/linux/commit/69d91ed1469b49b4d3b5a9ac40e4abc453698dc2)
show controller-specific clock/card-detection handling for this family.
This motivates an initialization investigation; it does not establish that
the same condition causes this macOS failure. The 8620 revision-1 delay and
FUJIN2/8520 register sequences must not be copied onto 8621 without evidence.

The next controlled check retains the same EFI and SD: read the card in
Windows, then restart directly into macOS without removing the card or powering
off. If this changes the outcome, an inherited controller state becomes a
useful lead. Failure would remain inconclusive because firmware/driver reset
can erase that state. Before implementing O2 register initialization, targeted
read-only PCI/MMIO observations and the relevant OEM ACPI would be preferable
to speculative register writes or another renamed copy of the same driver.

## Bounded register observer prepared

The user also reports no improvement after reading the SD in Windows and
restarting directly into the same macOS test EFI with the card inserted.
The startup/insertion comparisons have therefore not produced working access.

The [read-only observer](../sd-observer/README.md) and
[diagnostic profile](../../config/profiles/sd-observer-trial.json) provide the next
instrumentation step. The observer attaches to IOResources, leaving the SD
driver bound to the controller. It is restricted to x86_64/Darwin 25 and the
unique real 1217:8621/17AA:3803/class080501 device. Four startup snapshots read
whitelisted PCI registers and guarded existing-BAR SDHCI/O2 memory registers.
No register writes, power requests, card commands or payload reads are made.
Concurrent driver power changes remain a limit of any unowned snapshot.

Source commit `e91c8bef0a5abc38db2ce640783e6b3484f12d67` passed the Intel macOS build,
bundle checks and native Bash collector regression. The private config adds
exactly one Kernel/Add to the last legacy-driver trial, reverses to that
baseline, and passes OpenCore 1.0.8 ocvalidate. Exact recovery is included.
The resulting private package is `S540-SD-REGISTRI-240GB.zip`. These checks
verify preparation, not loading or SD functionality on the Lenovo. This is
diagnostic instrumentation; a functional reader correction remains pending.
