# S540HotkeysVPC 0.1.0 contract

## Identity and matching

- Kext: `S540HotkeysVPC.kext`; executable and IOService class: `S540HotkeysVPC`.
- Bundle identifier: `org.s540.HotkeysVPC`; version: `0.1.0`.
- Personality provider: `IOACPIPlatformDevice`; `IONameMatch`: `VPC2004`.
- Runtime requirements: ACPI name `VPC0`, `_CFG == 0xFE0D0014`, and `_CFG`, `VPCR`, `VPCW` objects present.
- Refuse an already opened provider, an observed competing IdeaVPC/YogaVPC/HotkeysVPC client, or failure to inspect clients.
  Provider open ownership is held until stop. The installer also excludes known competing VPC drivers.
- Runtime publishes exact `CFBundleIdentifier` on the service. No user client or writable `setProperties` interface exists.

## Firmware traffic

`VPCR(1)` reads command status; `VPCR(0)` reads data. `VPCW(1, command)` writes a command;
`VPCW(0, value)` writes data. Read commands are exactly `0x10`, `0x1A`, and `0x1D`.
The only control command is `0x1E`, with Boolean value `0` or `1`, through the internally authorized camera event path.
The read queries themselves use the command-register write required by the VPC protocol.

Every transaction checks an initially idle command register before writing; it never overwrites another command.
After command issue it accepts status zero (complete) or the exact issued command (busy), with 1ms deferred sleeps.
Polling and subsequent operations stop at a 200ms monotonic deadline. A synchronous AML call cannot be forcibly aborted:
the deadline prevents additional work after that call returns, rather than guaranteeing a hard upper bound for faulty AML.
Errors never cause an automatic command retry or compensating control write.

ACPI notification delivery uses `kIOACPIMessageDeviceNotification` with a pointer to the UInt32 code `0x80`.
The callback only increments counters and signals a manual `IOInterruptEventSource`; all AML is serialized on
the driver's private `IOWorkLoop`. There is no idle timer and no idle EC polling.

At load/wake, actions are disabled while `0x10/0x1A` drain old event bits, then `0x1D` establishes a camera baseline.
Notifications are counted even while actions are disabled. Acceptance is atomically enabled only when the notification
generation remains unchanged across that sequence. A changed generation causes another drain/baseline pass,
with at most four passes. An unquiet baseline faults without applying pending hotkeys.

Power requests stop accepting new events immediately. The PM callback returns a deferred 4s acknowledgement allowance;
the current serialized transaction can finish while the power domain remains on. The workloop then invalidates the camera
baseline, disables transport for sleep, and calls `acknowledgeSetPowerState`. Wake re-enables transport solely for the
drain/baseline sequence before accepting events. Stop fences the workloop before removing sources/PM/provider ownership;
no control action is initiated by stop.

## Camera bit 7

The exact target CFG advertises camera capability (bit19) and camera OSD (bit31). These are capability gates, not proof
of firmware toggle ownership. Camera behavior is a guarded integration inference requiring the final functional check.

For a bit7 event with valid camera baseline:

1. Read current camera power (`0x1D`), requiring Boolean 0/1.
2. A rapid repeat (<300ms quiet time) or a coalesced notification batch only updates the observed baseline, with no write.
   Every bit7 event extends the quiet period. This also observes any firmware toggle during a suppressed event.
3. If current differs from the baseline, accept the firmware's change and publish it without another toggle.
4. Otherwise issue `0x1E` with `current XOR 1`, then read `0x1D` and require matching readback.

An invalid camera payload or failed readback invalidates the baseline and disables camera writes until a fresh load/wake.
A failed camera payload read after command completion can disable just camera; command/status/write errors or timeout
poison the global protocol and stop all event acceptance until unload/reload. F4/F7 remain available for isolated camera
payload failure. A global fault is never reactivated by wake or properties.

## Registry Snapshot schema 1

Consumers read **one `Snapshot` dictionary** using `IORegistryEntryCreateCFProperty`. Dictionaries/arrays already published
are never mutated; a later cycle replaces the entire property. Top-level aliases exist for installer diagnostics only.
Each nonzero event mask is inserted once, after camera work/readback, with a monotonically increasing sequence.

| Field | Type | Meaning |
|---|---|---|
| `Schema` | number32 | `1` |
| `Version` | string | `0.1.0` |
| `State` | string | `Ready`, `Fault`, or `Stopping` |
| `Ready` | bool | Actions accepted, awake, no fault, not stopping |
| `Awake` | bool | Requested device power state |
| `CFG` | number32 | Exact verified firmware CFG |
| `EventSequence` | number64 | Latest emitted nonzero-mask sequence |
| `EventRing` | array | At most32 ordered immutable records `{seq:number64, mask:number32, time_ns:number64}` |
| `NotifyCount` | number64 | Accepted/coalesced notifications processed |
| `QueryCount` | number64 | Issued query/control transaction attempts |
| `QueryFailureCount` | number64 | Reported protocol/camera/publication failure count |
| `ErrorCode` | number32 | Last global failure code, zero until a global fault |
| `LastIOReturn` | number32 | Last ACPI call return code |
| `LastMask` | number32 | Last queried event mask, including zero |
| `CameraState` | number32 | `0` off, `1` on, or `0xFFFFFFFF` unknown |
| `LastCameraResult` | number32 | Values below |
| `CameraErrorCode` | number32 | Camera transaction error code |
| `CameraBaselineValid` | bool | A valid Boolean camera baseline exists |
| `CameraEnabled` | bool | Camera feature remains enabled |
| `BaselineMask` | number32 | Last discarded load/wake mask |

Result values: `0` never requested; `1` unsupported; `2` host change verified; `3` repeated/coalesced event observed without
write; `4` invalid Boolean camera state; `5` readback mismatch; `6` protocol failure; `7` firmware change observed without write.

Error values: `0` OK; `1` invalid command; `2` stopped; `3` status read failure; `4` command/data write failure;
`5` busy before command; `6` unexpected command status; `7` timeout; `8` payload outside byte range;
`9` allocation/publication failure; `10` notification overflow; `11` sequence overflow; `12` completed-command payload read failure;
`13` baseline never became quiet.

Top-level aliases are `Ready`, `Version`, `State`, `EventSequence`, `EventRing`, `CFG`, `QueryFailureCount`, `LastCameraResult`,
and `CameraState`. On publication failure the old `Snapshot` is removed and top-level `Ready` is false.
No arbitrary ACPI/register contents, key text, or personally identifying system data are published.

The companion binds exact class+bundle identity and schema, samples the current sequence on startup without replay,
uses the IORegistry entry ID as a load epoch, and rejects gaps beyond the retained ring rather than applying stale actions.
Reading cached registry properties every200ms causes no firmware query.

## Host verification and build boundary

`c++ -std=c++14 -Wall -Wextra -Werror tests/ProtocolCoreTests.cpp -o ProtocolCoreTests && ./ProtocolCoreTests`
checks the closed command capability, exact register transcripts, zero events, failure/timeout termination,
power cancellation classification, bounded arithmetic, and the pure camera decision/debounce policy.
It does not test IOACPI delivery, macOS kernel linkage, target camera ownership, or target sleep behavior.

Native x86_64 macOS build uses pinned MacKernelSDK `3f750085caa17ec3a7880f11c11bf4f48cd6a164`, C++14,
standard IOKit module-start glue, and explicit IOACPIFamily/KPI dependencies in `Info.plist`.
