# Panel off at startup, Bluetooth, and Wi-Fi

The panel delay was resolved in the result reported on October 13, 2026: the black-screen wait fell **from about two minutes to zero** after the `-igfxblr`-only trial. Keep this configuration. Working Bluetooth headphones and HeliPort were reported on October 14, 2026. Keep the current Intel firmware, BlueToolFixup, and itlwm. Battery information and counters are preserved in [Battery and sleep](../status/battery-sleep.md). Further sleep checks, function keys, and equalization are deferred.

## Distinguish system startup from panel power-on

On October 13, 2026, the panel was reported as literally off for about two minutes before the Apple logo appeared. During that period, macOS already accepted the password and allowed login. This points the diagnosis toward panel power-on and backlighting; it does not document a complete system freeze.

Official WhateverGreen 1.7.1 code includes two corrections: BLR (`-igfxblr`) intercepts PWM register writes; BLT (`-igfxblt`) identifies and rewrites specific inlined sequences. The general guide recommends BLT for KBL/CFL from macOS 13.4, because calls had been inlined in those drivers.

In the previously collected Tahoe dump, the CFL framebuffer has UUID `7E294F0F-852E-3252-B54D-61D9A7BBE6B2`. The executable section is complete: 601466 bytes. The LEA sequence with displacement `0xFFF37DA7`, required by the BLT probe for CFL, is absent. Calls to a shared function for PWM registers `0xC8254` and `0xC8258` are present instead. The dump is mapped in memory and does not retain LINKEDIT, so function names cannot be resolved directly.

**Inference behind the trial:** for this specific driver, BLR alone was more consistent with the evidence than generic BLT. The trial requires the same loaded-driver UUID and Darwin 25.6.0. The subsequent laptop result confirms that the black screen disappeared in the reported trial; this is not a recommendation for every Tahoe version. BLR, BLT, and other graphics options are not combined.

The report preceding the trial confirms the same CFL UUID and already working Intel memory settings. In the latest boot segment, macOS shows `LoginwindowUIShown` about 31.3 seconds after the kernel, consistent with login being possible while the panel was still off. The report predates BLR and does not include it in the boot arguments; the result after rebooting was reported directly. No other unverified hardware changes are attributed to the trial.

## Collection from the desktop

`RACCOGLI-AVVIO-RETE.command` asks log show for the first five minutes of the current boot and reads driver UUIDs, Bluetooth/USB state, graphics, and network services. In the received report, the reader also returned earlier boots and later events: the requested interval was not respected. The cause has not been established. Analysis isolated the segment corresponding to kern.boottime; events later than five minutes are distinguished from the initial sequence. Another collection is not requested for the resolved panel issue. The two Bluetooth NVRAM variables are read separately; their absence does not prevent ZIP creation. Current device readings are taken after startup.

The command does not modify EFI, NVRAM, or drivers. The password is used only to read logs. It creates a private folder and `DIAGNOSI-AVVIO-RETE-XXXXXX.zip` on the Desktop for attachment to the chat. The report may contain hardware addresses and process messages: do not add it to the repository. It does not include the complete configuration, PlatformInfo, or the itlwm Info.plist containing credentials.

Extract the package into Downloads and run:

```sh
bash "$HOME/Downloads/S540-avvio-rete/RACCOGLI-AVVIO-RETE.command"
```

Recovery, reinstallation, and a new DEBUG driver are not required. Old OpenCore logs end before kernel events; the available unified logs describe trials preceding the memory correction and do not establish the cause of the current black screen.

## Panel trial

```sh
bash "$HOME/Downloads/S540-avvio-rete/TEST-SCHERMO-AVVIO.command"
```

The trial saves the current configuration privately in `EFI/OC/backup-schermo-avvio`, checks the driver actually loaded, and adds only `-igfxblr`. It preserves identity, the 19 MB/9 MB framebuffer memory settings, the audio layout, and SIP. Reboot from the same OpenCore HDD and compare the wait with the panel off. After rebooting, `sysctl -n kern.bootargs` must include `-igfxblr`: if it is absent, the patch was not tried in the kernel.

To undo it:

```sh
bash "$HOME/Downloads/S540-avvio-rete/ANNULLA-SCHERMO-AVVIO.command"
```

Restore verifies the backup and preserves the original bytes. **Undo this trial before making other EFI changes.** Audio v3 restore also protects the configuration and kext tree with hashes; its snapshots must not be rewritten to bypass those checks. Keeping the correction permanently requires coordinating the restore states.

## Bluetooth

IntelBTPatcher 2.4 remains disabled after the panic. Its source predates the HCI USB descriptor correction for Sequoia and later. A development build, version 2.5.0, of official source `a414375505fa3b014be32f8fca31b5bbfdf9f10f`, with declared Tahoe support, is available from Dortania; it is not a stable release.

BlueToolFixup 2.7.2 is already present. For Intel, the project requires NVRAM variables `bluetoothExternalDongleFailed` as Data `00` and `bluetoothInternalControllerInfo` as Data containing **fourteen zero bytes**, under Apple GUID `7C436110-AB2A-4BBB-A880-FE41995C9F82`. The previous count of thirteen bytes was incorrect: the official sequence contains twenty-eight hexadecimal digits. Although neither is set in the examined configuration, both variables are already correct in the report's active NVRAM. They are not rewritten.

The report shows Bluetooth State On, FirmwareLoaded=Yes, a connected transport, and loaded Intel firmware/BlueToolFixup; IntelBTPatcher remains disabled. In the latest boot, the stack completes initialization and starts scanning about 26.5 seconds after the kernel. Real BLE devices are detected later. Bluetooth headphone playback and the headset microphone are confirmed working. On October 14, 2026, disconnection and reconnection of both Bluetooth and Wi-Fi, and Wi-Fi network switching, were also confirmed. These results do not require a preventive driver update. THIRD_PARTY_DONGLE is a classification handled by BlueToolFixup and does not prove that an external dongle is present.

## Wi-Fi listed as Ethernet

This is the expected behavior of itlwm 2.3.0: it uses IOEthernetController. Renaming the service does not turn it into an IO80211 device. Networks can be managed through HeliPort or driver profiles; the project states that this representation does not reduce performance.

The desktop report confirms itlwm 2.3.0 and the Ethernet service on en0. To select networks from the menu bar, use [official HeliPort 1.5.0](https://github.com/OpenIntelWireless/HeliPort/releases/tag/v1.5.0), with the [release DMG](https://github.com/OpenIntelWireless/HeliPort/releases/download/v1.5.0/HeliPort.dmg). The app is the itlwm client: it does not change the classification in the macOS network settings. HeliPort was reported as working on October 14, 2026. This result is not a speed measurement or a Continuity feature check.

The official stable AirportItlwm 2.3.0 release has packages up to Sonoma, without a Tahoe asset. Approaches using older Airport drivers and restored Wi-Fi frameworks require broader system and SIP changes. Native Tahoe integration remains a separate task; the working driver is not replaced now solely to change the Ethernet label, and AirDrop is not promised.

## Connection performance baseline

Wireless disconnection/reconnection and network switching are already confirmed. The next performance observation uses the working itlwm/HeliPort connection without changing the driver or its Ethernet presentation. Close the laptop's downloads and streams, keep HeliPort connected to the usual network, and run Apple's built-in command:

```sh
networkQuality
```

Retain the summary's downlink/uplink capacity, responsiveness and idle latency when reported. This measures the full path through Wi-Fi, router, Internet service and remote endpoint. It is not an isolated radio/LAN throughput measurement; a low result alone does not identify an itlwm defect. Interpret it as a baseline before selecting any further comparison. Use the connected network path for the test; another active connection or VPN would change what is being measured.

No additional collector, archive, reboot or EFI change is required. Exclude network names, addresses, credentials and raw connection logs from public status updates. The [Apple instructions](https://support.apple.com/en-us/101942) describe the command and responsiveness metric; the [reference server project](https://github.com/network-quality/server) describes server-based testing.

### Recorded concurrent result: October 14, 2026

| Metric | Result |
|---|---|
| Downlink capacity | 15.751 Mb/s |
| Uplink capacity | 63.036 Mb/s |
| Responsiveness under load | Low: 1.023 seconds / 58 RPM |
| Idle latency | 41.376 ms / 1450 RPM |

The delay is elevated during the concurrent test, but no subscribed-line baseline or comparison client result is available. The measurement does not locate the bottleneck or establish an itlwm defect. Keep the current driver.

For one controlled diagnostic comparison, retain the same network and laptop position, stop the laptop's other transfers, and measure the directions sequentially:

```sh
networkQuality -s
```

Sequential mode separates upload and download responsiveness. A better result would show sensitivity to concurrent traffic in these observations, without isolating the responsible component. A poor sequential result would still need a separate reference before a driver or router change. [Apple's WWDC22 example](https://developer.apple.com/videos/play/wwdc2022/10078/) uses `-s`; the [responsiveness methodology](https://github.com/network-quality/draft-ietf-ippm-responsiveness/blob/main/draft-ietf-ippm-responsiveness.md#concurrent-vs-sequential-uplink-and-downlink) explains why sequential measurements help distinguish the affected direction.

### Recorded sequential comparison: October 14, 2026

| Metric | Result |
|---|---|
| Downlink capacity | 78.762 Mb/s |
| Uplink capacity | 81.610 Mb/s |
| Uplink responsiveness | Low: 684.383 ms / 87 RPM |
| Downlink responsiveness | Medium: 144.830 ms / 414 RPM |
| Idle latency | 33.658 ms / 1782 RPM |

The sequential trial reports higher capacity than the concurrent baseline, and the larger loaded delay is in the uplink. The difference shows sensitivity to test conditions in these observations; it does not isolate radio, driver, router, ISP or endpoint. No line-rate or independent-client reference is available. Keep itlwm/HeliPort unchanged. Further network investigation is deferred while the reported quiet-volume issue is addressed.

## Checks and limitations

The scripts are checked for Bash syntax and with simulated Linux fixtures. Collection checks cover the boot window, timeouts, errors, data filtering, and ZIP creation. Native collection was run on the laptop and the report analyzed. The panel trial eliminated the black screen in the reported result. Bluetooth headphone and HeliPort operation were subsequently confirmed; other checks remain open.

## Sources

- [WhateverGreen 1.7.1: backlight correction code](https://github.com/acidanthera/WhateverGreen/blob/1.7.1/WhateverGreen/kern_igfx_backlight.cpp).
- [WhateverGreen 1.7.1: Intel guide](https://github.com/acidanthera/WhateverGreen/blob/1.7.1/Manual/FAQ.IntelHD.en.md#fix-the-3-minute-black-screen-issue-on-kblcfl-platforms-running-macos-134-or-later).
- [Apple log manual](https://keith.github.io/xcode-man-pages/log.1.html).
- [OpenIntelWireless: differences between itlwm and AirportItlwm](https://openintelwireless.github.io/itlwm/FAQ.html).
- [BlueToolFixup: Intel NVRAM variables](https://github.com/acidanthera/BrcmPatchRAM#bluetoolfixupkext).
- [IntelBTPatcher HCI descriptor correction](https://github.com/OpenIntelWireless/IntelBluetoothFirmware/commit/50e971c524081a1d97a72794db2640aa0136e284).
- [IntelBluetoothFirmware development build a414375](https://github.com/dortania/build-repo/releases/tag/IntelBluetoothFirmware-a414375).
