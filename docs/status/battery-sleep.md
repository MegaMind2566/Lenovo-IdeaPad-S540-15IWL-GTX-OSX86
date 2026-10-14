# Battery and sleep counters

Results received from the Tahoe desktop on October 13–14, 2026. Tahoe and OpenCore now boot independently from the external USB Samsung 960 EVO after manual EFI transfer. This page retains the observations without changing settings.

## Battery reading

On October 13, `pmset -g batt` reported **AC Power**, an internal battery present, **100%** and **charged**, with `0:00 remaining`.

On October 14, after removing AC power, it reports:

| Item | Observed value |
|---|---|
| Power source | **Battery Power** |
| Internal battery | Present |
| Charge indicator | 100% |
| Status | **Discharging** |
| OS remaining-time estimate | 2 hours 21 minutes |

Basic battery operation and discharge reporting are confirmed. The displayed remaining time is an estimate at that moment, not measured runtime. The reading does not determine battery health, usable capacity, extended SSD stability or sleep recovery. Battery instance IDs are excluded.

## System counters

| Counter from pmset -g stats | Value |
|---|---|
| Sleep Count | 1 |
| Dark Wake Count | 0 |
| User Wake Count | 1 |

These counters cover the boot associated with the original October 13 report. They document one sleep event and one user wake event recorded by the system; they do not identify the test time or, by themselves, certify recovery of the panel, USB drives, networking and audio. Hibernation and extended sleep remain to be verified.

## Reported settings

These settings were collected on October 13 and were not reread with the new battery sample.

| Setting | Battery Power | AC Power |
|---|---:|---:|
| standbydelayhigh | 86400 | 86400 |
| standbydelaylow | 10800 | 10800 |
| standby | 1 | 1 |
| lowpowermode | 0 | 0 |
| proximitywake | 0 | 1 |
| hibernatemode | 3 | 3 |
| powernap | 0 | 1 |
| gpuswitch | 2 | 2 |
| ttyskeepawake | 1 | 1 |
| highstandbythreshold | 50 | 50 |
| displaysleep | 2 | 10 |
| sleep | 1 | 1 |
| lessbright | 1 | not reported |
| halfdim | 1 | 1 |
| tcpkeepalive | 1 | 1 |
| disksleep | 10 | 10 |
| womp | not reported | 1 |
| networkoversleep | not reported | 0 |

`hibernatefile` is `/var/vm/sleepimage` for both power sources. No settings are changed by this record. Sleep work remains deferred while remaining peripheral checks, storage reliability and power/thermal measurements take priority. The former panel delay, wireless reconnection and network switching are already resolved.

## Reference

- [Apple pmset manual](https://keith.github.io/xcode-man-pages/pmset.1.html): meanings of readings, counters and settings.
