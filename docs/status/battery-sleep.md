# Battery and sleep status

Updated on **20 October 2026** for the working official EFI on the external Samsung 960 EVO. This page records observations; it does not change power settings.

## Verified results

| Area | Result | Evidence and limit |
|---|---|---|
| Battery reporting | Internal battery detected; switching from AC to Battery Power and discharging confirmed | User check on 14 October; the displayed 2 h 21 min was an OS estimate, not measured runtime |
| Battery health | Good, 296 cycles | 20 October system report; no design-capacity comparison is used to calculate wear |
| Full charge | 100%, fully charged; not charging; 60 W adapter connected | These readings are consistent with a full battery |
| Lid sleep and wake | Closing the lid sleeps; opening it resumes | User-confirmed ordinary use on 20 October |
| Native Wi-Fi recovery | Working after restart/sleep | User confirmation; the current native driver is recorded in [Boot and network](../guides/boot-network.md) |

The lid result closes the ordinary close/open check. No extra lid collector, power patch or repeat cycle is requested. It does not establish overnight drain, prolonged sleep reliability, measured battery autonomy or hibernation. Full peripheral recovery is claimed only where separately confirmed by the user.

## Earlier counters and measurements

The 13 October report recorded Sleep Count 1, User Wake Count 1 and Dark Wake Count 0. Those counters cover that earlier boot and do not identify a controlled cycle. The 20 October hardware collection preceded the user's later direct lid confirmation; absence of a new cycle in that collection does not contradict the subsequent result.

The earlier battery reading on AC was 100% and charged. After removing AC on 14 October, `pmset -g batt` reported Battery Power, discharging and an estimated 2:21 remaining. This establishes battery operation without turning the estimate into a runtime measurement.

## Configuration retained

The collected settings include `hibernatemode=3`, a one-minute system sleep timer and different display-sleep timers on AC and battery. These settings are observations, not recommended replacements. No power preference, NVRAM value, EFI argument or driver was changed for the lid confirmation. The USB boot disk remains part of the working setup.

SD and NVIDIA development are paused. The separate delivered removal of the residual NVMe block still awaits an explicit reboot confirmation and adds no battery or sleep claim. See [Hardware status](hardware.md).

## Reference

- [Apple pmset manual source](https://github.com/apple-oss-distributions/PowerManagement/blob/main/pmset/pmset.1): readings, counters and power-setting meanings.
