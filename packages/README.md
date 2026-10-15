# Packages and development components

Sources are grouped by feature. Installable packages retain their launchers and
runtime helpers together. CPU-only NVIDIA components are combined in the
experimental transport package for targeted laptop milestones; their other
checks run in GitHub. Builders and regression checks are kept separately.

| Package | Purpose | Guide |
| --- | --- | --- |
| [nvidia-nvport-runtime](nvidia-nvport-runtime) | V7 combined CPU support runtime: original strings/PRNG, checked initialization/shutdown, real vector/list consumers and an explicit vector cleanup correction. Native CI and compiled package verification passed: 258 combined startup checks, container/failure coverage and strict reporting. One combined laptop checkpoint remains; v6 is the confirmed kernel baseline. | [CPU support runtime](nvidia-nvport-runtime/README.md) |
| [nvidia-nvport-lifecycle](nvidia-nvport-lifecycle) | V6 tracked memory, real spinlocks, allocator-owned mutex lifecycle and resource accounting confirmed in the Tahoe kernel: all 72 lifecycle checks passed, including cleanup, with no warnings. | [NVPort lifecycle](nvidia-nvport-lifecycle/README.md) |
| [nvidia-caller-integration](nvidia-caller-integration) | Three original allocation callers and five mutex callers with bounded reserve and mutex backends. The v5 transport passed native CI and its laptop kernel startup: 35 caller/reserve checks and 23 foundation checks passed. | [NVPort callers](nvidia-caller-integration/README.md) |
| [nvidia-os-adapter](nvidia-os-adapter) | CPU-only clock, RAM, atomics, allocation and thread-mutex foundations. Integrated v4 kernel startup check confirmed on the laptop; native/sanitizer checks and kernel packaging passed. Concurrent kernel execution and full NVIDIA caller compatibility remain separate. | [OS adapter](nvidia-os-adapter/README.md) |
| [nvidia-transport](nvidia-transport) | V6 confirmed on the laptop: all 130 kernel startup checks passed (72 lifecycle, 35 caller/reserve, 23 foundations), cleanup complete and no warnings. Two-read TU117 identification retained. No HAL/RM, firmware or acceleration. | [PCI transport](nvidia-transport/README.md) |
| [nvidia-visibility](nvidia-visibility) | Superseded for the reached visibility milestone. V1 automatic locator stopped at `Mounted`; subsequent manual removal of the disable argument produced a visible PCI service. | [Retained visibility experiment](nvidia-visibility/README.md) |
| [nvidia-pci](nvidia-pci) | Read published PCI metadata; laptop visibility is confirmed for the exact target. No hardware access or GPU initialization. | [NVIDIA PCI inventory](nvidia-pci/README.md) |
| [ssd-boot](ssd-boot) | Automatic transfer helper on hold after a mounted-target guard stop. Manual transfer and independent Samsung boot are confirmed. | [Independent SSD boot](../docs/guides/ssd-boot.md) |
| [cpu-sensors](cpu-sensors) | Read continuous, filtered sensor telemetry and loaded SMC driver versions without a CPU workload. | [Passive sensor check](cpu-sensors/README.md) |
| [cpu-thermal](cpu-thermal) | Collect bounded idle, CPU-load and recovery telemetry with owned-worker cleanup. Continuous temperature readings during desktop activity work; sustained cooling remains separate. | [CPU check](cpu-thermal/README.md) |
| [microphone](microphone) | Install, verify and reverse the scoped ALC257 input-gain correction. Includes the shared V3 audio ownership check. | [Microphone correction](../docs/guides/microphone-fix.md) |
| [audio-volume](audio-volume) | Restore the full analog DAC range while retaining the 3.6.9 microphone correction and an exact private rollback copy. | [Fine output volume](../docs/guides/volume-control.md) |
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
