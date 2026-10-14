# Runtime packages

Source files are grouped by feature. Each group keeps its launchers at the top
level and its runtime helpers in `tools/`, matching the layout of the distributed
ZIP packages. Builders and regression checks are kept separately.

| Package | Purpose | Guide |
| --- | --- | --- |
| [ssd-boot](ssd-boot) | Automatic transfer helper on hold after a mounted-target guard stop. Manual transfer and independent Samsung boot are confirmed. | [Independent SSD boot](../docs/guides/ssd-boot.md) |
| [cpu-sensors](cpu-sensors) | Read continuous, filtered sensor telemetry and loaded SMC driver versions without a CPU workload. | [Passive sensor check](cpu-sensors/README.md) |
| [cpu-thermal](cpu-thermal) | Collect bounded idle, CPU-load and recovery telemetry with owned-worker cleanup. Further load checks are on hold pending sensor reliability. | [CPU check](cpu-thermal/README.md) |
| [microphone](microphone) | Install, verify and reverse the scoped ALC257 input-gain correction. Includes the shared V3 audio ownership check. | [Microphone correction](../docs/guides/microphone-fix.md) |
| [audio](audio) | Prepare, install and reverse the Tahoe VoodooHDA audio setup and its speaker-volume correction. | [Audio](../docs/guides/tahoe-audio.md) |
| [backlight](backlight) | Apply or reverse the guarded `-igfxblr` boot-backlight correction. | [Boot and network](../docs/guides/boot-network.md) |
| [boot-network](boot-network) | Collect startup, graphics, Bluetooth and network reports without changing their configuration. | [Boot and network](../docs/guides/boot-network.md) |
| [hardware-inventory](hardware-inventory) | Collect Windows hardware and ACPI information. | [Hardware](../docs/status/hardware.md) |
| [boot-maintenance](boot-maintenance) | Archive recognized old trial files from the OpenCore disk with copy verification. | [Boot-disk maintenance](../docs/guides/boot-maintenance.md) |
| [bluetooth](bluetooth) | Exclude IntelBTPatcher in an existing EFI and restore the exact previous configuration. | [Bluetooth](../docs/guides/bluetooth.md) |
| [recovery](recovery) | Download the Apple recovery image and configure the local `itlwm` recovery network profile in an assembled EFI package. | [First installation](../docs/reference/first-boot.md) |
| [microphone-diagnostics](microphone-diagnostics) | Read the pre-correction VoodooHDA 3.6.8 mixer state. The native reader source is in `src/`; the built package includes its executable and a copy of the shared ownership check. | [Microphone diagnostics](../docs/guides/microphone-diagnostics.md) |

Use the complete built package for audio installation, microphone correction or
microphone diagnostics. The repository sources do not contain the compiled,
locked driver payload or reader binary required by those launchers. The recovery
launchers also expect the generated `tools/macrecovery/` files and an assembled
EFI beside them.

Keep the internal package layout when extracting a ZIP. The guards and rollback
state belong to the package and driver version that created them; follow the
corresponding guide before switching packages or reversing a later correction.
Microphone diagnostics currently supports the pre-correction 3.6.8 driver.

Historical first-boot experiments are kept in [archive](../archive/README.md).

The [EFI](efi/README.md) package describes the current release.

Available keyboard companions (remaining icon-key investigation is deferred):

- [Function-key snapshots](function-keys/README.md): device and brightness observations.
- [Function-key events](function-key-events/README.md): passive direct/Fn session-event observation.
- [Fn shortcut setup](function-keys-setup/README.md): reversible removal of four conflicting macOS function-key shortcuts.
- [Driver scan-code collection](function-key-scancodes/README.md): bounded runtime logging for the verified VoodooPS2Keyboard RELEASE binary, with automatic restoration.

