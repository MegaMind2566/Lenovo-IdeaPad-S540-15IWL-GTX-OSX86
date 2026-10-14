# USB mapping from Windows

This step identifies physical ports before preparing the installer. The map is also needed for the webcam, Bluetooth, and the external Samsung 960 EVO connected over USB-C.

1. Download [Windows.exe from the official USBToolBox 0.2 release](https://github.com/USBToolBox/tool/releases/download/0.2/Windows.exe) and save it in a regular folder, such as USBToolBox on the Desktop.
2. Run Windows.exe. Select **Discover Ports** from the menu.
3. Connect a USB 3 flash drive or disk to every external port, one port at a time. Wait for it to appear in the list before moving to the next port. Include USB-C if available and, where possible, both connector orientations.
4. Return to the menu and select **Select Ports and Build Kext**. Keep the detected ports, including internal webcam and Bluetooth ports; internal ports normally use type **255**.
5. Press **K** to create the map. Compress the generated **UTBMap.kext** folder into a ZIP and attach it to the project chat.

For USB-C, also check the Samsung 960 EVO using the intended enclosure and cable. Confirm that it appears in the list in both connector orientations. USBToolBox does not initialize or format the disk.

On Windows, USBToolBox detects companion ports: a USB 3 device normally also identifies the corresponding USB 2 port. If a pair is not detected, repeat the check on that port with a USB 2 device.

If the program reports an error or the port selection is unclear, provide a screenshot of the selection menu before creating the map. No BIOS changes are required.

The map must respect the macOS limit of 15 ports per controller. This limit applies to logical ports, so one USB 3 connector can count as two ports. The selection will be checked before integration into OpenCore.

Source: [USBToolBox — official documentation](https://github.com/USBToolBox/tool).

## Current macOS link-speed check

Independent Samsung boot is confirmed after manual EFI transfer. The original Windows mapping recorded the RTL9210 bridge at USB 2 speed; this does not establish its current macOS connection speed.

With Tahoe running from the SSD in its current connection, read the USB device report:

```bash
system_profiler SPUSBHostDataType
```

Review the enclosure's own **Link Speed** or **Speed** entry, together with its position in the USB tree. A controller's advertised maximum is not the enclosure's negotiated link speed, and neither is a measured storage transfer rate. The October 14 reports confirm a 5 Gb/s RTL9210 link in both laptop-side USB-C connector orientations.

The current system SSD must remain connected while macOS is running. The completed USB-C reversal check and any later alternate-port check require shutdown before moving its cable, followed by another boot and device-speed reading. Sustained storage reliability remains a separate usage check.

The report-type selection for Tahoe is also implemented in the primary source of [usbi](https://gist.github.com/kaushikgopal/7e1555569cd5bb3138cb5ca67bb7a4ae). No third-party utility is required for this read-only check.

## Observed macOS result: October 14, 2026

| Item | Result |
|---|---|
| Enclosure | ULT-Best, Realtek RTL9210, USB `0BDA:9210` |
| Device link speed | **5 Gb/s — SuperSpeed in both USB-C orientations** |
| Host controller | AppleIntelCNLUSBXHCI, PCI `8086:9DED` |
| Physical connector/orientation | USB-C; the follow-up explicitly reports the laptop-side connector reversed |
| Storage throughput and sustained reliability | Still unmeasured |

The enclosure's USB serial is not retained. Its reported 4.48 W is allocated USB power, not measured power consumption. A Location ID does not by itself establish the physical map entry.

The USB-C reversal check is complete: after the preceding 5 Gb/s report, the follow-up explicitly reports the Samsung on reversed USB-C and retains 5 Gb/s. The result applies to the current SSD, enclosure and cable. Remaining USB-A ports can be checked with another USB 3 device or after shutting down before moving the system SSD.

## Remaining USB-A check

Keep the running Samsung connected to USB-C. Use the separate 240 GB HDD or another USB storage device to check the two USB-A connectors, one at a time:

1. Confirm the separate drive appears in Finder and open an existing file from it.
2. Run `system_profiler SPUSBHostDataType`. Record only that device's name, negotiated Link Speed and physical USB-A connector.
3. Eject that separate drive in Finder before moving it to the other USB-A connector; repeat the same check there.

Do not eject or move the Samsung system disk. This check needs no formatting, writes, EFI changes or benchmark. The HDD's USB generation and cable capability are not yet established: a 480 Mb/s result alone does not show a faulty USB-A port. SuperSpeed can be established with a device/cable known to support it. A successful file read confirms basic operation, not sustained storage reliability.

## Received and verified map

The supplied `UTBMap.kext` matches the 9 ports selected in `usb.json` on the `XHC` controller, PCI `8086:9DED`. The original plist is preserved in `usb/UTBMap.kext`; the summary without serial numbers or Windows paths is in `usb/ports.json`. The raw JSON is not added to the repository.

| Map name | Controller port | Type | Use |
|---|---:|---:|---|
| HS01 | 1 | 9 | USB-C USB 2 |
| HS02 | 2 | 255 | Internal fingerprint reader |
| HS03 | 4 | 255 | Internal webcam |
| HS04 | 6 | 3 | USB-A USB 2 |
| HS05 | 7 | 3 | USB-A USB 2 |
| HS06 | 10 | 255 | Internal Bluetooth |
| SS01 | 13 | 3 | USB-A SuperSpeed |
| SS02 | 14 | 3 | USB-A SuperSpeed |
| SS03 | 15 | 9 | USB-C SuperSpeed |

Here, `HS03` represents physical port 4: the names are labels generated by the program; the binary `port` field contains the actual number. Internal devices are marked `255`, USB-A ports `3`, and USB-C `9` (with a switch).

The original Windows discovery observed the RTL9210 enclosure at USB 2 speed on port 1, with SuperSpeed port 15 selected but no recorded device. The later macOS reports above confirm 5 Gb/s in both USB-C orientations. They do not by themselves identify a particular logical map entry or validate remaining USB-A ports.
