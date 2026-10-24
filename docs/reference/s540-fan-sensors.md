# S540 fans — accepted status and historical RPM investigation

Updated 24 October 2026. **Fans are working, as confirmed by the user; RPM telemetry is not readable in the current macOS configuration.** The user accepted this limitation and closed fan investigation for v0.3.0. No further DSDT collection, laptop tests or sensor-driver changes are requested for this release, and fan investigation no longer holds publication.

The historical passive check exposed CPU temperatures through VirtualSMC/SMCProcessor 1.3.8, but no SMCSuperIO service or fan/RPM line. The three powermetrics SMC samples reported 58, 60 and 59 degrees C. This established unavailable telemetry; it did not measure zero RPM or diagnose a physical fan failure. The working internal non-NVIDIA EFI, audio and S540 Tasti were preserved. No EC scanning, fan-control writes or experimental sensor driver was applied.

## Primary implementation references

- [Linux yogafan.c](https://github.com/torvalds/linux/blob/5b0764a53235d3c77e1ed674e836e1b3fe1a4b1f/drivers/hwmon/yogafan.c) uses ACPI integer objects for supported models. Generic IdeaPad examples name FAN0 and scale their value by 100; other paths/scales differ. There is no verified 81SW mapping in these findings. Our previously recorded EC path is LPCB.H_EC, so another model's LPC0.EC0 path is not a ready patch.
- [YogaSMC IdeaSMC](https://github.com/zhen-zen/YogaSMC/blob/299907b359c4d323e8c45ecc91e88c2a87b6082d/YogaSMC/YogaSMC/IdeaSMC.cpp) supports fan queries when Game Zone WMI is present. Its GUID is 887B54E3-DDDC-4B2C-8B88-68A26A8835D0. Presence in the source laptop's firmware was not established. No second full VPC driver was loaded alongside the working S540 Tasti.
- [VirtualSMC EC mapping](https://github.com/acidanthera/VirtualSMC/blob/master/Docs/EmbeddedControllers.md) requires hardware-specific interpretation. ThinkPad offsets and another manufacturer's scaling must not be copied into this laptop.

The IdeaPad VPC command named R_FAN in Linux exposes a fan *mode*, not an RPM tachometer. It is not evidence for an F0Ac implementation.

## Historical firmware evidence and collectors

The earlier private DSDT had SHA-256 5139a06fd931e15c7655046d79e67a36d63cdd626fdea3393e3482a59ca70f56. It was not retained in the working files during this investigation. A macOS collector was prepared to export only DSDT/SSDT data already published in IORegistry, using the same AppleACPIPlatformExpert/ACPI Tables property described by [osquery's primary implementation](https://github.com/osquery/osquery/blob/master/osquery/tables/system/darwin/acpi_tables.cpp).

The retained [macOS collector](../../packages/fan-readonly/RACCOGLI-ACPI.command) performs no ACPI method execution or EC access. It excludes other ACPI tables, including MSDM, and deletes its temporary full registry property capture. A missing property is reported as inconclusive, not hardware incompatibility. Its Bash syntax and a mocked selection/privacy flow were checked locally.

No model-specific RPM field, scaling or Game Zone interface was verified, and no telemetry implementation was added. The collectors remain historical tools; their presence is not a request to run them or a release prerequisite.

## macOS export result and unexecuted Windows fallback

The supplied S540-Ventole-ACPI.nzl3FL report contains no firmware tables. It reports the DSDT property not exposed by IORegistry and zero exported SSDTs. This is inconclusive for sensor support, not evidence that the firmware has no fan methods. No EC access was attempted.

The retained [Windows collector](../../packages/fan-readonly/windows/LEGGI-DSDT.ps1) was prepared to read only DSDT via the documented GetSystemFirmwareTable ACPI provider. It verifies signature, length, checksum and SHA-256 before writing a fresh report. It does not request MSDM/SMBIOS, read EC registers or install drivers. Its native API invocation on the Lenovo was not performed before the user closed this investigation. PowerShell parser, eight pure helper checks and the C# declaration/reflection contract passed locally; those are not a Windows hardware result.

The Windows API returns only the first table when multiple tables share a signature, so this tool does not claim to recover all SSDTs. The proposed offline search for EC fan objects and the Game Zone WMI GUID was not completed and is not scheduled for this release. [Microsoft API contract](https://learn.microsoft.com/en-us/windows/win32/api/sysinfoapi/nf-sysinfoapi-getsystemfirmwaretable).
