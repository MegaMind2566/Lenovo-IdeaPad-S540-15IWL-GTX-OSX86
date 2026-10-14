# Documentation

Start with the [project README](../README.md) for the current state and scope. Detailed technical guides are currently written in Italian.

## Status

| Document | Purpose |
|---|---|
| [Hardware](status/HARDWARE.md) | Hardware IDs and results observed on the laptop |
| [Roadmap](status/ROADMAP.md) | Open work, priorities and acceptance criteria |
| [Battery and sleep](status/BATTERIA-SOSPENSIONE.md) | Recorded samples and deferred checks |

## Current guides

| Guide | Purpose |
|---|---|
| [Intel graphics](guides/GRAFICA-INTEL.md) | Acceleration and stability checks |
| [Boot and networking](guides/AVVIO-RETE.md) | Backlight boot fix, HeliPort and Bluetooth |
| [Tahoe audio](guides/AUDIO-TAHOE.md) | Initial audio setup, volume fix and recovery |
| [Microphone v2](guides/MICROFONO-FIX.md) | S540 driver variant, verification and rollback |
| [USB mapping](guides/MAPPATURA-USB.md) | Mapped ports and outstanding tests |
| [Boot disk maintenance](guides/RIORDINO-AVVIO.md) | Separate maintenance procedure for the physical boot disk |
| [Bluetooth](guides/TEST-BLUETOOTH.md) | The targeted patcher exclusion and its rollback |
| [Previous microphone diagnostics](guides/MICROFONO.md) | Collector for VoodooHDA 3.6.8 before the microphone fix; it rejects the 3.6.9 variant |

## Reference

- [ACPI analysis](reference/ANALISI-ACPI.md), [ACPI patch review](reference/VERIFICA-PATCH-ACPI.md) and [initial EFI delivery review](reference/VERIFICA-EFI.md).
- [External disk installation](reference/INSTALLAZIONE.md) and [initial EFI instructions](reference/PRIMO-AVVIO.md), written before the working configuration.
- [Repository layout](reference/REPOSITORY-LAYOUT.md), including the distinction between source modules and generated ZIP packages.

## Previous investigations

Graphics experiments, Intel traces and Recovery log collectors are preserved in the [archive](../archive/README.md), together with their sources, asset locks and licenses.

## Release preparation

[v0.1.0 release notes](releases/v0.1.0.md) describe the working features and remaining limitations. Publication is pending the current EFI snapshot.
