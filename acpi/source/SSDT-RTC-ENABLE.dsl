// RTC._STA is gated by the STAS firmware field. AWAC._STA returns Zero.
// Enable the standard RTC only for Darwin; no CMOS registers are modified.
DefinitionBlock ("", "SSDT", 2, "LNVOC", "S54RTC", 0x00000001)
{
    External (STAS, FieldUnitObj)
    If (_OSI ("Darwin"))
    {
        If (CondRefOf (STAS)) { Store (One, STAS) }
    }
}
