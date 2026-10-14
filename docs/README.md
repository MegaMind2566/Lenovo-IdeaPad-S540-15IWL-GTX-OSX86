# Documentation

Start with the [project README](../README.md) for the current state and scope. Detailed technical guides are currently written in Italian.

## Status

| Document | Purpose |
|---|---|
| [Hardware](status/hardware.md) | Hardware IDs and results observed on the laptop |
| [Roadmap](status/roadmap.md) | Open work, priorities and acceptance criteria |
| [Battery and sleep](status/battery-sleep.md) | Recorded samples and deferred checks |

## Current guides

| Guide | Purpose |
|---|---|
| [Intel graphics](guides/intel-graphics.md) | Acceleration and stability checks |
| [Boot and networking](guides/boot-network.md) | Backlight boot fix, HeliPort and Bluetooth |
| [Tahoe audio](guides/tahoe-audio.md) | Initial audio setup, volume fix and recovery |
| [Microphone v2](guides/microphone-fix.md) | S540 driver variant, verification and rollback |
| [USB mapping](guides/usb-mapping.md) | Mapped ports and outstanding tests |
| [Boot disk maintenance](guides/boot-maintenance.md) | Separate maintenance procedure for the physical boot disk |
| [Bluetooth](guides/bluetooth.md) | The targeted patcher exclusion and its rollback |
| [Previous microphone diagnostics](guides/microphone-diagnostics.md) | Collector for VoodooHDA 3.6.8 before the microphone fix; it rejects the 3.6.9 variant |

## Reference

- [ACPI analysis](reference/acpi-analysis.md), [ACPI patch review](reference/acpi-patch-review.md) and [initial EFI delivery review](reference/efi-review.md).
- [External disk installation](reference/installation.md) and [initial EFI instructions](reference/first-boot.md), written before the working configuration.
- [Repository layout](reference/repository-layout.md), including the distinction between source modules and generated ZIP packages.

## Previous investigations

Graphics experiments, Intel traces and Recovery log collectors are preserved in the [archive](../archive/README.md), together with their sources, asset locks and licenses.

## Release preparation

[v0.1.0 release notes](releases/v0.1.0.md) describe the working features and remaining limitations. Publication is pending the current EFI snapshot.
