# NVIDIA PCI attachment prototype

This is the first kernel attachment experiment for the S540 NVIDIA port. The laptop now publishes its GTX 1650 Max-Q (`10DE:1F91`, subsystem `17AA:3806`) in IOService with `-wegnoegpu` absent. This package checks the next boundary: an IOKit service attaching to that exact PCI device, reading fixed configuration registers and publishing the already-assigned BAR resource descriptors.

**Status:** implementation available for an experimental boot; laptop attachment is not yet confirmed. This prototype provides no graphics acceleration, GPU command submission, display output or GSP initialization. It is independent of NVIDIA's Linux resource manager, which has not been integrated yet.

## Boot the experiment

Use the complete built **S540-nvidia-transport-v1.zip**. Keep the working Samsung EFI available and make the following changes only to the separate EFI on the 240 GB boot HDD.

1. Copy **S540NvidiaPCIProbe.kext** into the test EFI's `EFI/OC/Kexts/` directory.
2. Add the dictionary in **Kernel-Add-entry.plist** as one entry in the test `config.plist` under `Kernel → Add`. This file is an entry fragment, not a replacement configuration.
3. Keep `-wegnoegpu` absent and `SSDT-DGPU-OFF.aml` disabled. Preserve `-igfxblr` and the working Intel settings.
4. Validate the edited configuration with the matching OpenCore validator, then boot the HDD from the firmware's one-time boot menu and select the existing Tahoe installation.

The entry uses `Arch=x86_64`, `BundlePath=S540NvidiaPCIProbe.kext`, `ExecutablePath=Contents/MacOS/S540NvidiaPCIProbe`, `PlistPath=Contents/Info.plist`, `Enabled=true`, `MinKernel=25.0.0` and `MaxKernel=25.99.99`.

No system installation, administrator command, SIP change, NVRAM reset or kernel collection rebuild is part of this procedure.

## Collect the result

After the experimental boot, extract the package into Downloads and run:

```bash
bash "$HOME/Downloads/S540-nvidia-transport-v1/CHECK-TRANSPORT.command"
```

The native Intel reporter verifies its packaged executable, reads only the probe's bounded IORegistry snapshot and verifies the actual parent device identity. It saves **nvidia-transport.json** in a new private **NVIDIA-TRANSPORT…** folder on the Desktop. Share that JSON to choose the next implementation step. No developer tools or administrator password are required.

An `attached` result establishes the kernel attachment and configuration-read milestone. `not_attached` means the probe service was not found; it does not establish why loading or matching failed. Invalid snapshots or unexpected providers are reported as errors. BAR descriptors are resource metadata; their presence does not prove that GPU register access, VRAM, power transitions or firmware initialization work.

## Return to the working configuration

Boot the unchanged Samsung EFI. To remove the experiment from the test HDD, remove its `Kernel → Add` entry and `S540NvidiaPCIProbe.kext`, then reboot. The package does not install anything into macOS. Do not attempt a live unload while investigating an unexpected boot failure.

## Implementation boundary

The service uses a private match category and an exact PCI identity match. It takes one snapshot at startup and removes it at stop. It does not open the provider exclusively, map BARs, read or write MMIO, change PCI command bits, enable bus mastering, allocate DMA, install interrupts, invoke ACPI methods or alter device power. Its user-space reporter opens no hardware client. The access policy and strict snapshot decoder are checked during the native Intel build; CI does not load this experimental kext.

The reproducible build pins **acidanthera/MacKernelSDK** to `3f750085caa17ec3a7880f11c11bf4f48cd6a164`. Its unmodified kernel module runtime contains Apple code released under APSL 2.0. The built archive includes that license and the corresponding source location in **THIRD-PARTY-NOTICES.txt**. Project source is under the adjacent MIT license.
