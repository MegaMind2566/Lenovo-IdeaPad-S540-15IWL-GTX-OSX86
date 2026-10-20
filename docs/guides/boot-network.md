# Boot, native Wi-Fi and Bluetooth

Updated on **20 October 2026**. The official EFI on the external Samsung 960 EVO has working native Wi-Fi and the hardware-name corrections. The user has confirmed the installed result; the separate 240 GB EFI remains a test/recovery configuration.

## Current working configuration

| Area | Installed state and result |
|---|---|
| Native Wi-Fi | Intel Wireless-AC 9560 with AirportItlwm 2.4.0, laobamac source `738d4c6`; native macOS menu and Wi-Fi service working |
| Previous Wi-Fi driver | `itlwm.kext` disabled; the earlier HeliPort/Ethernet presentation is historical |
| Recovery | User-confirmed native connection and operation after restart/sleep |
| Bluetooth | IntelBluetoothFirmware 2.4.0 and BlueToolFixup 2.7.2; IntelBTPatcher intentionally disabled |
| Bluetooth use | Headphone playback, headset microphone, disconnect and reconnect confirmed by the user |
| Panel startup | The `-igfxblr` correction is retained; the former approximately two-minute blackout was resolved |
| Lid | Closing sleeps and opening resumes, confirmed on 20 October; see [Battery and sleep](../status/battery-sleep.md) |

The native-driver result does not establish AirDrop, Continuity or a new throughput measurement. Renaming the old Ethernet service was a label correction; the current native integration comes from AirportItlwm. No wireless driver replacement or preventive Bluetooth update is requested.

## Panel correction provenance

The original 13 October observation distinguished a panel that was off from a frozen system: macOS accepted login while the screen remained black. For the captured CFL framebuffer and Darwin 25.6.0, the BLT pattern was absent and the shared PWM-write path was present. That supported the specific `-igfxblr`-only trial.

The subsequent user result reduced the black-screen wait from about two minutes to zero. Intel framebuffer memory settings were preserved. This is a result for the examined driver/configuration, not a general prescription for every Tahoe build. The earlier startup collector and panel-trial scripts are historical tools; no repeat collection or trial is requested for this resolved issue.

## Bluetooth state

The 20 October report confirms the Intel USB device `8087:0AAA`, a running controller and loaded firmware/BlueToolFixup. Its internal USB port is type 255 in the applied map. The profiler's `THIRD_PARTY_DONGLE` and Apple vendor labels come from the software stack; they are not evidence of a physical external dongle or a new failure.

The established working NVRAM and driver configuration is retained. The earlier IntelBTPatcher panic and later upstream fixes remain diagnostic history, not a reason to replace the working stack. Real headphone and microphone use is already user-confirmed.

## Historical itlwm performance observations

These measurements were taken on **14 October with itlwm/HeliPort**, before the current native AirportItlwm integration. They must not be presented as current native-driver performance.

Disconnection/reconnection and network switching were also confirmed with that earlier stack. Those historical checks are separate from the current native-driver result.

| Metric | Concurrent `networkQuality` | Sequential `networkQuality -s` |
|---|---:|---:|
| Downlink capacity | 15.751 Mb/s | 78.762 Mb/s |
| Uplink capacity | 63.036 Mb/s | 81.610 Mb/s |
| Loaded responsiveness | Low: 1.023 s / 58 RPM | Uplink Low: 684.383 ms / 87 RPM; downlink Medium: 144.830 ms / 414 RPM |
| Idle latency | 41.376 ms / 1450 RPM | 33.658 ms / 1782 RPM |

These are end-to-end Internet-path observations, not isolated Wi-Fi/LAN throughput. They do not identify a driver, router or ISP fault. No new performance test is required to record the current working state.

## Scope and privacy

Native Wi-Fi and hardware names are installed and confirmed. The subsequent config removing the residual NVMe block has been delivered, but its reboot is not yet explicitly confirmed; [Hardware status](../status/hardware.md) keeps that distinction. SD and NVIDIA work are paused.

Private network names, addresses, credentials, complete configurations and raw diagnostic archives are not repository content.

## Sources

- [WhateverGreen 1.7.1 backlight correction](https://github.com/acidanthera/WhateverGreen/blob/1.7.1/WhateverGreen/kern_igfx_backlight.cpp).
- [OpenIntelWireless: itlwm and AirportItlwm differences](https://openintelwireless.github.io/itlwm/FAQ.html).
- [BlueToolFixup Intel NVRAM requirements](https://github.com/acidanthera/BrcmPatchRAM#bluetoolfixupkext).
- [Apple networkQuality explanation](https://support.apple.com/en-us/101942).
