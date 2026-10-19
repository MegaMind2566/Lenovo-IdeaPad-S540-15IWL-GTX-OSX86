# Isolated first-transaction service integration

These are actual service overlays, separate from the production Owner and the
frozen prospective V3 profile. `prepare_services.py`, `prepare_timers.py` and
`prepare_context.py` reject changed source inputs and emit exact patches plus
input/output hashes. No caller readiness flags or stop-callback table exist.

The fixed binding associates the real device queue, published global queue and
timer registry with the exact original `nv_state_t` and immutable transaction
generation. Bind occurs before any queue item, RC arm or nano timer exists.
Partial bind is retained and cannot be replaced.

| Boundary | Actual operation and retained evidence |
| --- | --- |
| Work acceptance | Under the real queue guard, capacity is checked, then the strong record admits its lease immediately before irreversible ring publication. |
| Work entry | The genuine worker enters that exact lease before invoking the original action. Unknown/refused work is retained with its ticket. |
| Work completion | Context notes the public original wrapper return; the real queue separately notes action return after the action has actually returned. Freed work data is never re-read. |
| Timer identity | Event registration and each arm have separate opaque generations. Direct callback entry uses the genuinely admitted arm, not a foreign-thread auto-enrolment. |
| Timer completion | The original wrapper return is noted in the typed port. The actual Darwin backend calls the action-return hook after `timer->action()` returns. |
| Event destruction | Actual synchronous cancel precedes nonblocking event-borrower validation. Failed validation retains event/handle/registry ownership. A separate safe metadata tombstone records actual destruction. |
| Seal and drain | The original lock probe runs before blocking. The fixed endpoint stops real timers, seals both real queues and drains accepted callbacks through the real backend. Validation pulls locked state. |

`check_services.py` executes 20 queue boundary controls and 24 timer/endpoint
controls per plain and fatal ASan/UBSan/function variant. Record hooks and the
original lock probe in these controls are explicit dependency controls: they
test actual boundary placement and refusal retention, and do not authorize any
original callback policy. Five complete project/backend translation units also
compile for Mach-O with the pinned Apple SDK/full NVIDIA headers, Werror and a
4096-byte frame check. Strong-record integration has a separate report.

The candidate deliberately refuses an RC producer and replacement of an
already-pending timer arm until their exact policies are reviewed. Unknown
event/owner descriptors refuse and retain. Closing both queue admission paths
can refuse a causal descendant; that refusal must become sticky before caller
rollback, and is not a claim that all essential producer semantics are closed.
There is no final context/service release issuer: bound callback/text owners
remain retained, global unbind refuses, and void destruction cannot free them.

Admission still requires the actual original RM-semaphore exclusion/ownership
proof, complete first-error and scalar/fatal-path coverage, reviewed producer
descriptors, bounded PM cancellation and authentic final hardware/GSP stop.
The queue/timer drain is not hardware DMA cessation, PMstop is not a join, and
this candidate does not issue a DMA-stop receipt or enable original kernel RM.
