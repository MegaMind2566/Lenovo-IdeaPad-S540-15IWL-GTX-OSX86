# Battery and sleep status

Updated on **24 October 2026**. The current official non-NVIDIA EFI boots internally; dated observations below retain their original source/configuration scope. This page records results and does not change power settings.

## Verified results

| Area | Result | Evidence and limit |
|---|---|---|
| Battery reporting | Internal battery detected; switching from AC to Battery Power and discharging confirmed | User check on 14 October; the displayed 2 h 21 min was an OS estimate, not measured runtime |
| Battery health | Good, 296 cycles | 20 October system report; no design-capacity comparison is used to calculate wear |
| Full charge | 100%, fully charged; not charging; 60 W adapter connected | These readings are consistent with a full battery |
| Lid sleep and wake | Closing the lid sleeps; opening it resumes | User-confirmed ordinary use on 20 October |
| Native Wi-Fi recovery | Working after restart/sleep | User confirmation; the current native driver is recorded in [Boot and network](../guides/boot-network.md) |
| Bluetooth headset after sleep/wake | Headset reconnected; playback and the headset microphone work after waking | User-confirmed on 24 October 2026; automatic versus manual reconnection was not specified |
| Internal audio after sleep/wake and Bluetooth disconnection | Playback returns to the built-in speakers; a recording with the selected internal microphone works | User-confirmed on 24 October 2026 in the same wake session; no additional sleep cycle or prolonged standby was tested |

The lid result closes the ordinary close/open check. No extra lid collector, power patch or repeat cycle is requested. It does not establish overnight drain, prolonged sleep reliability, measured battery autonomy or hibernation. Full peripheral recovery is claimed only where separately confirmed by the user.

## Observed lid and idle cycles — 21 October 2026

The retained pmset log records clamshell sleep from 13:28:43 to 14:28:46: **3,603 seconds**, followed by `PWRB XDCI/Lid Open` wake. Its counters show one sleep, one user wake and zero DarkWake. A later idle cycle runs from 14:38:31 to 14:40:02: **91 seconds**, again followed by user/lid wake with zero DarkWake in that session. These close the tested ordinary lid/idle behavior; they do not measure calibrated standby drain, overnight reliability or hibernation.

## Low Power Mode under CPU load — 24 October 2026

The user requested a direct effect check after `pmset` showed `lowpowermode=0` on battery and AC. The battery preference was enabled with `pmset -b lowpowermode 1`; AC remained at 0.

The private report `S540-Risparmio.FE1EEI.zip` records macOS 26.7.1 (25G241), Intel Core i7-8565U, four physical cores and eight logical processors. One automatic OFF–ON–ON–OFF comparison used two `yes` workers per phase, 15 seconds without the artificial load for settling, 5 seconds of workload warmup and 15 one-second `powermetrics` samples per phase. The CPU sampler used `-a 0` to suppress additional average blocks.

| Phase | Battery Low Power Mode | Mean estimated Intel package power | Mean active system frequency | Accepted samples |
|---|---|---|---|---|
| 1 | Off | 36.453 W | 4002.0 MHz | 15 power / 15 frequency |
| 2 | On | 11.389 W | 2400.0 MHz | 15 power / 15 frequency |
| 3 | On | 11.427 W | 2400.0 MHz | 15 power / 15 frequency |
| 4 | Off | 34.429 W | 3892.3 MHz | 15 power / 15 frequency |

All four raw streams reproduce the summary, their sampler stderr files are empty, and each phase's active profile matches the requested setting. Battery snapshots show discharge at every recorded boundary. The before/after power-preference snapshots are byte-identical: battery Low Power Mode was restored to 1, AC stayed at 0, and the other recorded preferences were preserved. The `caffeinate` termination message is the collector stopping its own temporary sleep-prevention process during cleanup.

The OFF phases average 35.441 W and the ON phases 11.408 W: about **68% lower estimated package power in these workload windows**, with a repeatable active-frequency change toward 2.4 GHz. Returning to OFF restores the higher power/frequency response. This confirms a real CPU/package response to Low Power Mode on this installation.

The scope is a short fixed-duration workload, not equal completed work. Intel package estimates include CPU cores, integrated graphics and system-agent logic; they are not total laptop watts, a calibrated external power measurement, measured battery autonomy or an energy-efficiency result. Reported frequency is during active execution. The result does not predict a 68% reduction in ordinary battery drain.

Thermal pressure is Nominal throughout, but the detailed OFF streams contain `CPU LIMIT THERMAL` in 2/15 and 5/15 samples respectively, alongside other power/performance-limit flags. These flags are absent in both ON streams. The brief OFF averages include changes in boost and limiting; Nominal pressure and `pmset` limits of 100 do not establish an absence of throttling. CPU die temperature and fan speed were not collected by this test. No further stress test, EFI change or power-limit patch is requested from this result.

## User assessment — 24 October 2026

The user reports modest battery runtime and attributes it to an aged battery. This is a user-reported explanation, not a new capacity comparison or a measured system-power result. No further autonomy test or macOS power-setting change is requested on that basis. The earlier Good-health/296-cycle inventory remains historical evidence and does not quantify present wear.

## Earlier counters and measurements

The 13 October report recorded Sleep Count 1, User Wake Count 1 and Dark Wake Count 0. Those counters cover that earlier boot and do not identify a controlled cycle. The 20 October hardware collection preceded the user's later direct lid confirmation; absence of a new cycle in that collection does not contradict the subsequent result.

The earlier battery reading on AC was 100% and charged. After removing AC on 14 October, `pmset -g batt` reported Battery Power, discharging and an estimated 2:21 remaining. This establishes battery operation without turning the estimate into a runtime measurement.

## Configuration retained

The collected settings include `hibernatemode=3`, a one-minute system sleep timer and different display-sleep timers on AC and battery. These settings are observations, not recommended replacements. No power preference, NVRAM value, EFI argument or driver was changed for the lid confirmation. Those settings were captured during the earlier setup; the current official macOS boot is internal.

SD operation has since been user-confirmed from the internal non-NVIDIA EFI and is included in v0.3.0. NVIDIA remains disabled in that release; its experimental research is separate. Those later changes add no new autonomy, hibernation or prolonged-standby claim. See [Hardware status](hardware.md).

## Reference

- [Apple pmset manual source](https://github.com/apple-oss-distributions/PowerManagement/blob/main/pmset/pmset.1): readings, counters and power-setting meanings.
