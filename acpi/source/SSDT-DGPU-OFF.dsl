// Native _OFF method exists in SSDT9 at \_SB.PCI0.RP05.PXSX.
// Optional until the first boot has confirmed the firmware power sequence.
DefinitionBlock ("", "SSDT", 2, "LNVOC", "S54DGPU", 0x00000001)
{
    External (_SB_.PCI0.RP05.PXSX._OFF, MethodObj)
    Scope (\_SB)
    {
        Device (DOFF)
        {
            Name (_HID, "LNV0001")
            Method (_STA, 0, NotSerialized)
            {
                If (_OSI ("Darwin")) { Return (0x0F) }
                Return (Zero)
            }
            Method (_INI, 0, NotSerialized)
            {
                If (_OSI ("Darwin"))
                {
                    If (CondRefOf (\_SB.PCI0.RP05.PXSX._OFF))
                    {
                        \_SB.PCI0.RP05.PXSX._OFF ()
                    }
                }
            }
        }
    }
}
