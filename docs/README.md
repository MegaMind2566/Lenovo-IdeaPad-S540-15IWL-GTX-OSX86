# Documentation

Start with the [project README](../README.md) for the current state and scope. Documentation and runtime messages are written in English.

## Status

| Document | Purpose |
|---|---|
| [Hardware](status/hardware.md) | Hardware IDs and results observed on the laptop |
| [Roadmap](status/roadmap.md) | Open work, priorities and acceptance criteria |
| [NVIDIA validation](status/nvidia-validation.md) | Grouped checkpoints, separate native/target evidence and one future integrated target checkpoint |
| [Battery and sleep](status/battery-sleep.md) | Battery evidence, confirmed lid/idle sleep and selected peripheral recovery; long-duration coverage remains separate |
| [SD and fingerprint](status/sd-fingerprint.md) | Working internal SD result, retained initialization history and non-working fingerprint authentication |
| [CPU and thermals](status/cpu-thermal.md) | CPU response, incomplete load-temperature measurement and sensor follow-up |

## Current guides

| Guide | Purpose |
|---|---|
| [NVIDIA Resource Server and host services](../packages/nvidia-rm-services/README.md) | V9 confirmed: all 486 kernel startup checks, cleanup and 15 separate userspace firmware checks passed, with no warnings; completed checkpoint, no repeat requested |
| [Native NVIDIA integration validation](../packages/nvidia-global-rm/NATIVE-INTEGRATION-VALIDATION.json) | Current Intel macOS compiler and CPU evidence, including original global lifecycle/fault controls; kernel and GPU execution remain unconfirmed |
| [Original NVIDIA GSP integration](../packages/nvidia-gsp-bootstrap/README.md) | Development owner, transport and firmware preparation; original runtime remains gated, including cancellation and teardown within the macOS power deadline; no new laptop package |
| [Original NVIDIA Resource Server](../packages/nvidia-resource-server/README.md) | Selected NVOC/library subsystem, real client/resource/access/sharing paths and explicit adaptations; not full global RM startup |
| [Matching NVIDIA firmware assets](../packages/nvidia-firmware-assets/README.md) | Official release 615.78.08 GSP/UCODES byte hashes, parsing, provenance and full license; no device upload or execution |
| [NVIDIA hardware-transport preparation](../packages/nvidia-hardware-transport/README.md) | V8 confirmed in the Tahoe kernel: all 390 combined startup checks passed, cleanup complete and no warnings; untranslated host preparation is not device DMA verification |
| [Passive CPU sensors](../packages/cpu-sensors/README.md) | A continuous sensor reading with no CPU workload; complete temperature readings at idle and during desktop activity |
| [NVIDIA CPU support runtime](../packages/nvidia-nvport-runtime/README.md) | V7 confirmed in the Tahoe kernel: checked memory/PRNG startup, original utilities and vector/list consumers; all 258 combined checks passed, cleanup complete and no warnings |
| [CPU, temperature and power](../packages/cpu-thermal/README.md) | Grouped idle, short-load and recovery collector; sustained-cooling validation remains separate from the successful activity readings |
| [NVIDIA NVPort lifecycle](../packages/nvidia-nvport-lifecycle/README.md) | V6 tracked memory, spinlocks and allocator-owned mutex lifecycle confirmed in the Tahoe kernel: 72 lifecycle checks passed, including cleanup, with no warnings |
| [NVIDIA NVPort callers](../packages/nvidia-caller-integration/README.md) | Original allocation/mutex caller integration with bounded reserve and mutex backend; v5 kernel startup confirmed with 35 caller/reserve checks and 23 foundation checks |
| [NVIDIA Darwin OS adapter](../packages/nvidia-os-adapter/README.md) | CPU-only clock, RAM, atomics, allocation and thread mutexes; integrated v4 kernel startup check confirmed on the laptop; native/sanitizer checks and kernel packaging passed |
| [NVIDIA PCI transport](../packages/nvidia-transport/README.md) | Combined package delivery/reporting: v9 confirmed at 486 kernel startup checks; 485 native checks remain separate build evidence |
| [NVIDIA PCI inventory](../packages/nvidia-pci/README.md) | Native read-only inventory; active target PCI visibility is confirmed |
| [Intel graphics](guides/intel-graphics.md) | Acceleration and stability checks |
| [Boot and networking](guides/boot-network.md) | Backlight boot fix, native-menu AirportItlwm and Bluetooth; HeliPort retained as historical fallback |
| [Tahoe audio](guides/tahoe-audio.md) | Initial audio setup, volume fix and recovery |
| [Microphone v2](guides/microphone-fix.md) | S540 driver variant, verification and rollback |
| [Fine output volume](guides/volume-control.md) | Full analog DAC range with the working microphone correction retained |
| [USB mapping](guides/usb-mapping.md) | Mapped ports and outstanding tests |
| [Independent SSD boot](guides/ssd-boot.md) | Confirmed manual EFI transfer and Samsung boot; automatic helper on hold |
| [Boot disk maintenance](guides/boot-maintenance.md) | Separate maintenance procedure for the physical boot disk |
| [Function keys](guides/function-keys.md) | Keyboard icon actions, ordinary Fn function keys and brightness rollback; the brightness-adjustment regression in the NVIDIA-test EFI is deferred; the non-NVIDIA EFI works normally |
| [Bluetooth](guides/bluetooth.md) | The targeted patcher exclusion and its rollback |
| [Previous microphone diagnostics](guides/microphone-diagnostics.md) | Collector for VoodooHDA 3.6.8 before the microphone fix; it rejects the 3.6.9 variant |

## Reference

- [NVIDIA port assessment](reference/nvidia-port-assessment.md): pinned source, confirmed v9 Resource Server checkpoint, full-RM closure diagnostics and remaining GPU/GSP boundaries.
- [Original-entry power deadline](../packages/nvidia-gsp-bootstrap/platform/POWER-DEADLINE-AUDIT.md): pinned NVIDIA wait budgets and Apple acknowledgement behavior; a completed child lease does not prove safe original RM entry during normal sleep.
- [ACPI analysis](reference/acpi-analysis.md), [ACPI patch review](reference/acpi-patch-review.md) and [initial EFI delivery review](reference/efi-review.md).
- [External disk installation](reference/installation.md) and [initial EFI instructions](reference/first-boot.md), written before the working configuration.
- [Repository layout](reference/repository-layout.md), including the distinction between source modules and generated ZIP packages.

## Previous investigations

Graphics experiments, Intel traces and Recovery log collectors are preserved in the [archive](../archive/README.md), together with their sources, asset locks and licenses. The [NVIDIA visibility helper](../packages/nvidia-visibility/README.md) is superseded for the reached milestone: its V1 automatic locator stopped at `Mounted`, and the subsequent manual path produced an active target PCI service.

## Current release and continuing work

**[v0.3.0](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/releases/tag/v0.3.0)** is the current internal non-NVIDIA baseline. The project remains in development. [Release notes](releases/v0.3.0/RELEASE-NOTES.md), [installation](releases/v0.3.0/INSTALL.md) and [provenance](releases/v0.3.0/SOURCE-PROVENANCE.md) explain the working and unsupported hardware, identity personalization and payload boundaries.

The package contains **EFI/OC only**, with a rEFInd config example. Microsoft boot files, EFI/BOOT and the rEFInd executable are not redistributed. Audio and S540 Tasti are separately installed macOS companions; their ZIPs and checksums are available with the release. SD reading, session insertion, mount/unmount and availability after sleep are user-confirmed on the known 8 GB FAT32 card.

F8 camera disablement and fingerprint authentication remain non-working with work paused/stopped. F6/F10 completion and external-display support retain their stated scope. Fan RPM telemetry is unavailable in the current configuration, while CPU temperature readings work; physical fan failure is not established. NVIDIA is disabled in the official EFI; its separate experimental records remain available and do not establish graphics acceleration. Missing extended measurements do not reopen confirmed checks automatically.

The earlier [v0.2.0](releases/v0.2.0/RELEASE-NOTES.md), [v0.1.0](releases/v0.1.0.md), and `config/efi/current` are historical snapshots, not the new installation procedure. Feature guides retain their dated diagnostics and rollback information.
