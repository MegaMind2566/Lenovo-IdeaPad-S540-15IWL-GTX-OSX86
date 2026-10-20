# CPU and thermal observations

## Current status: 20 October 2026

The official Samsung EFI displays the correct Intel Core i7-8565U name. The current report retains four cores/eight logical processors and an active X86PlatformPlugin. The naming correction does not change CPU frequency, voltage or power limits. VirtualSMC, SMCProcessor and SMCBatteryManager remain in the working configuration.

The measurements below are historical observations from 14 October, not new thermal tests of the later naming or NVMe-cleanup config. They show a power-management response and readable continuous temperature telemetry. Fan RPM, sustained-load cooling and measured battery runtime remain outside those results. No new stress test, sensor patch or collector is requested. SD and NVIDIA development are paused.

## Historical measurement session: 14 October 2026

Reported system: macOS 26.7.1 build 25G241, Intel Core i7-8565U, AC power.

## Observed response

| Phase | CPU die temperature | Estimated Intel package power | Reported average system frequency |
|---|---|---|---|
| Idle | 54 °C | 1.89–2.17 W | 1.45–1.62 GHz |
| Brief CPU load | No valid reading retained | 43.83 W | 3.62 GHz |
| Recovery | 57 → 56 → 55 °C | 1.94–2.18 W | 1.49–1.68 GHz |

Four physical cores and eight logical processors are present. X86PlatformPlugin is registered, matched and active. Frequency and estimated package power rise with the workload and return toward their initial values after it stops. This confirms an observable CPU power-management response.

## Incomplete thermal measurement

The load ended after three seconds because a valid temperature reading was unavailable. It did not stop because the 85 °C operating cutoff had been observed. The recovery reading of 57 °C is not a measured load peak.

Thermal pressure was reported as Nominal throughout the collected samples. Fifteen unavailable SMC keys were reported in every sample, including those with valid temperatures. Fan RPM was not available. These observations do not establish sustained-load cooling, the absence of throttling, battery autonomy or NVIDIA electrical power-off.

The collector retained no valid CPU temperature line in the load sample. The original unfiltered stream was not saved, so a missing source reading and a rejected format cannot be distinguished retrospectively. The historical gap remains unexplained; the later continuous-reader results below did retain valid temperatures. No immediate stress test is requested.

## Existing configuration review

The previously supplied EFI enables VirtualSMC, SMCProcessor and SMCBatteryManager 1.3.8 with Darwin 24.0.0–25.99.99 bounds. Darwin 25.6.0 is inside those bounds. This is a configuration review, not proof of the exact extensions loaded during the new report.

The working configuration is retained. No CPU, BIOS, power-limit or graphics patch is inferred from the missing sample. Original reports and private EFI identity data are excluded from the repository.

## Passive sensor follow-up

The [standalone sensor collector](../../packages/cpu-sensors/README.md) reads fifteen consecutive two-second samples without starting a workload. It records filtered loaded-driver versions and the SMCProcessor runtime state. Temperature diagnostics distinguish a missing label, a rejected or unavailable value, duplicate labels and a single accepted reading. Unknown payloads and unrelated raw telemetry are discarded.

The driver review used VirtualSMC 1.3.8 at commit `b15991dd87e36a102bf159ea56490e3126245590`. SMCProcessor registers temperature keys from CPU capability bits and encodes a cached integer temperature as `sp78`; its key reader has no NaN or unavailable-temperature branch. The periodic MSR update retains its previous cached temperature when the valid bit is absent. These source observations do not establish which key powermetrics requests or why the earlier sample contained no accepted temperature. A new driver, generic fan plugin or EFI patch is not justified by that sample.

### Passive report result: October 14, 2026

The continuous reader completed successfully with fifteen samples, each containing one valid numeric CPU temperature. No temperature labels were missing, rejected or duplicated.

| Item | Observed result |
|---|---|
| CPU die temperature | 45–48 °C; mean 46.47 °C |
| Estimated Intel package power | 1.02–2.72 W; median 1.05 W |
| Reported average system frequency | 0.883–1.855 GHz; median 0.913 GHz |
| Thermal pressure | Nominal in all fifteen samples |
| Loaded sensor drivers | VirtualSMC, SMCProcessor and SMCBatteryManager 1.3.8; Lilu 1.7.2 |
| Reader completion | kmutil, IORegistry and powermetrics exit status 0 |
| Fan RPM | Not reported |

This establishes complete temperature readings during this passive session and low estimated Intel package power in the observed idle conditions. It does not explain the earlier workload temperature gap or verify sustained-load cooling, battery runtime, NVIDIA power-off or total laptop power.

The SMCProcessor service-header filter did not observe the complete registered/matched/active combination. That output is not proof of an inactive driver: kmutil confirms the loaded extension, the VersionInfo property is present, and all temperature samples are valid. No driver or EFI change is inferred.

Invalid-key warning markers remain: fifteen before the first sample and ninety-eight within sample groups. The report merges stdout and stderr, so their placement cannot identify individual keys or establish an improvement relative to the earlier separate reader sessions. Warnings coexist with valid CPU temperatures.

The current configuration is retained. Independent boot from the external Samsung, USB-C SuperSpeed in both orientations, and USB-A SuperSpeed/file reads on both connectors have since been confirmed. Reliable workload temperature measurement remains open.

### Reviewed primary source

- [SMCProcessor registration and periodic update](https://github.com/acidanthera/VirtualSMC/blob/b15991dd87e36a102bf159ea56490e3126245590/Sensors/SMCProcessor/SMCProcessor.cpp)
- [Temperature key implementation](https://github.com/acidanthera/VirtualSMC/blob/b15991dd87e36a102bf159ea56490e3126245590/Sensors/SMCProcessor/KeyImplementations.cpp)
- [Sensor plugin scope](https://github.com/acidanthera/VirtualSMC/blob/b15991dd87e36a102bf159ea56490e3126245590/Docs/SensorInfo.md)

## Continuous reader during desktop activity

The original CPU collector restarts `powermetrics -n 1` for each sample and accepts only a strict decimal temperature line. The later passive collector uses one continuous session and records missing, rejected and duplicate temperature categories. These implementation differences do not retrospectively explain the original missing load reading.

The follow-up reused the existing [sensor collector](../../packages/cpu-sensors/README.md) after requesting about 15–20 seconds of normal browser activity within its thirty-second collection. The idle-only prompt to leave the laptop untouched did not apply. The collector starts no artificial CPU workers and changes no EFI, driver or power setting. The report does not separately timestamp the browser activity.

### Activity report result: October 14, 2026

| Item | Observed result |
|---|---|
| Accepted CPU temperatures | 15 of 15; no missing, rejected or duplicate readings |
| CPU die temperature | 57–82 °C; median 59 °C; mean 62.33 °C |
| Estimated Intel package power | 3.03–35.62 W; median 4.60 W |
| Reported average system frequency | 1.230–3.436 GHz; median 1.507 GHz |
| Highest retained sample | Sample 4: 82 °C, 35.62 W and 3436.41 MHz |
| Following / final temperature | 59 °C in sample 5 / 57 °C in sample 15 |
| Thermal pressure | Nominal in every sample |
| Loaded sensor drivers | VirtualSMC, SMCProcessor and SMCBatteryManager 1.3.8; Lilu 1.7.2 |
| Reader completion | kmutil, IORegistry and powermetrics exit status 0 |
| Fan RPM | Not reported |

Compared with the earlier idle report (45–48 °C, median estimated package power 1.05 W and average system frequency 0.913 GHz), this session contains a clear activity/power rise while every CPU temperature remains readable. The original missing load sample is not reproduced. Its original cause is still unknown; the filter's incomplete SMCProcessor service-state observation does not establish a driver failure.

The highest retained temperature is a sampled value, not a guarantee of the true peak between readings. The last seven temperatures are 57–59 °C as estimated package power falls to 3.03–4.60 W. This is not a sustained workload or proof that thermal throttling never occurs. NVIDIA electrical power-off, fan telemetry, battery runtime and total laptop power remain unverified by this report.

There are fifteen startup warning markers and ninety-eight within sample groups, as in the idle session. These counts do not identify individual unavailable keys or justify an SMC patch. The configuration is retained; no immediate repeat sensor collection or artificial stress is required by this result.
