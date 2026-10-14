# CPU and thermal observations

October 14, 2026, macOS 26.7.1 build 25G241, Intel Core i7-8565U, AC power.

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

The collector retained no valid CPU temperature line in the load sample. The original unfiltered stream was not saved, so a missing source reading and a rejected format cannot be distinguished retrospectively. Further immediate stress is not required; sensor-read reliability remains the next diagnostic issue.

## Existing configuration review

The previously supplied EFI enables VirtualSMC, SMCProcessor and SMCBatteryManager 1.3.8 with Darwin 24.0.0–25.99.99 bounds. Darwin 25.6.0 is inside those bounds. This is a configuration review, not proof of the exact extensions loaded during the new report.

The working configuration is retained. No CPU, BIOS, power-limit or graphics patch is inferred from the missing sample. Original reports and private EFI identity data are excluded from the repository.
