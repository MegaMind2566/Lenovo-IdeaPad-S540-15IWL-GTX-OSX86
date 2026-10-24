# S540 SD initialization trace

Userspace-only diagnostic for the retained BigSurSDXC 1.9.0 x86_64 binary
(UUID D2EAAA60-AF10-360F-B645-1592B9B3A804, executable SHA-256
`dfb316e5e4ce745da6dbbb7470af1720e6719741e2a900aff3b3114e35060bd7`).
The installed direct-match driver attaches to O2Micro `1217:8621`; the target
8 GB FAT32 card is readable under Windows but publishes no macOS IOMedia.

The program temporarily enables only the driver's trace bit, using its reviewed
16-byte binary sysctl protocol and retaining the full original 64-bit value.
It restores and verifies that value during ordinary/error/signal cleanup.
It does not install a driver or change EFI, ACPI, NVRAM, NVIDIA or pmset.
Existing foreground trace sessions are refused. A background trace state may
hand off to this short foreground session through the normal macOS ownership
mechanism; no other process is killed and no global reset/remove is issued.
The existing driver performs normal media insertion/initialization.

A removal event in the selected SD trace must agree with the slot's absent-card
state before reinsertion is requested. An inaccessible or wrong sysctl owner,
unknown trace schema, unavailable CLI or missing positive control yields an
inconclusive result, not a failed SD initialization claim.

Only selected SD event fields are retained. Command arguments, card responses,
CID/CSD, kernel pointers and unrelated system events are dropped. Nonzero SD
query returns can be handled by the driver, so this tool records the sequence
without calling the first nonzero event the definitive failure.

## Native validation

The separate `build-sd-init-trace.yml` workflow uses a standard public
`macos-15-intel` runner, one grouped job and one explicit SD request file.
It never changes the NVIDIA request files. Compilation, self-tests, synthetic
trace/CLI validation and target SD evidence are separate outcomes.

## Runtime scope

Only x86_64 Darwin 25 with the reviewed direct-match BigSurSDXC controller and
one corresponding slot is admitted. A successful trace collection does not
establish working media or guarantee that a patch exists.
