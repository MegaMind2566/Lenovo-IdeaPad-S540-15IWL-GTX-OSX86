# ACPI analysis — BIOS BWCN19WW

Twenty original tables were verified: one DSDT, 12 SSDTs, and APIC, DMAR, ECDT, FACP, HPET, LPIT and MCFG. The 12 SSDTs have distinct hashes and match the number enumerated by Windows. The original dumps remain private local analysis material and are not included in the repository.

The original report's PARTIAL status contains only one note about an unavailable tool exit code. Subsequent file verification confirms correct lengths, checksums and hashes for every table. The dump does not need to be repeated.

## Prepared patches

| File | Purpose | Firmware evidence | Status |
|---|---|---|---|
| SSDT-PLUG | CPU power-management plugin-type property | Processor PR00 under `_SB` | Compiled; device test pending |
| SSDT-EC-USBX | Compatibility EC and USB power properties | Physical EC at `_SB.PCI0.LPCB.H_EC` | Compiled; physical EC preserved |
| SSDT-PNLF | Intel backlight device | iGPU at `_SB.PCI0.GFX0` | Compiled; brightness test pending |
| SSDT-RTC-ENABLE | Makes the standard RTC available to Darwin | RTC._STA depends on STAS; AWAC._STA returns Zero | Compiled; changes the firmware flag, not CMOS registers |
| SSDT-XOSI | Windows 2015 initialization path for I2C | TPD0._INI and _CRS depend on OSYS | Compiled; requires the OEM `_OSI → XOSI` rename |
| SSDT-DGPU-OFF | Calls the GTX's native power-off method | `_SB.PCI0.RP05.PXSX._OFF` in SSDT9 | Compiled; optional after the first successful boot |

The `_OSI("Darwin")` guards restrict macOS-specific changes to macOS. The XOSI wrapper forwards requests to the original method when another operating system starts.

The native NVIDIA power-off method contains hardware waits without timeouts. For the first boot, the profile uses `-wegnoegpu` and keeps the power-off patch optional. This boot argument prevents the dGPU driver from loading but does not guarantee that the GPU is powered off. Testing the power-off sequence follows a successful first boot.

## Two possible 960 EVO connections

- **960 EVO in a USB enclosure:** the PM981a remains on RP09. The macOS configuration must exclude it; confirm the connection before preparing that profile.
- **960 EVO replacing the PM981a:** the same RP09 path will host the target disk. Excluding it would hide the destination, so that exclusion must not be applied.

The M.2 NVMe form factor does not establish compatibility. The declared model is the 960 EVO; firmware, disk integrity and Tahoe operation still require device testing.

## Audio and touchpad

The codec is Realtek ALC257. Tahoe lacks AppleHDA, so AppleALC alone does not automatically restore the speakers and jack. The analog audio solution is selected after the first boot. No changes were applied to the system volume or macOS protections during this preparation.

The touchpad is an ELAN0662 I2C HID device on I2C0. The firmware sets its HID, I2C address and resources according to its own parameters. The XOSI wrapper selects the modern initialization path without inventing GPIO pin numbers. VoodooI2C and VoodooI2CHID are planned; actual operation requires a device test.

## Compilation

Sources are in `config/acpi/source`. The command `python builders/build_acpi.py --iasl /path/to/iasl` produces AML, logs and a manifest in `build/acpi`. Each AML must have an SSDT signature, a matching declared length and a checksum of zero modulo 256. The manifest also links the source SHA-256 to the compiled result.

The copies in `config/acpi/compiled` were produced with iASL 20240927. The automated check recompiles the sources with the CI compiler and validates the outputs again.

The original DSDT is not loaded again through OpenCore. These files are supplementary patches. The complete configuration, drivers, kexts and USB map still need to be assembled and checked before creating the installer.

## Initial USB-C disk configuration

The external 960 EVO connection is confirmed. The initial EFI blocks `com.apple.iokit.IONVMeFamily` from starting with the `Disable` strategy while preserving dependency information. The PM981a is the only detected native NVMe device; the external disk uses the USB stack. This block applies to every native NVMe device and must be removed before installing the 960 EVO internally. The PM981a's ACPI and PCI paths remain documented for possible revision. The outcome requires verification during the first boot.
