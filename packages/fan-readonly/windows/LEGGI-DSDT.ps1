# Lettura della sola DSDT tramite API firmware documentata di Windows.
[CmdletBinding()]
param([switch]$SelfTest)
Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$S540PriorHash = '5139a06fd931e15c7655046d79e67a36d63cdd626fdea3393e3482a59ca70f56'

function Assert-DsdtSize {
    param([long]$Size)
    if ($Size -lt 36 -or $Size -gt 2097152) {
        throw 'Dimensione DSDT fuori dai limiti ammessi (36 byte - 2 MiB).'
    }
}

function Get-AsciiHeader {
    param([byte[]]$Bytes, [int]$Offset, [int]$Length)
    $value = [Text.Encoding]::ASCII.GetString($Bytes, $Offset, $Length)
    return ([regex]::Replace($value, '[^\x20-\x7E]', '?')).Trim()
}

function Get-DsdtHeader {
    param([byte[]]$Bytes)
    if ($null -eq $Bytes) { throw 'La DSDT restituita e vuota.' }
    Assert-DsdtSize $Bytes.LongLength
    if ([Text.Encoding]::ASCII.GetString($Bytes, 0, 4) -ne 'DSDT') {
        throw 'Firma firmware diversa da DSDT.'
    }
    if (-not [BitConverter]::IsLittleEndian) {
        throw 'Piattaforma con ordine dei byte non supportato.'
    }
    [uint32]$declared = [BitConverter]::ToUInt32($Bytes, 4)
    Assert-DsdtSize $declared
    if ([long]$declared -ne $Bytes.LongLength) {
        throw 'La lunghezza dichiarata della DSDT non coincide con i byte ricevuti.'
    }
    [uint64]$sum = 0
    foreach ($item in $Bytes) { $sum += [uint64]$item }
    if (($sum % 256) -ne 0) { throw 'Checksum ACPI della DSDT non valido.' }
    return [ordered]@{
        Signature = 'DSDT'
        Length = [long]$declared
        AcpiRevision = [int]$Bytes[8]
        ChecksumValid = $true
        OEMID = Get-AsciiHeader $Bytes 10 6
        OEMTableID = Get-AsciiHeader $Bytes 16 8
        OEMRevision = [uint32][BitConverter]::ToUInt32($Bytes, 24)
        CreatorID = Get-AsciiHeader $Bytes 28 4
        CreatorRevision = [uint32][BitConverter]::ToUInt32($Bytes, 32)
    }
}

function Get-Sha256 {
    param([byte[]]$Bytes)
    $algorithm = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($algorithm.ComputeHash($Bytes))).Replace('-', '').ToLowerInvariant() }
    finally { $algorithm.Dispose() }
}

function Write-NewBytes {
    param([string]$Path, [byte[]]$Bytes)
    $stream = [IO.File]::Open($Path, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    try { $stream.Write($Bytes, 0, $Bytes.Length) }
    finally { $stream.Dispose() }
}

function Test-RejectedDsdt {
    param([byte[]]$Bytes, [string]$Label)
    $rejected = $false
    try { $null = Get-DsdtHeader $Bytes } catch { $rejected = $true }
    if (-not $rejected) { throw ('Self-test non superato: ' + $Label) }
}

function Invoke-SelfTest {
    [byte[]]$valid = New-Object byte[] 44
    [Text.Encoding]::ASCII.GetBytes('DSDT').CopyTo($valid, 0)
    [BitConverter]::GetBytes([uint32]44).CopyTo($valid, 4)
    $valid[8] = 2
    [Text.Encoding]::ASCII.GetBytes('LENOVO').CopyTo($valid, 10)
    [Text.Encoding]::ASCII.GetBytes('S540TEST').CopyTo($valid, 16)
    [int]$sum = 0
    foreach ($item in $valid) { $sum += $item }
    $valid[9] = [byte]((256 - ($sum % 256)) % 256)
    $header = Get-DsdtHeader $valid
    if ($header.Length -ne 44 -or $header.OEMTableID -ne 'S540TEST') { throw 'Self-test header valido non superato.' }
    if ([BitConverter]::ToUInt32([Text.Encoding]::ASCII.GetBytes('DSDT'), 0) -ne 0x54445344) { throw 'Self-test identificatore API DSDT non superato.' }
    [byte[]]$bad = $valid.Clone(); $bad[0] = 88
    Test-RejectedDsdt $bad 'firma errata'
    [byte[]]$bad = $valid.Clone(); [BitConverter]::GetBytes([uint32]45).CopyTo($bad, 4)
    Test-RejectedDsdt $bad 'lunghezza incoerente'
    [byte[]]$bad = $valid.Clone(); $bad[43] = 1
    Test-RejectedDsdt $bad 'checksum errato'
    Test-RejectedDsdt (New-Object byte[] 35) 'buffer corto'
    Test-RejectedDsdt (New-Object byte[] 2097153) 'buffer troppo grande'
    if ((Get-Sha256 ([Text.Encoding]::ASCII.GetBytes('abc'))) -ne 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad') { throw 'Self-test SHA256 non superato.' }
    Write-Output 'Self-test: 8 controlli superati. Nessuna API firmware chiamata.'
}

try {
    if ($SelfTest) { Invoke-SelfTest; exit 0 }
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
        throw 'Eseguire questo comando in Windows avviato normalmente sul Lenovo.'
    }
    if (-not ('S540DsdtNativeApi' -as [type])) {
        Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class S540DsdtNativeApi {
    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern uint GetSystemFirmwareTable(uint provider, uint tableId, IntPtr buffer, uint bufferSize);
}
'@
    }
    [uint32]$provider = 0x41435049 # C provider signature 'ACPI'.
    [uint32]$table = 0x54445344    # Little-endian table bytes 'DSDT'.
    [uint32]$required = [S540DsdtNativeApi]::GetSystemFirmwareTable($provider, $table, [IntPtr]::Zero, 0)
    if ($required -eq 0) {
        throw ('Windows non ha restituito la DSDT. Codice API: ' + [Runtime.InteropServices.Marshal]::GetLastWin32Error())
    }
    Assert-DsdtSize $required
    $buffer = [IntPtr]::Zero
    try {
        $buffer = [Runtime.InteropServices.Marshal]::AllocHGlobal([int]$required)
        [uint32]$received = [S540DsdtNativeApi]::GetSystemFirmwareTable($provider, $table, $buffer, $required)
        if ($received -eq 0) {
            throw ('Lettura DSDT non riuscita. Codice API: ' + [Runtime.InteropServices.Marshal]::GetLastWin32Error())
        }
        if ($received -ne $required) {
            throw 'La dimensione della DSDT e cambiata durante la lettura; raccolta interrotta.'
        }
        [byte[]]$dsdt = New-Object byte[] ([int]$received)
        [Runtime.InteropServices.Marshal]::Copy($buffer, $dsdt, 0, [int]$received)
    }
    finally { if ($buffer -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::FreeHGlobal($buffer) } }
    $header = Get-DsdtHeader $dsdt
    $hash = Get-Sha256 $dsdt
    $report = [ordered]@{
        Schema = 1
        Mode = 'READ_ONLY_WINDOWS_FIRMWARE_API_DSDT_ONLY'
        SHA256 = $hash
        PreviousDSDTSHA256 = $S540PriorHash
        MatchesPreviousDump = ($hash -eq $S540PriorHash)
        Header = $header
        Manufacturer = $null
        Model = $null
        Scope = 'DSDT soltanto; nessuna lettura EC, driver, modifica EFI o altre tabelle ACPI.'
    }
    try {
        $machine = Get-CimInstance -ClassName Win32_ComputerSystem -Property Manufacturer, Model -ErrorAction Stop | Select-Object -First 1
        $report.Manufacturer = [string]$machine.Manufacturer
        $report.Model = [string]$machine.Model
    } catch { } # Il modello non e necessario per leggere e verificare la tabella.
    $desktop = [Environment]::GetFolderPath([Environment+SpecialFolder]::Desktop)
    if ([string]::IsNullOrWhiteSpace($desktop) -or -not (Test-Path -LiteralPath $desktop -PathType Container)) {
        throw 'Cartella Scrivania di Windows non disponibile.'
    }
    $name = 'S540-Ventole-DSDT.' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.' + [Guid]::NewGuid().ToString('N').Substring(0,8)
    $directory = Join-Path $desktop $name
    $zip = $directory + '.zip'
    if ((Test-Path -LiteralPath $directory) -or (Test-Path -LiteralPath $zip)) { throw 'Il percorso del report esiste gia; nessun file sovrascritto.' }
    $null = New-Item -ItemType Directory -Path $directory -ErrorAction Stop
    Write-NewBytes (Join-Path $directory 'DSDT.aml') $dsdt
    $json = $report | ConvertTo-Json -Depth 6
    $encoding = New-Object Text.UTF8Encoding($false)
    Write-NewBytes (Join-Path $directory 'report.json') ($encoding.GetBytes($json + [Environment]::NewLine))
    Compress-Archive -LiteralPath $directory -DestinationPath $zip -CompressionLevel Optimal -ErrorAction Stop
    Write-Output 'RACCOLTA DSDT COMPLETATA. Nessuna modifica a EFI, driver o controller EC.'
    Write-Output ('SHA256: ' + $hash)
    Write-Output ('Coincide con il dump precedente: ' + $report.MatchesPreviousDump)
    Write-Output ('ZIP da allegare: ' + $zip)
    exit 0
}
catch {
    Write-Host ('ERRORE: ' + $_.Exception.Message)
    Write-Host 'Raccolta interrotta. Nessun tentativo automatico o modifica hardware eseguiti.'
    exit 1
}
