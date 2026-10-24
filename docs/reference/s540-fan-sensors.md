# S540 fan RPM investigation

Updated 24 October 2026. The source laptop exposes CPU temperatures through VirtualSMC/SMCProcessor 1.3.8, but the current configuration has no SMCSuperIO service and its three powermetrics SMC samples report 58, 60 and 59 degrees C without a fan/RPM line. This establishes unavailable telemetry in that configuration; it does not establish physical fan failure.

The user requested further investigation before the next public EFI milestone. The working internal non-NVIDIA EFI, audio and S540 Tasti remain unchanged. No EC scanning, fan-control writes or experimental sensor driver has been applied.

## Primary implementation references

- [Linux yogafan.c](https://github.com/torvalds/linux/blob/5b0764a53235d3c77e1ed674e836e1b3fe1a4b1f/drivers/hwmon/yogafan.c) uses ACPI integer objects for supported models. Generic IdeaPad examples name FAN0 and scale their value by 100; other paths/scales differ. There is no verified 81SW mapping in these findings. Our previously recorded EC path is LPCB.H_EC, so another model's LPC0.EC0 path is not a ready patch.
- [YogaSMC IdeaSMC](https://github.com/zhen-zen/YogaSMC/blob/299907b359c4d323e8c45ecc91e88c2a87b6082d/YogaSMC/YogaSMC/IdeaSMC.cpp) supports fan queries when Game Zone WMI is present. Its GUID is 887B54E3-DDDC-4B2C-8B88-68A26A8835D0. Presence in the source laptop's firmware still needs verification. Loading a second full VPC driver alongside the working S540 Tasti is not part of this plan.
- [VirtualSMC EC mapping](https://github.com/acidanthera/VirtualSMC/blob/master/Docs/EmbeddedControllers.md) requires hardware-specific interpretation. ThinkPad offsets and another manufacturer's scaling must not be copied into this laptop.

The IdeaPad VPC command named R_FAN in Linux exposes a fan *mode*, not an RPM tachometer. It is not evidence for an F0Ac implementation.

## Required firmware evidence

The earlier private DSDT had SHA-256 5139a06fd931e15c7655046d79e67a36d63cdd626fdea3393e3482a59ca70f56. It is not currently retained in the working files. The next collection exports only DSDT/SSDT data already published in macOS IORegistry, using the same AppleACPIPlatformExpert/ACPI Tables property described by [osquery's primary implementation](https://github.com/osquery/osquery/blob/master/osquery/tables/system/darwin/acpi_tables.cpp).

The [collector](../../packages/fan-readonly/RACCOGLI-ACPI.command) performs no ACPI method execution or EC access. It excludes other ACPI tables, including MSDM, and deletes its temporary full registry property capture. A missing property is reported as inconclusive, not hardware incompatibility. Its Bash syntax and a mocked selection/privacy flow were checked locally; native export remains pending. The resulting firmware data remains private.

Candidate fan fields/methods and the Game Zone GUID must be verified in the actual DSDT/SSDT before an isolated telemetry implementation is prepared. The v0.3.0 non-NVIDIA package and its six release assets are otherwise prepared and reviewed; publication is held for this requested investigation.
