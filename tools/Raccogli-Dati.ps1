#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$OutputRoot = '',
    [switch]$SkipToolDownload,
    [switch]$NoOpenFolder
)

$ErrorActionPreference = 'Stop'
$kitRoot = Split-Path $PSScriptRoot -Parent
$warnings = [System.Collections.Generic.List[string]]::new()
$collectionVersion = '1.0.0'
$wantedSignatures = @('DSDT', 'SSDT', 'FACP', 'APIC', 'HPET', 'DMAR', 'MCFG', 'ECDT', 'LPIT')
$utf8 = [System.Text.UTF8Encoding]::new($false)

function Write-JsonFile {
    param([string]$Path, [object]$Value)
    [System.IO.File]::WriteAllText($Path, (ConvertTo-Json -InputObject $Value -Depth 12), $utf8)
}

function Add-CollectionWarning {
    param([string]$Message)
    $warnings.Add($Message)
    Write-Host ('  Nota: ' + $Message) -ForegroundColor Yellow
}

function Get-DeviceProperties {
    param([string]$DeviceId)
    $values = @{}
    try {
        $keys = @('DEVPKEY_Device_HardwareIds', 'DEVPKEY_Device_CompatibleIds', 'DEVPKEY_Device_LocationPaths', 'DEVPKEY_Device_Service')
        foreach ($prop in @(Get-PnpDeviceProperty -InstanceId $DeviceId -KeyName $keys -ErrorAction SilentlyContinue)) {
            if ($null -ne $prop) { $values[$prop.KeyName] = $prop.Data }
        }
    } catch { }
    return $values
}

function Get-AcpiHeader {
    param([string]$Path)
    $bytes = [System.IO.File]::ReadAllBytes($Path)
    if ($bytes.Length -lt 36) { throw 'Tabella ACPI troppo corta.' }
    $signature = [System.Text.Encoding]::ASCII.GetString($bytes, 0, 4)
    $length = [BitConverter]::ToUInt32($bytes, 4)
    if ($length -lt 36 -or $length -ne $bytes.Length) { throw ('Lunghezza ACPI non valida: ' + $signature) }
    $sum = 0
    foreach ($b in $bytes) { $sum = ($sum + [int]$b) -band 255 }
    if ($sum -ne 0) { throw ('Checksum ACPI non valido: ' + $signature) }
    return [pscustomobject]@{
        Signature = $signature
        Length = $length
        OemId = [System.Text.Encoding]::ASCII.GetString($bytes, 10, 6).Trim()
        OemTableId = [System.Text.Encoding]::ASCII.GetString($bytes, 16, 8).Trim()
        Sha256 = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
    }
}

try {
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) { throw 'Questo programma richiede Windows.' }
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    $isAdmin = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if (-not $isAdmin) {
        Write-Host 'Windows richiedera i permessi di amministratore per leggere i dati.'
        $arguments = '-NoLogo -NoProfile -ExecutionPolicy Bypass -File "{0}"' -f $PSCommandPath
        if ($OutputRoot) { $arguments += ' -OutputRoot "{0}"' -f $OutputRoot }
        if ($SkipToolDownload) { $arguments += ' -SkipToolDownload' }
        if ($NoOpenFolder) { $arguments += ' -NoOpenFolder' }
        $powershell = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
        $child = Start-Process -FilePath $powershell -ArgumentList $arguments -Verb RunAs -Wait -PassThru
        exit $child.ExitCode
    }

    if (-not $OutputRoot) { $OutputRoot = [Environment]::GetFolderPath('Desktop') }
    if (-not $OutputRoot) { $OutputRoot = Join-Path $kitRoot 'Raccolte' }
    $null = New-Item -ItemType Directory -Path $OutputRoot -Force
    $name = 'Lenovo-Hackintosh-dati-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
    if (Test-Path -LiteralPath (Join-Path $OutputRoot $name)) { $name += '-' + [Guid]::NewGuid().ToString('N').Substring(0, 8) }
    $out = Join-Path $OutputRoot $name
    $acpiOut = Join-Path $out 'ACPI'
    $null = New-Item -ItemType Directory -Path $acpiOut -Force
    Write-Host 'Lenovo Hackintosh - raccolta dati' -ForegroundColor Cyan
    Write-Host '[1/4] Modello, BIOS, processore e dischi'
    try {
        $computer = Get-CimInstance Win32_ComputerSystem
        $bios = Get-CimInstance Win32_BIOS
        $system = [ordered]@{
            Manufacturer = $computer.Manufacturer
            Model = $computer.Model
            MemoryBytes = $computer.TotalPhysicalMemory
            BiosVersion = $bios.SMBIOSBIOSVersion
            BiosDate = $bios.ReleaseDate
            Cpu = @(Get-CimInstance Win32_Processor | Select-Object Name, NumberOfCores, NumberOfLogicalProcessors)
            Windows = Get-CimInstance Win32_OperatingSystem | Select-Object Caption, Version, BuildNumber, OSArchitecture
            Disks = @(Get-CimInstance Win32_DiskDrive | Select-Object Index, Model, Size, InterfaceType, FirmwareRevision)
        }
        try { $system['SecureBoot'] = [bool](Confirm-SecureBootUEFI) } catch { $system['SecureBoot'] = 'Non rilevato' }
        Write-JsonFile (Join-Path $out 'sistema.json') $system
    } catch { Add-CollectionWarning ('Inventario sistema incompleto: ' + $_.Exception.Message) }

    Write-Host '[2/4] Identificativi di audio, touchpad e altri dispositivi'
    $devices = @()
    try {
        $classes = @('Display', 'MEDIA', 'AudioEndpoint', 'HIDClass', 'Mouse', 'Keyboard', 'Net', 'Bluetooth', 'System', 'USB', 'SDHost', 'Camera', 'Image')
        $pnp = @(Get-PnpDevice -PresentOnly | Where-Object {
            $_.Class -in $classes -and $_.InstanceId -match '^(PCI|ACPI|HDAUDIO|INTELAUDIO|USB|HID)\\'
        })
        $devices = @(foreach ($dev in $pnp) {
            $p = Get-DeviceProperties $dev.InstanceId
            $parts = $dev.InstanceId.Split('\')
            [pscustomobject]@{
                Class = $dev.Class
                Name = $dev.FriendlyName
                Status = $dev.Status
                DeviceType = ($parts | Select-Object -First 2) -join '\'
                HardwareIds = @($p['DEVPKEY_Device_HardwareIds'])
                CompatibleIds = @($p['DEVPKEY_Device_CompatibleIds'])
                LocationPaths = @($p['DEVPKEY_Device_LocationPaths'])
                Service = $p['DEVPKEY_Device_Service']
            }
        })
        Write-JsonFile (Join-Path $out 'dispositivi.json') $devices
        $devices | Select-Object Class, Name, Status, DeviceType,
            @{n='HardwareIds';e={$_.HardwareIds -join '; '}},
            @{n='CompatibleIds';e={$_.CompatibleIds -join '; '}},
            @{n='LocationPaths';e={$_.LocationPaths -join '; '}}, Service |
            Export-Csv -LiteralPath (Join-Path $out 'dispositivi.csv') -NoTypeInformation -Encoding UTF8
    } catch { Add-CollectionWarning ('Identificativi dispositivi incompleti: ' + $_.Exception.Message) }

    Write-Host '[3/4] Tabelle ACPI'
    $tableIds = @()
    $tableCounts = @{}
    $acpiSource = 'Windows API'
    try {
        Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class LenovoFirmwareReader {
    public const UInt32 Acpi = 0x41435049;
    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern UInt32 EnumSystemFirmwareTables(UInt32 provider, byte[] buffer, UInt32 size);
    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern UInt32 GetSystemFirmwareTable(UInt32 provider, UInt32 id, byte[] buffer, UInt32 size);
}
'@
        $n = [LenovoFirmwareReader]::EnumSystemFirmwareTables([LenovoFirmwareReader]::Acpi, $null, 0)
        if ($n -eq 0 -or $n -gt 1048576 -or ($n % 4) -ne 0) { throw 'Enumerazione ACPI non disponibile.' }
        $buffer = [byte[]]::new([int]$n)
        $read = [LenovoFirmwareReader]::EnumSystemFirmwareTables([LenovoFirmwareReader]::Acpi, $buffer, $n)
        if ($read -ne $n) { throw 'Enumerazione ACPI incompleta.' }
        for ($i = 0; $i -lt $n; $i += 4) {
            $id = [BitConverter]::ToUInt32($buffer, $i)
            $sig = [System.Text.Encoding]::ASCII.GetString($buffer, $i, 4)
            $tableIds += [pscustomobject]@{Id=$id;Signature=$sig}
            if ($wantedSignatures -contains $sig) {
                if (-not $tableCounts.ContainsKey($sig)) { $tableCounts[$sig] = 0 }
                $tableCounts[$sig]++
            }
        }
    } catch { Add-CollectionWarning ('Enumerazione firmware: ' + $_.Exception.Message) }

    $toolSpec = [ordered]@{
        Version = '20251212'
        Url = 'https://github.com/open-acpica/acpica/releases/download/20251212/acpidump.exe'
        Sha256 = '872bac39d470aab28f743e11fa40bb1885a09786238cef56a3d5b5a406a6e43b'
    }
    $scratch = Join-Path ([System.IO.Path]::GetTempPath()) ('LenovoAcpi-' + [Guid]::NewGuid().ToString('N'))
    $null = New-Item -ItemType Directory -Path $scratch
    try {
        if (-not $SkipToolDownload) {
            [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
            $tool = Join-Path $scratch 'acpidump.exe'
            Invoke-WebRequest -Uri $toolSpec.Url -OutFile $tool -UseBasicParsing -TimeoutSec 60
            $actual = (Get-FileHash -LiteralPath $tool -Algorithm SHA256).Hash.ToLowerInvariant()
            if ($actual -ne $toolSpec.Sha256) { throw 'SHA-256 dello strumento ACPI non valido: esecuzione annullata.' }
            Push-Location $scratch
            try {
                $proc = Start-Process -FilePath $tool -ArgumentList '-b' -WorkingDirectory $scratch -PassThru -NoNewWindow -RedirectStandardOutput (Join-Path $scratch 'output.txt') -RedirectStandardError (Join-Path $scratch 'error.txt')
                if (-not $proc.WaitForExit(60000)) { $proc.Kill(); throw 'Lo strumento ACPI non ha terminato entro 60 secondi.' }
                $proc.WaitForExit()
                if ($proc.ExitCode -ne 0) { Add-CollectionWarning ('acpidump ha restituito il codice ' + $proc.ExitCode + '; verifico i file disponibili.') }
                if (-not (Get-ChildItem -LiteralPath $scratch -Filter 'dsdt*.dat')) {
                    $proc = Start-Process -FilePath $tool -ArgumentList '-b -n DSDT' -WorkingDirectory $scratch -PassThru -NoNewWindow -RedirectStandardOutput (Join-Path $scratch 'dsdt-output.txt') -RedirectStandardError (Join-Path $scratch 'dsdt-error.txt')
                    if (-not $proc.WaitForExit(30000)) { $proc.Kill(); throw 'Lettura DSDT oltre il tempo previsto.' }
                    $proc.WaitForExit()
                }
            } finally { Pop-Location }
            foreach ($f in @(Get-ChildItem -LiteralPath $scratch -Filter '*.dat')) {
                try {
                    $header = Get-AcpiHeader $f.FullName
                    if ($wantedSignatures -contains $header.Signature) {
                        $destination = Join-Path $acpiOut ($f.BaseName.ToUpperInvariant() + '.aml')
                        Copy-Item -LiteralPath $f.FullName -Destination $destination
                        $acpiSource = 'ACPICA acpidump; eventuale ripiego Windows API'
                    }
                } catch { Add-CollectionWarning ('Una tabella ACPI non supera i controlli: ' + $f.Name) }
            }
        }
    } catch { Add-CollectionWarning ('Raccolta ACPICA non completa: ' + $_.Exception.Message) }
    finally { Remove-Item -LiteralPath $scratch -Recurse -Force -ErrorAction SilentlyContinue }

    foreach ($entry in @($tableIds | Where-Object {$wantedSignatures -contains $_.Signature} | Sort-Object Signature -Unique)) {
        if (Get-ChildItem -LiteralPath $acpiOut -Filter ($entry.Signature + '*.aml')) { continue }
        $file = $null
        try {
            $size = [LenovoFirmwareReader]::GetSystemFirmwareTable([LenovoFirmwareReader]::Acpi, $entry.Id, $null, 0)
            if ($size -lt 36 -or $size -gt 16777216) { throw 'Dimensione ACPI non valida.' }
            $data = [byte[]]::new([int]$size)
            $read = [LenovoFirmwareReader]::GetSystemFirmwareTable([LenovoFirmwareReader]::Acpi, $entry.Id, $data, $size)
            if ($read -ne $size) { throw 'Lettura ACPI incompleta.' }
            $file = Join-Path $acpiOut ($entry.Signature + '.aml')
            [System.IO.File]::WriteAllBytes($file, $data)
            $null = Get-AcpiHeader $file
        } catch {
            if ($file -and (Test-Path -LiteralPath $file)) { Remove-Item -LiteralPath $file -Force }
            Add-CollectionWarning ('Ripiego ACPI non riuscito per ' + $entry.Signature)
        }
    }

    $tables = @(foreach ($file in @(Get-ChildItem -LiteralPath $acpiOut -Filter '*.aml')) {
        $h = Get-AcpiHeader $file.FullName
        [pscustomobject]@{File=$file.Name;Signature=$h.Signature;Length=$h.Length;OemId=$h.OemId;OemTableId=$h.OemTableId;Sha256=$h.Sha256}
    })
    $dsdtCount = @($tables | Where-Object Signature -eq 'DSDT').Count
    $ssdtCount = @($tables | Where-Object Signature -eq 'SSDT').Count
    $ssdtDistinct = @($tables | Where-Object Signature -eq 'SSDT' | Select-Object -ExpandProperty Sha256 | Sort-Object -Unique).Count
    $expectedSsdt = if ($tableCounts.ContainsKey('SSDT')) { [int]$tableCounts['SSDT'] } else { 0 }
    $ssdtComplete = $expectedSsdt -gt 0 -and $ssdtDistinct -ge $expectedSsdt
    if ($dsdtCount -eq 0) { Add-CollectionWarning 'DSDT assente. Allegare comunque lo ZIP per scegliere il metodo successivo.' }
    if (-not $ssdtComplete) { Add-CollectionWarning 'SSDT complete non confermate. Il ripiego Windows legge solo la prima tabella per firma.' }
    if ($devices.Count -eq 0) { Add-CollectionWarning 'Nessun identificativo hardware esportato.' }
    Write-JsonFile (Join-Path $out 'acpi-manifest.json') ([ordered]@{Source=$acpiSource;EnumeratedCounts=$tableCounts;Tables=$tables})

    Write-Host '[4/4] Creazione dello ZIP'
    $status = [ordered]@{
        SchemaVersion = 1
        CollectorVersion = $collectionVersion
        CreatedUtc = [DateTime]::UtcNow.ToString('o')
        DeviceCount = $devices.Count
        AcpiTableCount = $tables.Count
        DsdtAvailable = $dsdtCount -gt 0
        SsdtEnumerated = $expectedSsdt
        SsdtExported = $ssdtCount
        SsdtDistinct = $ssdtDistinct
        AllEnumeratedSsdtExported = $ssdtComplete
        CollectionStatus = if ($warnings.Count -eq 0) {'OK'} else {'PARZIALE'}
        Warnings = @($warnings.ToArray())
        AcpiTool = $toolSpec
    }
    Write-JsonFile (Join-Path $out 'stato-raccolta.json') $status
    $summary = @(
        'LENOVO HACKINTOSH - RACCOLTA DATI',
        ('Stato: ' + $status.CollectionStatus),
        ('Dispositivi: ' + $devices.Count),
        ('DSDT: ' + $dsdtCount),
        ('SSDT esportate: ' + $ssdtCount + '; enumerate: ' + $expectedSsdt),
        '',
        'Allega lo ZIP nella chat del progetto, anche se la raccolta e parziale.',
        'Questi file non sono una EFI pronta da installare.',
        '',
        'Note:'
    ) + @($warnings.ToArray())
    [System.IO.File]::WriteAllLines((Join-Path $out 'LEGGIMI.txt'), [string[]]$summary, $utf8)
    $zip = $out + '.zip'
    Compress-Archive -LiteralPath $out -DestinationPath $zip -CompressionLevel Optimal
    Write-Host ('File pronto: ' + $zip) -ForegroundColor Green
    if (-not $NoOpenFolder) {
        Start-Process -FilePath 'explorer.exe' -ArgumentList ('/select,"{0}"' -f $zip)
        $null = Read-Host 'Premi Invio per chiudere'
    }
    exit 0
} catch {
    $message = 'Raccolta non completata: ' + $_.Exception.Message
    Write-Host $message -ForegroundColor Red
    try { [System.IO.File]::WriteAllText((Join-Path $kitRoot 'errore-avvio.txt'), $message, $utf8) } catch { }
    if (-not $NoOpenFolder) { $null = Read-Host 'Premi Invio per chiudere' }
    exit 1
}
