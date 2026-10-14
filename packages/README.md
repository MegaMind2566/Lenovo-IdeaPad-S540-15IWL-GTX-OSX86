# Runtime packages

Source files are grouped by feature. Each group keeps its launchers at the top
level and its runtime helpers in `tools/`, matching the layout of the distributed
ZIP packages. Builders and regression checks are kept separately.

| Package | Purpose | Guide |
| --- | --- | --- |
| [microphone](microphone) | Install, verify and reverse the scoped ALC257 input-gain correction. Includes the shared V3 audio ownership check. | [Microphone correction](../docs/guides/MICROFONO-FIX.md) |
| [audio](audio) | Prepare, install and reverse the Tahoe VoodooHDA audio setup and its speaker-volume correction. | [Audio](../docs/guides/AUDIO-TAHOE.md) |
| [backlight](backlight) | Apply or reverse the guarded `-igfxblr` boot-backlight correction. | [Boot and network](../docs/guides/AVVIO-RETE.md) |
| [boot-network](boot-network) | Collect startup, graphics, Bluetooth and network reports without changing their configuration. | [Boot and network](../docs/guides/AVVIO-RETE.md) |
| [hardware-inventory](hardware-inventory) | Collect Windows hardware and ACPI information. | [Hardware](../docs/status/HARDWARE.md) |
| [boot-maintenance](boot-maintenance) | Archive recognized old trial files from the OpenCore disk with copy verification. | [Boot-disk maintenance](../docs/guides/RIORDINO-AVVIO.md) |
| [bluetooth](bluetooth) | Exclude IntelBTPatcher in an existing EFI and restore the exact previous configuration. | [Bluetooth](../docs/guides/TEST-BLUETOOTH.md) |
| [recovery](recovery) | Download the Apple recovery image and configure the local `itlwm` recovery network profile in an assembled EFI package. | [First installation](../docs/reference/PRIMO-AVVIO.md) |
| [microphone-diagnostics](microphone-diagnostics) | Read the pre-correction VoodooHDA 3.6.8 mixer state. The native reader source is in `src/`; the built package includes its executable and a copy of the shared ownership check. | [Microphone diagnostics](../docs/guides/MICROFONO.md) |

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
