# S540 firmware hotkey paths

This reference records selected findings from the original S540-15IWL GTX OEM tables. It contains no original table dumps or machine identities.

The DSDT and twelve SSDTs were recovered from the previously supplied hardware bundle. All twenty supplied ACPI tables match the bundle manifest, declared lengths and ACPI checksums. The DSDT SHA-256 is `5139a06fd931e15c7655046d79e67a36d63cdd626fdea3393e3482a59ca70f56`. Private disassembly used ACPICA 20230628; the known external `GFX0.CLID` resolution warning does not prevent inspection of the local methods below.

## Verified objects

| Object | OEM behavior |
|---|---|
| `\_SB.PCI0.LPCB.H_EC.VPC0` | HID `VPC2004`; `_STA` returns `0x0F` |
| `VPC0._CFG` | Returns `_VPC`, value `0xFE0D0014` |
| `H_EC._Q40` | Calls `D8XH(0, 0x40)`, then `Notify(VPC0, 0x80)` |
| `VPC0.VPCR(1)` | Reads the EC command field `VCMD` |
| `VPC0.VPCR(other)` | Reads the EC data field `VDAT` |
| `VPC0.VPCW(1, value)` | Writes `VCMD` |
| `VPC0.VPCW(other, value)` | Writes `VDAT` |
| EC fields | `VCMD`, `VDAT`, `VSTA` are eight-bit fields at offsets `0xB0`, `0xB1`, `0xB2` |
| `\_SB.PCI0.LPCB.PS2K` | HID `MSFT0001`, compatible ID `PNP0303`; no OEM `_DSM` |
| Keyboard profile override | No `RMCF` object in the original DSDT or twelve SSDTs |
| Brightness | `_Q8E`/`_Q8F` send `0x86`/`0x87` notifications to `GFX0.DD1F` |

## Event identity and protocol limits

The generic `_Q40` notification does not identify an individual F4/F5/F7/F8/F9/F10 action. The event payload must be read through the VPC protocol. Assigning a key directly to `_Q40` would conflate different firmware events.

The [Linux IdeaPad driver](https://github.com/torvalds/linux/blob/5029bff09e79ad80883c5ee2828b8c4a263cf3dd/drivers/platform/x86/lenovo/ideapad-laptop.c) provides a primary protocol reference. Its operation named `read_ec_data` first writes a read command, waits for completion, then reads the data field. Consequently a VPC query is not an entirely passive registry snapshot. A future implementation needs a timeout and command synchronization, with read queries separated from radio/camera state-changing commands. Cross-model event numbers are not a laptop test result.

The locked [VoodooPS2 2.3.7 keyboard map](https://github.com/acidanthera/VoodooPS2/blob/bdbf80639936701337f4574bae8c3ea25bb8dd3d/VoodooPS2Keyboard/ApplePS2ToADBMap.h) maps ordinary PS/2 F1–F12 to ordinary macOS F1–F12. The current release profile contains no Function Keys Standard/Special arrays. Firmware layer discrimination and macOS shortcut consumption are therefore reviewed separately from keyboard scancode remapping.

The [native event observer](../../packages/function-key-events/README.md) is the first diagnostic. It does not issue VPC commands or enable driver-wide scancode logging. If no matching user-space event is found, the firmware and driver paths above remain candidates for a targeted follow-up.

## Driver trace boundary

The current keyboard binary matches the official VoodooPS2 2.3.7 RELEASE payload: SHA-256 `b55758219af1b12b1c0e5e116ff1ee65dc5d8484086e5231103c242a5858a1e5`, Mach-O UUID `EFA883F4-7558-3E98-A352-E202CB3DFAAF`. A live diagnostic must also match the loaded bundle identity, version and UUID; an EFI file alone cannot establish which binary is running.

In the [pinned driver source](https://github.com/acidanthera/VoodooPS2/blob/bdbf80639936701337f4574bae8c3ea25bb8dd3d/VoodooPS2Keyboard/VoodooPS2Keyboard.cpp), a numeric `LogScanCodes` value of 2 enables down/up trace messages at runtime through the keyboard command gate. The trace includes original and remapped scan codes plus the ADB result before the final dead-key suppression. Earlier special handling, macro inversion and repeat filtering can still bypass that trace. An empty trace therefore cannot establish that no PS/2 input occurred.

These `IOLog` messages enter the system log. Any collector must enable the setting only during prompted windows, restore the original value, limit the stream to the exact keyboard message grammar, and keep password entry outside those windows. No persistent boot argument or keyboard map change is required.
