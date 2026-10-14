# CPU, temperature and power check

Run on the Intel S540 from the installed macOS desktop. Connect the charger, close busy apps and put the laptop on a firm surface. Extract the package into Downloads, then run:

```bash
bash "$HOME/Downloads/S540-cpu-thermal/CHECK-CPU.command"
```

Enter the administrator password once. The command records idle samples, runs a CPU load for up to **20 seconds**, and records recovery samples. It creates **CPU-THERMAL-….zip** on the Desktop. Attach that ZIP in the chat. No developer tools or additional applications are needed.

The load uses at most eight workers. A separate supervisor owns their processes and stops them when the deadline expires, the parent exits, or the check requests a stop. It also stops independently if the latest temperature is missing, malformed, at least 85 °C, or older than four seconds. It sends TERM, then KILL to any remaining owned workers. Ctrl+C requests the same cleanup. The load is skipped unless every idle sample contains one valid CPU die temperature below 85 °C. This is a conservative operating cutoff for this check, **not** a manufacturer temperature limit. The cutoff is evaluated between samples, rather than continuously. Each Apple sampler process also has an independent four-second timeout.

The command checks the installed `powermetrics --help` before selecting the advertised `cpu_power`, `smc` and `thermal` samplers. `thermal` reports pressure; it does not replace a CPU temperature reading. Only recognized scalar temperature, frequency, package-power, fan and thermal-limit lines are saved. Missing measurements are reported as unavailable. The privileged wrapper only runs Apple's `powermetrics` and stops its owned process on timeout or interruption. The command makes no EFI, driver, firmware, power-setting or fan-control changes.

The report also includes the CPU model, physical/logical core counts, macOS version/build, power source and whether X86PlatformPlugin is registered, matched and active. It excludes process lists, usernames, device serials and full IORegistry dumps. Intel package power estimates cover CPUs, integrated graphics and system agent; they are not the whole laptop's power consumption. This short check does not certify cooling under a sustained workload or battery autonomy.

Apple documents `powermetrics` in its [Energy Efficiency Guide](https://developer.apple.com/library/archive/documentation/Performance/Conceptual/power_efficiency_guidelines_osx/MonitoringEnergyUsage.html). Sampler availability and options are taken from the help shipped on the actual laptop; the local `man powermetrics` supplies the matching manual.

`bash CHECK-CPU.command --self-test` runs only deterministic filter, sampler-discovery and temperature-guard fixtures. It does not probe the system or start CPU workers.
