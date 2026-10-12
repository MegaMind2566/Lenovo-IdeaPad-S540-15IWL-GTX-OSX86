// CPU path verified in the original firmware: \_SB.PR00.
DefinitionBlock ("", "SSDT", 2, "LNVOC", "S54PLUG", 0x00000001)
{
    External (_SB_.PR00, ProcessorObj)
    Scope (\_SB.PR00)
    {
        Method (_DSM, 4, NotSerialized)
        {
            If (_OSI ("Darwin"))
            {
                If (Arg2 == Zero) { Return (Buffer (One) { 0x03 }) }
                Return (Package (0x02) { "plugin-type", One })
            }
            Return (Buffer (One) { 0x00 })
        }
    }
}
