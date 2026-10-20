# S540 O2Micro read-only observer 0.1.0

Diagnostic experiment for the Lenovo S540 reader `1217:8621`, subsystem
`17AA:3803`, class `080501`. It does not implement SD card support.
Only Intel x86_64 on Darwin 25 is accepted at runtime.

The single personality attaches to `IOResources` with its own match category.
The observer enumerates published `IOPCIDevice` services; it never attaches to,
opens, claims, powers, configures, interrupts or resets the reader. It makes
four finite observations at start and nominally 2, 10 and 20 seconds later.
No further timer is scheduled. A missing or powered-down reader is recorded
as a skipped observation, without trying to wake it.

PCI reads are limited to identification/BDF, command/status, class/revision,
header type, existing BAR values, a bounded standard capability-header walk
and PM capability/status, byte offsets `D3 D4`, and dword offsets
`DC F0 300 304 324 3E4`. BAR sizing probes are not performed.

MMIO is attempted only for the unique exact hardware/subsystem/class, a valid assigned
memory BAR0, PCI memory decoding enabled, PMCSR already D0 and an existing
BAR0 memory descriptor whose physical segment agrees with BAR0. The descriptor is obtained through a retained copy
of `IODeviceMemory`, then mapped with `kIOMapReadOnly | kIOMapUnique`.
The mapping must report read-only protection and sufficient length.
Reads are limited to SDHCI dwords `24 28 2C 30 34 38 40 44`, the version
word `FE` and O2Micro dword `1CC`. No command, argument, FIFO, response,
CID/CSD, card contents, serial number, UUID or volume name is read or exposed.
The mapping is released after each observation. There are no register writes,
power-management requests, interrupts, ACPI evaluations or user-client commands.

`S540SDDiagnostics` in the observer's IORegistry entry contains `Version`,
`Status`, `SnapshotLimit` and a `Snapshots` array. Each snapshot includes its
index, scheduled offset, target count/status, whitelisted PCI/MMIO numbers and
bounded child-driver class/scalar state. The expected port path
`RP04@1C/PXSX@0` is reported only as a boolean context check; full registry
paths are not published. Snapshots are observations, not an
atomic transaction: the existing SD driver can change state concurrently.
Guards are rechecked before and after MMIO reads, but cannot eliminate that
race without claiming or changing the device. A successful read is not proof
that a card has initialized. An absent field is not a false hardware state.

The collector in `tools` waits 25 seconds, captures the observer and existing
SD driver state, then records a remove/insert event. The boot snapshots are
fixed; removing and inserting a card does not trigger new probe MMIO reads.
Do not treat this experiment as proven harmless solely because it contains
no writes: read-side effects and driver concurrency remain hardware limits.

## Build

Use macOS/Xcode and a clean checkout of
[MacKernelSDK](https://github.com/acidanthera/MacKernelSDK/tree/3f750085caa17ec3a7880f11c11bf4f48cd6a164)
at commit `3f750085caa17ec3a7880f11c11bf4f48cd6a164`:

```sh
SDK_PATH=/absolute/path/to/MacKernelSDK /bin/bash build.sh
```

Output: `build/Release/S540O2MicroReadOnlyProbe.kext`. The build script does
not install/load it or modify EFI, NVRAM or system settings. Boot injection
must be restricted to x86_64 Darwin 25 in the separate test EFI. This source
package does not alter an existing SD driver or its match configuration.

## API basis

The pinned SDK supplies `IOService::getMatchingServices`, retained
`IORegistryEntry::copyProperty`, `IOPCIDevice::extendedConfigRead8/16/32`,
`IOMemoryDescriptor::map`, read-only/unique map options and
`IOTimerEventSource`. Matching dictionaries, iterators, retained properties,
maps and timer/workloop resources have explicit release paths. Sources:

- [Pinned IOPCIDevice API](https://github.com/acidanthera/MacKernelSDK/blob/3f750085caa17ec3a7880f11c11bf4f48cd6a164/Headers/IOKit/pci/IOPCIDevice.h)
- [Pinned memory mapping API](https://github.com/acidanthera/MacKernelSDK/blob/3f750085caa17ec3a7880f11c11bf4f48cd6a164/Headers/IOKit/IOMemoryDescriptor.h)
- [Pinned timer API](https://github.com/acidanthera/MacKernelSDK/blob/3f750085caa17ec3a7880f11c11bf4f48cd6a164/Headers/IOKit/IOTimerEventSource.h)

The new observer code and scripts are MIT licensed. MacKernelSDK and its
headers/libraries retain their own licenses; the SDK is not bundled here.
