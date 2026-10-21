# Actual cancellation/endpoint acceptance ordering

This opt-in successor serializes producer acceptance against the genuine
cancellation record's `RevokeAt` publication reservation. It replaces four
project sources and the original TX source in the exact final operational
parent. It adds no translation unit and changes no existing cancellation
header ABI. The new typed companion declares six explicitly owned functions.

The shared control word has one nonrecursive `COMMIT_BUSY` reservation. Entry
requires the exact bound state and the actual current worker, enrolled callback
or authenticated IRQ scope. A single strong CAS compares phase, revocation and
publication together; contention refuses immediately, including an interrupt
of its holder. Unknown or unbound identities refuse rather than inheriting the
old cancellation check's permissive nonmatching-state behavior.

All four RC/nano arm sites route through one real timer endpoint wrapper.
The backend reserves before changing its arm state and invoking the actual
`enableInterrupt`; it retires only after that call genuinely returns. A failed
end keeps the reservation and truthful hardware obligations. Software ISR
acceptance closes on enable failure or end failure. The typed original GPU
bridge wraps genuine `msgqTxSubmitBuffers`, retaining the original submit
failure when both the endpoint and retirement fail.

New timer, IRQ and separately selected DMA BME-enable work requires a genuine
OPERATION origin. TX transport can use genuine CLEANUP until the existing fixed
deadline. The current cancellation record supplies that origin; the caller
cannot pass a cleanup Boolean. A second actual clock/deadline check after the
CAS prevents a preempted cleanup caller from obtaining a new usable token after
its deadline. Accepted endpoint work can still finish after that deadline.

Revocation never waits for an endpoint. Previously accepted work may physically
commit after cancellation publishes, and its busy reservation remains until
the real endpoint returns. Finish, unbind and cleanup transition refuse that
reservation in the same compared word. Diagnostic snapshots include payload
publication and retirement windows and never expose a lease token. Their
`origin` uses internal OPERATION=2/CLEANUP=4 bits, distinct from the existing
public phase enum; these values grant no authority.

## Local checks

```sh
python3 -B packages/nvidia-gsp-bootstrap/prospective-pm-revocation-closure/check.py \
  --base build/operational-successor-2 \
  --cc /path/to/clang --cxx /path/to/clang++ \
  --output /path/to/fresh-pm-controls
```

The checker executes the complete selected cancellation TU, its old IRQ scope
controls, the exact timer helper and backend arm body with the actual selected
Platform layout, and the original TX/msgq bodies with the typed GPU bridge.
Thread/clock and framework/provider endpoints and the independent IRQ record
authority are explicit fixtures. The cancellation record, enrollment and
commit state themselves are genuine implementations. Both ordinary and fatal
ASan/UBSan/function modes run; three negative production mutations must fail.
The natural cleanup clock endpoint observes the busy reservation before token
publication and expires the deadline between its two real checks. Forty-eight
pthread schedules race actual revocation with real commit entry. Separate IRQ
end-failure processes verify software admission closure, original endpoint
error precedence and retained hardware obligations.

`LOCAL-CONTROL-VALIDATION.json` binds the executed artifacts and sources. Full
KERNEL SDK compilation is owned by the combined child compiler and is recorded
separately; these CPU controls establish no target execution or native cache
eligibility.

## Remaining limits

This is acceptance ordering against actual cancellation publication. The power
protocol can record its earlier event before a delayed callback publishes that
cancellation; these two events are not made atomic. The original event time
still starts the unchanged thirty-second deadline. Callback duration, actual
hardware/firmware producer stop, posted PCIe write drain, total shutdown time,
stack capacity and framework headroom remain separate unproved obligations.
Neither zero commits nor retained memory is a hardware-stop receipt, release
permit or PM acknowledgement. Original/global/loader/hardware gates stay
closed. No CI, security, EFI or hardware action is requested.
