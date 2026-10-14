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

## Working baseline and private backup

Tahoe and OpenCore now boot independently from the external Samsung 960 EVO after manual EFI transfer. The 240 GB HDD is retained as the recovery route. The [SSD boot guide](ssd-boot.md) records the result and the separate automatic helper's unresolved guard stop.

Preserve a private copy of the exact current Samsung EFI before any future graphics change. Identify its live partition and mount point rather than assuming a permanent disk number or using the earlier public release. The archive includes machine-specific identity and configuration; keep it outside the repository.

## HDMI investigation: October 14, 2026

HDMI produces no image in the current configuration. Leave the external monitor powered on, connected to the laptop's HDMI port and set to the intended input, then read:

```bash
system_profiler SPDisplaysDataType
```

The first question is whether macOS enumerates the external display, including its GPU grouping, resolution and online state. An absent monitor does not establish which GPU owns the physical connector.

The supplied private EFI uses the working Whiskey Lake identity and memory properties listed above, `-wegnoegpu` and `-igfxblr`, with no connector remapping. OEM SSDT9 enumerates `0x80087330` under NVIDIA `RP05.PXSX`; the ACPI display-type field is External Digital Monitor. Intel's output list is read from runtime OpRegion memory, and no captured VBT/OpRegion is available. NVIDIA routing is a hypothesis until the physical port is identified.

Lenovo's exact GTX model specification confirms HDMI 2.0 output capability but does not publish the GPU wiring. If a later Windows check is needed, the NVIDIA Control Panel's display-connection diagram can identify the GPU associated with the attached display. Inspecting enumeration and routing precedes any bus-ID, connector-type, pipe or graphics-policy change. The working Intel configuration and disabled optional NVIDIA power-off SSDT are retained.

## Remaining checks

1. Repeatable restart and shutdown with this same EFI, noting any panel delays.
2. Desktop use and a Metal workload without freezes or artifacts.
3. Panel recovery after sleep remains deferred. The brightness slider and direct F11/F12 work; remaining icon keys are tracked in the [roadmap](../status/roadmap.md#deferred-function-key-work).
4. Video decoding and external displays as separate checks.

The first powermetrics sample, lasting about one second, reported a CPU temperature of 50 °C. Two subsequent idle samples, each lasting five seconds, report 45–46 °C, estimated Intel package power of 0.80–0.95 W, and a system average frequency of about 0.95–0.97 GHz. IORegistry confirms that X86PlatformPlugin is active. Package power includes the CPU, iGPU, and system agent, excluding NVIDIA. Fan RPM is unavailable, but a later report stated that the fan had been quiet for some time. Temperature under load and dGPU power consumption remain to be checked. `2Slices on: 100%` describes time spent in the state with two active slices; 100% at 300 MHz is a frequency ratio. Neither value demonstrates 100% GPU utilization.

Other features remain in the [hardware roadmap](../status/roadmap.md). For another status check, these commands read information without changing the EFI:

```sh
sysctl -n kern.bootargs
system_profiler SPDisplaysDataType
```

## References

- [Lenovo: exact S540-15IWL GTX specification](https://psref.lenovo.com/syspool/Sys/PDF/IdeaPad/ideapad_S540_15IWL_GTX/ideapad_S540_15IWL_GTX_Spec.pdf).
- [ACPI: output enumeration and display-type fields](https://uefi.org/htmlspecs/ACPI_Spec_6_4_html/Apx_B_Video_Extensions/display-specific-methods.html).
- [WhateverGreen 1.7.1: framebuffer connectors](https://github.com/acidanthera/WhateverGreen/blob/1.7.1/Manual/FAQ.IntelHD.en.md).
- [NVIDIA: configuration visualizer and display connections](https://www.nvidia.com/content/Control-Panel-Help/vLatest/en-us/mergedProjects/3D%20Settings/To_use_PhysX_GPU_acceleration.htm).

- [WhateverGreen 1.7.1: Intel options, including -igfxvesa](https://github.com/acidanthera/WhateverGreen/blob/1.7.1/README.md#intel-hd-graphics)
- [Apple: System Information on Tahoe](https://support.apple.com/guide/system-information/welcome/11.0/mac/26)
- [Apple: creating a ZIP archive with ditto](https://developer.apple.com/documentation/xcode/packaging-mac-software-for-distribution)
- [Apple powermetrics manual](https://keith.github.io/xcode-man-pages/powermetrics.1.html): estimated power, frequencies, and instantaneous sensor readings.
- [Dortania: Intel graphics on Coffee Lake / Whiskey Lake laptops](https://dortania.github.io/OpenCore-Install-Guide/config-laptop.plist/coffee-lake.html#deviceproperties)
