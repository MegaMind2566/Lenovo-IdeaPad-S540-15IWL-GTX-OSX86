// Keep the real laptop controller H_EC. Add a Darwin-only compatibility EC.
DefinitionBlock ("", "SSDT", 2, "LNVOC", "S54ECUSB", 0x00000001)
{
    External (_SB_.PCI0.LPCB, DeviceObj)
    Scope (\_SB.PCI0.LPCB)
    {
        Device (EC)
        {
            Name (_HID, "ACID0001")
            Method (_STA, 0, NotSerialized)
            {
                If (_OSI ("Darwin")) { Return (0x0F) }
                Return (Zero)
            }
        }
    }
    Scope (\_SB)
    {
        Device (USBX)
        {
            Name (_ADR, Zero)
            Method (_STA, 0, NotSerialized)
            {
                If (_OSI ("Darwin")) { Return (0x0F) }
                Return (Zero)
            }
            Method (_DSM, 4, NotSerialized)
            {
                If (Arg2 == Zero) { Return (Buffer (One) { 0x03 }) }
                Return (Package (0x08)
                {
                    "kUSBSleepPowerSupply", 0x13EC,
                    "kUSBSleepPortCurrentLimit", 0x0834,
                    "kUSBWakePowerSupply", 0x13EC,
                    "kUSBWakePortCurrentLimit", 0x0834
                })
            }
        }
    }
}
