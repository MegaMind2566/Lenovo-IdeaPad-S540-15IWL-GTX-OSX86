# Passive CPU sensor check

This standalone Intel macOS diagnostic reads 15 consecutive `powermetrics`
samples at a two-second interval. A single reader session helps distinguish an
intermittent CPU-temperature reading from a format rejected by the old filter.
It uses built-in Bash 3.2 and Apple utilities. No Xcode or dependency installation
is needed.

Extract the package into Downloads and run:

```bash
bash "$HOME/Downloads/S540-cpu-sensors/CHECK-SENSORS.command"
```

Leave the laptop idle during the reading. Administrator authentication is
requested once for the bounded Apple telemetry and loaded-driver readers.
There is no CPU workload, driver installation, EFI edit or settings change.
The `powermetrics` reader has a 40-second deadline. Its owning wrapper stops
both running and suspended reader children with TERM, then KILL. The `kmutil`
reader and the unprivileged SMCProcessor status reader each have a separate
ten-second deadline.

The private `SMC-SENSORS-*.zip` report is written to the Desktop. Only selected
CPU, power, frequency, thermal-pressure and fan scalars are retained. Relevant
loaded Lilu, VirtualSMC, SMCProcessor and SMCBatteryManager bundle IDs and numeric
versions are included; kernel addresses, UUIDs, process lists and system logs
are discarded.
The runtime state and numeric VersionInfo of the verified `SMCProcessor`
IORegistry class are filtered separately; no registry IDs or property payloads
are retained. A nonnumeric VersionInfo is reported as present with its payload
omitted. This class does not expose actual temperature values in its registry
properties.

Each recognized sample reports valid, missing, rejected and duplicate
CPU-temperature counts. Signed or scientific numbers with an explicit Celsius
unit are retained. A single finite value above 0 and at most 110 Celsius is
classified as valid. Exact `nan`, `N/A` and signed `inf` tokens are recorded as
unavailable; other payload is replaced by a fixed diagnostic category. Sample
timestamps and arbitrary strings are omitted. If sample headers are not
recognized, the report explicitly says completeness cannot be assessed.

This is a passive diagnostic. It does not establish sustained-load cooling,
fan control, or the cause of an unavailable SMC key. The previous CPU workload
temperature guard remains unchanged.
