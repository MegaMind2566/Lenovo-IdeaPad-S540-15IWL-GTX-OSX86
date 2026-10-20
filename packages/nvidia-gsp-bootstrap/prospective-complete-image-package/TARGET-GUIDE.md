# Idle complete-image loader ABI check

This package checks whether the exact complete image can load and publish its
closed idle control service on the Lenovo target. It is a prerequisite to a
later original GPU entry test. It does not initialize RM or GSP, prepare a GPU
provider, register GPU power management, arm interrupts, perform device DMA or
test graphics acceleration.

The required target is Intel macOS 26.7.1, build 25G241, Darwin 25.6.0. The
controller independently reads the already published PCI registry identity
10DE:1F91, subsystem 17AA:3806, revision A1, display class 030000. It opens only
the idle control service and sends only the snapshot selector. It never sends
the original-entry request selector.

Obtain the packaging-attestation SHA256 from the independently published build
result. Compare the downloaded package with that result before running it.
Keep the existing test setup. The scripts do not install into system extension
directories, rebuild boot collections, clear quarantine, change system security
or bypass a loader refusal. An ad-hoc signature verifies package integrity; it
does not grant kernel trust or target-loader approval.

From the extracted package directory, run this explicit check:

```sh
sudo ./test-idle-loader.sh --attestation-sha256 PUBLISHED_SHA256 \
  --ack-idle-loader-only
```

The script verifies the signed package, exact target OS and Lenovo GPU registry
identity, and refuses an already loaded matching identifier. It creates a
temporary root-owned copy, invokes normal `kmutil load`, checks the loaded
identifier/UUID and closed idle snapshot, then always attempts normal unload.
Keep the entire printed report directory, including command output and rollback.

An accepted load command, matching UUID and valid idle snapshot are recorded as
an external idle loader ABI observation. The kernel snapshot's
`target_loader_admission_proven` remains zero. Every hardware/original-entry
admission field remains false. Success does not turn this package into an
RM/GSP initialization or acceleration test.

Read-only observations are available:

```sh
sudo ./report.sh --attestation-sha256 PUBLISHED_SHA256
```

If an earlier check left this exact image loaded, normal rollback is:

```sh
sudo ./rollback.sh --attestation-sha256 PUBLISHED_SHA256
```

Rollback first checks the identifier and exact image UUID. It refuses to unload
a different or ambiguous image. A normal unload failure is reported without
force or automatic reboot. Keep those logs before further action through the
usual test procedure.
