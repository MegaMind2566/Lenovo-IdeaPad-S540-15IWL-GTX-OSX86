# Patch verification against the original tables

Verification dated 13 October 2026, covering the supplied config, the Whiskey Lake test config and the Lenovo S540-15IWL's 20 original ACPI tables. EFI structural checks are described in [EFI verification](efi-review.md). This review examined the actual paths and methods; no static error was found that would justify a new DSDT patch.

Update after the direct trace: the driver dump and photograph identify a specific insufficient stolen-memory error in Apple's calculation. The [memory test](../../archive/first-boot/docs/intel-memory-test.md) changes framebuffer properties in the config. The ACPI findings below remain valid.

## Patches and objects

| Patch or setting | Firmware finding | Result |
|---|---|---|
| SSDT-PLUG | The processor is `\_SB.PR00`; its scope contains no competing OEM `_DSM` | Correct path and type |
| SSDT-EC-USBX | The physical controller is `\_SB.PCI0.LPCB.H_EC`, also identified by ECDT; no competing EC or USBX Device exists | Physical controller preserved |
| SSDT-RTC-ENABLE | RTC returns active status when STAS=1; AWAC returns Zero | Consistent RTC selection |
| `_OSI → XOSI` | Eleven OEM occurrences in the DSDT; Windows queries extend through 2015 | Proxy covers the actual queries without a competing rename |
| SSDT-PNLF | GFX0 exists at PCI device 2, function 0; no OEM PNLF Device shares the name | Correct path, UID `0x13` = decimal 19 |
| SSDT-DGPU-OFF | The actual method is `\_SB.PCI0.RP05.PXSX._OFF` | Correct path, but the SSDT remains disabled |

OpenCore 1.0.8 patches OEM tables before adding custom SSDTs. Consequently, `_OSI("Darwin")` calls in the new SSDTs are not renamed to XOSI. The proxy does not create the recursion that would result from also modifying its own `_OSI` call.

PNLF uses the Coffee Lake value specified for these Whiskey Lake identifiers. The official sample selects UID 19 in its CFL branch. The absence of the sample's long PWM initialization method does not establish a missing feature in this profile: that branch does not perform the rescaling used for other generations.

## GPU and config properties

The DSDT exposes GFX0 with `_ADR=0x00020000` under PCI0. This corresponds to `PciRoot(0x0)/Pci(0x2,0x0)`, where OpenCore injects the Intel properties. OEM SSDTs add the GPU's complete methods.

The Intel `_DSM` handles its own GUID and panel metadata. It does not return Apple `AAPL,ig-platform-id`, `device-id` or framebuffer properties that override the config. The reviewed graphics `_INI` method updates the display list without a wait loop. WhateverGreen's device rename in the I/O registry does not require a binary GFX0 rename in the AML namespace.

| Four-byte Data property | Supplied config | Previously delivered Whiskey Lake test |
|---|---|---|
| AAPL,ig-platform-id | `00009B3E` | `0900A53E` |
| device-id | `9B3E0000` | `A53E0000` |

The WhateverGreen manual specifies the test pair for Whiskey Lake UHD 620. Both framebuffers are mobile and declare 58 MB of stolen memory. That difference alone does not identify the cause of the stall, and the test had already been reported without a working interface. The latest archive contains no new config that would establish which values were read during that boot.

GUMA, GIVD, GMFN, ASLB and BGMS are PCI/OpRegion/GNVS fields evaluated at runtime. These tables do not measure BIOS-assigned DVMT. No 32 MB allocation is assumed, and stolenmem, fbmem or connector patches are not added without a measurement or driver error.

## ACPI verification limitations

The DSDT and twelve OEM SSDTs were disassembled separately with iasl 20230628. Joint external-symbol resolution failed: SSDT9 defines RP05._PR0, while SSDT11 defines it in the RPIN=4 branch. RPIN is read at runtime, and its value is absent from the dump. This is a possible conditional OEM overlap, not a collision introduced by the custom SSDTs. Other joint-disassembly errors are not used to infer additional collisions unconfirmed by the source. The original tables are not deleted or replaced on the basis of this result.

OpenCore logs report MAT support as 0. The 1.0.8 code tolerates a missing MAT during RebuildAppleMemoryMap; SyncRuntimePermissions also retains handling of the regular memory map. No rule automatically requires EnableWriteUnprotector=True in this case. Recovery and VESA boot reach the interface. Without a runtime-call error, the Booter combination is not changed to explain the graphics stall.

## Resulting diagnostic step

The reviewed patches remain unchanged. The latest archive contains twelve new empty tracev3 files and five nonempty files matching the previous collection. Repeating that collection would not necessarily capture the Intel error. The [direct Intel trace](../../archive/first-boot/docs/intel-trace.md) uses DEBUG Lilu and WhateverGreen builds of the same installed versions and also saves the exact test config. It is a diagnostic tool, not an already confirmed acceleration fix.

## NVIDIA power-off review: October 14, 2026

The previously supplied private EFI keeps `SSDT-DGPU-OFF` disabled and includes `-wegnoegpu`. The optional table calls the OEM `\_SB.PCI0.RP05.PXSX._OFF` under Darwin. Confirming the method's path does not establish that calling it during initialization is safe.

In the supplied OEM SSDT9, `PXSX._OFF` issues an EC command, checks firmware state and can call `HGOF`. That method can set `LNKD=1` and wait for `LNKS=0` without a timeout before clearing `DPWR` and `DPWE`. If the hardware condition does not arrive, the method can remain in the wait. The separate `RP05.PC05._OFF` power-resource path includes an EC mutex, `MSD3` tracking and conditional GC6 sequencing; it is not treated as an interchangeable call.

The device's OEM `_STA` always returns `0x0F`. That status does not measure the physical power rail. Likewise, Intel package power excludes the NVIDIA rail.

The reviewed [Lilu 1.7.2 implementation](https://github.com/acidanthera/Lilu/blob/1.7.2/Lilu/Sources/kern_devinfo.cpp) terminates and stops GPU/audio IOService objects in `processSwitchOff()`; that function contains no explicit call to this OEM `_OFF`. This supports keeping software device disabling separate from verified electrical power-off.

No ACPI or EFI change follows from this review. By request, electrical power-off work is deferred until after the NVIDIA driver-port attempt. The optional SSDT remains disabled. When this work resumes, it still requires a bounded, justified hardware sequence and evidence of the resulting state. NVIDIA Linux-driver port research remains open and separate.

## Primary references

- [OpenCore 1.0.8, ACPI order and Booter quirks](https://github.com/acidanthera/OpenCorePkg/blob/1.0.8/Docs/Configuration.tex).
- [OpenCore 1.0.8, PNLF sample](https://github.com/acidanthera/OpenCorePkg/blob/1.0.8/Docs/AcpiSamples/Source/SSDT-PNLF.dsl).
- [OpenCore 1.0.8, memory-map handling](https://github.com/acidanthera/OpenCorePkg/blob/1.0.8/Library/OcAfterBootCompatLib/ServiceOverrides.c).
- [OpenCore 1.0.8, memory attributes](https://github.com/acidanthera/OpenCorePkg/blob/1.0.8/Library/OcMemoryLib/MemoryAttributes.c).
- [WhateverGreen 1.7.1, Intel manual](https://github.com/acidanthera/WhateverGreen/blob/1.7.1/Manual/FAQ.IntelHD.en.md).
- [WhateverGreen 1.7.1, GPU rename in the I/O registry](https://github.com/acidanthera/WhateverGreen/blob/1.7.1/WhateverGreen/kern_weg.cpp).
