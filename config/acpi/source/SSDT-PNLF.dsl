// Minimal backlight device. Actual brightness operation requires macOS testing.
DefinitionBlock ("", "SSDT", 2, "LNVOC", "S54PNLF", 0x00000001)
{
    External (_SB_.PCI0.GFX0, DeviceObj)
    Scope (\_SB.PCI0.GFX0)
    {
        Device (PNLF)
        {
            Name (_HID, EisaId ("APP0002"))
            Name (_CID, "backlight")
            Name (_UID, 0x13)
            Method (_STA, 0, NotSerialized)
            {
                If (_OSI ("Darwin")) { Return (0x0B) }
                Return (Zero)
            }
        }
    }
}
