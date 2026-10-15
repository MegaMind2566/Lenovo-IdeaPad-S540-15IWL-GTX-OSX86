# Darwin platform facts and endpoint ACPI

This component collects the platform record required by the original global RM. It supplies the real Darwin `nv_acpi_rom_method` boundary for the exact retained PCI endpoint. It does not initialize a GPU or stand in for adapter/GSP initialization.

`Context::initialize(provider)` retains the selected endpoint and resolves only its published `acpi-path` alias, following Apple's `IOPCICopyACPIDevice` implementation. Facts collection can precede global-host allocation. After the adapter context exists, `bindState(state)` binds its exact identity once; ROM access is unavailable before binding. The resolved entry must be an active `IOACPIPlatformDevice`. No PCI bridge, arbitrary service parent, guessed ACPI pathname, or unrelated ACPI device is substituted. A missing companion or `_ROM` method is recorded explicitly and the bound ROM call returns `NV_ERR_NOT_SUPPORTED`; original RM decides whether its fallback applies.

`collect(&facts)` publishes a partial record with a known-bit mask and returns `NV_ERR_NOT_READY` unless every required fact is established. Unknown facts are not converted into negative answers.

| Fact | Actual source |
| --- | --- |
| Registered CPU count | Exported XNU `unsigned int real_ncpus`, populated from registered processors |
| CPU frequency | Exported XNU `gPEClockFrequencyInfo.cpu_frequency_hz`; a zero value leaves the CPU fact unknown |
| EFI | Kernel-recognized `gPEEFISystemTable` pointer |
| Notebook chassis | SMBIOS Type 3 chassis values 9/10, including the defined lock bit; unknown or malformed records are refused |
| Rechargeable battery | Actual ACPI namespace `_BIX`/`_BIF` package technology field, matching the original NVIDIA predicate |
| NVIDIA vGPU hypervisor | Explicit non-`NV_VGX_HYPER` build profile; this is separate from generic CPU hypervisor detection |
| NvSwitch presence | Current published PCI inventory: NVIDIA vendor and PCI bridge-other class, matching the original predicate |
| S0ix | Explicitly disabled operational policy for the initial adapter profile; FADT hardware capability is collected separately |
| OS version and date | Running kernel globals from `libkern/version.h`, not the SDK's build-time version macros |

AppleSMBIOS publishes its table either as data or through its original serializer. The serializer path requires a checksum-valid bounded SMBIOS entry point first. The decoder reads only the chassis byte and never publishes table contents, identifiers, serial numbers, addresses, or registry paths. Registry enumeration has a finite node budget and an invalidated/incomplete enumeration leaves the relevant fact unknown.

`collectSegment` walks the exact companion's ACPI ancestors until it proves a PCI root bridge through `_HID` (`PNP0A03`/`PNP0A08`, string or compressed EISA ID). It reads that bridge's `_SEG`. ACPI's segment-zero default applies only after that identity proof and an explicit missing-object result; unrelated evaluation failures remain unavailable.

`collectDeviceFacts` records the selected provider's actual configuration header, BDF, segment, three assigned BAR descriptors and D0 state, without sizing writes or BAR mappings. It requires the exact pinned TU117/subsystem/revision identity and checks descriptor lengths against assigned BAR addresses. A null PCI handle is permitted during construction; the real transport token must be installed before adapter preparation. Intel-console proof requires an active original `IOFramebuffer::isConsoleDevice()` and its actual PCI ancestor with Intel display identity. If no such console is published, the result is not ready. `noCoherentGpuMemoryProfile` refers to NVIDIA's separate coherent GPU-memory/NUMA feature: the original Linux discovery immediately returns on non-AArch64. It does not describe or disable coherent x86 host-memory DMA.

The `_ROM` bridge accepts only the exact bound `nv_state_t` identity in ordinary thread context. Each request supplies offset and length as two ACPI integers. Requests are limited to 64 KiB within a 16 MiB ROM window. The returned object must be bounded data covering the request. Failed calls preserve the output buffer. Inputs, parameter objects, result objects, and companion/provider references retain distinct ownership.

The caller must keep this context alive through original adapter shutdown and callback quiescence, then shut down the global host context before releasing these fact-string lifetimes. Every lifecycle operation is externally serialized by the combined startup owner. The component creates no worker, interrupt handler, user client, kernel file reader, or power transition.

The native check exercises the production byte decoders, malformed tables, contradictory chassis records, and ROM-window bounds. Native builds deliberately refuse Darwin collection rather than fabricate platform facts. Darwin source compilation against the pinned SDK establishes type compatibility; actual runtime collection and GSP execution remain separate evidence.
