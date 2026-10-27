# Private unavailable-service observations

B8 observed two fresh Host unavailable calls after the original adapter failed.
Its cached counter was zero and its first bound failure remained the root
failure. The aggregate does not identify the unavailable callbacks. In
particular, the logged system-capability refusal returns directly from
`osRmCapRegisterSys` when `nvidia_caps_root` is null; it calls none of these Host
unavailable boundaries and the original system constructor treats it as nonfatal.

This profile adds diagnostics to the exact preceding B9 Host and Context
sources. It preserves the original central sequence: refusal observation,
atomic aggregate increment, second refusal observation. Private diagnostic
updates follow that sequence. Neither the original status nor its admission,
cleanup, ownership, Host snapshot layout or user protocol changes.

The new 72-byte private snapshot contains saturating atomic32 module-lifetime
totals, ten independent site counts and a site mask. A single successful
reservation winner writes the first `(site, service)` tuple, then release
publishes state2. Readers acquire that state and never inspect the tuple in
state0 or state1. This winner is the first diagnostic publisher, not a claim
about the causal first RM error. No production reset API exists.

| Site | Exact origin |
| --- | --- |
| 0 | External `s540GlobalRmRecordUnavailable(service)` entry |
| 1 | Host shutdown outside ordinary sleepable context |
| 2 | Host allocation outside ordinary sleepable context |
| 3 | Host free outside ordinary sleepable context |
| 4 | Host free permit refused |
| 5 | Physical free completion refused |
| 6 | Host snapshot outside ordinary sleepable context |
| 7 | Out-of-range service-mask registration |
| 8 | Null service name |
| 9 | Full service-name table |

Site0 is intentionally marked ambiguous. External raw service0 still combines
several callback sources; this profile does not manufacture a unique callback
name from that value. Invalid future internal site values conservatively map to
site0 without indexing outside the fixed array.

The pure getter uses the actual FirstTxn snapshot for the exact bound nv,
requires an ordinary current master thread and actual original-wrapper return
with no call in flight, then reads private atomic storage. Refusals leave output
untouched. The Context emits at most two scalar log records after the original
wrapper has returned. No logging, allocation, new lock, hardware operation or
Host snapshot occurs in the producer helper or the new getter.

`check.py` compiles and runs the complete actual transformed Host.cpp and the
actual inserted C logger with typed CPU endpoints. Controls cover all ten
origins, exact-nv/master/context/return refusals, unchanged output, pending first
publication, immutable first tuple, saturation, Host reopen persistence, the
unchanged refusal/aggregate ordering and eight concurrent writers. They run
plain and with fatal ASan/UBSan; ten behavior mutations must be rejected. The
strong FirstTxn implementation, Darwin kernel, RM and Lenovo hardware are not
executed by these CPU controls. Native cross-compilation and target evidence
remain separate milestones.
