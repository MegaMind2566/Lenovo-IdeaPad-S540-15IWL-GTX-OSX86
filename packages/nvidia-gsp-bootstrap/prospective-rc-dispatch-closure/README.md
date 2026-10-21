# Cooperative original 1Hz dispatch successor

This opt-in source profile closes concrete registration, list-lifecycle and
status-propagation gaps. It grants no original entry, interrupt admission,
hardware-stop receipt, physical release, PM acknowledgement or 30-second bound.
It edits only the two pinned original timer/OS wrapper TUs and the existing
private IRQ master-drain bridge. The generated OS header and existing ABI stay
unchanged. Two explicitly namespaced typed functions live in the original
`os_timer.c` TU; a package-owned header declares them.

The original first-registration path discarded `tmrEventScheduleRelSec` failure
and linked a callback anyway. The successor returns the actual arm failure
before linking or consuming its free-table entry. Once an arm succeeds, it
completes the genuine registration: revocation racing the timer arm is not
relabeled as an unsuccessful registration. There is no shared revoke/arm commit
guard, so this does not prove that no arm can commit concurrently with revocation.

The original dispatcher allowed callbacks to change the list, then searched by
entry pointer. A self-removing callback could leave that pointer on the free
list; same-slot reuse also defeats pointer identity. The successor increments a
permanent atomic mutation serial before each actual list mutation. If a void
callback changes any registration, dispatch returns a sticky refusal immediately
after it genuinely returns. It never dereferences that stale slot or treats a
replacement registration as completed. Actual remaining registrations stay
linked, and the pending bit stays set. This conservatively quarantines benign
mutations too; there is no automatic replay or fabricated callback completion.
The serial detects lifecycle changes and is not a replacement for the original
device-lock exclusion. Saturation or a failed single CAS refuses further work.

Bookkeeping visits at most the actual 36-entry table, validates table membership
and rejects repeat visits before executing a cyclic entry twice. Cancellation
and existing first-record failure are checked between genuine callback returns.
A returned oneshot is retired exactly once before consuming a later cancel;
unvisited work remains registered. Low power, lock refusal, cancellation and
mutation cannot clear the real pending bit. Both legacy wrappers preserve their
C ABI; the typed RC wrapper and master drain consume the actual status. The
PTIMER target stops rearming after observed failure. Existing lock, semaphore,
thread-state and TLS cleanup remains in the original path.

`osDestroy1HzCallbacks` now obtains the existing record-owned backend release
permit before destroying the timer or clearing any list metadata. A retained
epoch refuses that permit, preserving all three pointers and their payload
obligations. Pre-epoch destruction uses the real permit scope. No successful
software drain is interpreted as hardware quiescence.

`CALLBACK-INVENTORY.json` records all 14 registration sites in the 1,543 original
C files, their exact source hashes, entry conditions and remaining transitive
bounds. All registrations are repeating callbacks. TU117 positively enables the
BIF existence checker, which can enter GPU-lost reset/log/event/disconnect work.
Successful GSP initialization can register log polling; periodic health checking
depends on actual registry state. Their callback bodies, decoder/output paths
and fatal-timeout work have no proven common wall-clock bound. Three callbacks
have generated TU117 exclusions; other conditional producers require their real
source conditions or closed ingress proof. The inventory is evidence, never a
callback whitelist or an execution capability.

Local validation passed 263 checks in 20 separate native processes and the same
263 checks with fatal ASan, UBSan and function sanitization. These execute the
complete exact transformed original `os_timer.c` body and the genuine composed
cancellation implementation with real table registration/removal and callback
targets. Controls cover normal repeat/oneshot completion, cancellation before
and during dispatch, exact cleanup deadline expiry, self-removal, same-slot ABA,
insertion, full-table and cycle handling, arm/rearm failures, legacy pending-bit
behavior, low power, lock cleanup, foreign identity and accepted-arm/revoke race.
GPU power, lock, timer and clock endpoints, and first-record observation/release
boundaries are fixtures. They do not attest an actual master/lease, timer backend
or physical release. Five source contracts pass. Both complete changed original
TUs independently crosscompile to x86_64 Mach-O with `-mkernel`, `KERNEL`,
`__KERNEL__`, the original kernel ABI and the 4096-byte frame check; maximum
recorded frames are in `LOCAL-CONTROL-VALIDATION.json`.

The integrated bridge compile and strong-record composition remain part of the
root integration receipt. No complete 1100-TU native rebuild, final link, kernel
execution, actual callback, GSP transaction, PM drain or hardware stop is claimed
here. The hard 30-second PM proof remains false: a check before an arbitrary void
callback cannot preempt or bound the body already entered. Callback transitive
bounds and the existing hardware-stop receipt blocker must be resolved before
admission can change.
