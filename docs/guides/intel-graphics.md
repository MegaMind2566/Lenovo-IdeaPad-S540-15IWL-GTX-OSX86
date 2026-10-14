# Intel graphics verification after installation

## Device result: October 13, 2026

With the [framebuffer memory correction](../../archive/first-boot/docs/intel-memory-test.md), Tahoe reached initial setup and the desktop on the external Samsung 960 EVO. The subsequent powermetrics sample identifies IntelAccelerator and boot arguments without `-igfxvesa` or `-x`. The system_profiler report confirms:

| Item | Result |
|---|---|
| Exposed GPU | Intel UHD Graphics 620 |
| Exposed device ID | `0x3ea5`, consistent with the Whiskey Lake configuration |
| Graphics memory | Dynamic and shared, up to 1536 MB |
| Metal support | Metal 3 |
| Internal panel | Online, primary, 1920×1080 |
| Framebuffer depth | 24-bit ARGB8888 |

These results confirm a working desktop with the Intel accelerator driver loaded and Metal exposed. They do not complete checks for stability, Metal workloads, video decoding, brightness, sleep, or external displays. The physical PCI identifier detected by Windows remains `8086:3EA0`; `0x3ea5` is the identifier exposed by the macOS configuration.

The applied configuration retains `AAPL,ig-platform-id=0900A53E` and `device-id=A53E0000`, with `framebuffer-patch-enable=01000000`, `framebuffer-stolenmem=00003001`, and `framebuffer-fbmem=00009000`. All three properties are four-byte Data values. No additional patches were added after the desktop appeared.

Before initial setup, the panel was temporarily black, then the interface appeared without another EFI change. That first delay alone did not justify a backlight patch.

A later report described the panel remaining off for about two minutes at startup, before the Apple logo, while macOS already accepted the password and completed login. A review of the WEG code and Tahoe driver dump identified a [BLR-only trial](boot-network.md), restricted to the same framebuffer UUID and protected by a reversible backup. After rebooting with `-igfxblr`, the result reported on October 13, 2026 was **black screen resolved, zero delay**. Keep the working correction. The 19 MB/9 MB memory settings and Intel identity remain unchanged; no other backlight patches are added.

## Preserve the working EFI

Before further checks, create a private copy of the entire current EFI folder on the OpenCore HDD, including the framebuffer memory correction backups. With the boot volume mounted as `240 GB`, run this in Terminal:

```sh
ditto -c -k --keepParent "/Volumes/240 GB/EFI" "$HOME/Desktop/EFI-Tahoe-Metal3-$(date +%Y%m%d-%H%M%S).zip"
```

The command creates an archive on the Desktop and must be run on the laptop. If the volume is mounted under a different name, locate the EFI folder in Finder first. The archive contains personal configuration and a Wi-Fi profile: keep it private and do not add it to the repository. The EFI remains on the HDD until booting from the Samsung is prepared and checked separately.

## Remaining checks

1. Repeatable restart and shutdown with this same EFI, noting any panel delays.
2. Desktop use and a Metal workload without freezes or artifacts.
3. Panel recovery after sleep. Brightness control from the macOS slider is already reported as working. F11/F12 do not work and are deferred to the complete function-key task in the [roadmap](../status/roadmap.md#tasti-funzione-lavoro-rinviato-in-blocco).
4. Video decoding and external displays as separate checks.

The first powermetrics sample, lasting about one second, reported a CPU temperature of 50 °C. Two subsequent idle samples, each lasting five seconds, report 45–46 °C, estimated Intel package power of 0.80–0.95 W, and a system average frequency of about 0.95–0.97 GHz. IORegistry confirms that X86PlatformPlugin is active. Package power includes the CPU, iGPU, and system agent, excluding NVIDIA. Fan RPM is unavailable, but a later report stated that the fan had been quiet for some time. Temperature under load and dGPU power consumption remain to be checked. `2Slices on: 100%` describes time spent in the state with two active slices; 100% at 300 MHz is a frequency ratio. Neither value demonstrates 100% GPU utilization.

Other features remain in the [hardware roadmap](../status/roadmap.md). For another status check, these commands read information without changing the EFI:

```sh
sysctl -n kern.bootargs
system_profiler SPDisplaysDataType
```

## References

- [WhateverGreen 1.7.1: Intel options, including -igfxvesa](https://github.com/acidanthera/WhateverGreen/blob/1.7.1/README.md#intel-hd-graphics)
- [Apple: System Information on Tahoe](https://support.apple.com/guide/system-information/welcome/11.0/mac/26)
- [Apple: creating a ZIP archive with ditto](https://developer.apple.com/documentation/xcode/packaging-mac-software-for-distribution)
- [Apple powermetrics manual](https://keith.github.io/xcode-man-pages/powermetrics.1.html): estimated power, frequencies, and instantaneous sensor readings.
- [Dortania: Intel graphics on Coffee Lake / Whiskey Lake laptops](https://dortania.github.io/OpenCore-Install-Guide/config-laptop.plist/coffee-lake.html#deviceproperties)
