# Battery and sleep counters

Results received from the Tahoe desktop on 13 October 2026. The system is installed on the external USB Samsung 960 EVO; the EFI is on the OpenCore HDD. This page retains the data without changing any settings.

## Battery reading

`pmset -g batt` reports **AC Power**, an internal battery present, **100%** and **charged** status. The reported time is `0:00 remaining`. No sample on Battery Power was provided: switching to battery power, discharge and battery runtime have not yet been verified.

## System counters

| Counter from pmset -g stats | Value |
|---|---|
| Sleep Count | 1 |
| Dark Wake Count | 0 |
| User Wake Count | 1 |

These counters cover the current boot. They document one sleep event and one user wake event recorded by the system; they do not identify the test time or, by themselves, certify recovery of the panel, USB drives, networking and audio. Hibernation and extended sleep remain to be verified.

## Reported settings

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

`hibernatefile` is `/var/vm/sleepimage` for both power sources. The settings have not been changed. Sleep work is deferred: priority is given to the panel being off for approximately two minutes during boot, Bluetooth and Wi-Fi management.

## Reference

- [Apple pmset manual](https://keith.github.io/xcode-man-pages/pmset.1.html): meanings of readings, counters and settings.
