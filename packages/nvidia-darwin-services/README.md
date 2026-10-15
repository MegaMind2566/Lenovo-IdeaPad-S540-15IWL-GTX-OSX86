# Darwin services for the full NVIDIA Resource Manager

This component provides real host services for the separately namespaced full
NVIDIA RM build. It does not replace or reinterpret any v9 OS object. Public C
symbols use `s540Darwin_`; the RM facade explicitly bridges its own prefixed ABI
to these functions. NVIDIA interface signatures and the original Linux behavior
are pinned in [PROVENANCE.json](PROVENANCE.json).

## Implemented behavior

| Service | Darwin implementation and contract |
| --- | --- |
| Mutex | Dynamically allocated binary semaphore; ordinary-thread blocking/try acquisition, nonrecursive; balanced release. |
| Spinlock | `IOSimpleLock`, preserving and restoring the full interrupt-state token. |
| Semaphore | Counting semaphore with interrupt-safe try/release and atomic register-before-sleep waits. Overflow is refused. |
| Reader/writer lock | Multiple concurrent readers or one writer, queued-writer preference, real blocking waits and nonblocking conditional acquisition. |
| Wait queue | Sticky `complete_all` semantics: wake releases every waiter and remains set. Interruptible waits use `THREAD_ABORTSAFE`. |
| Work queue | Real ordinary-context callbacks through a preallocated serialized `thread_call` with `THREAD_CALL_OPTIONS_ONCE`; interrupt-safe enqueue, ticket-based flush, stop/drain and callback-return synchronization. |
| Timer | One-shot delayed `thread_call`, callback rearm, replacement-deadline validation and synchronous cancellation. |
| Context and clocks | Actual interrupt state, kernel thread identity, uptime, calendar time and delay APIs. |
| Process and credentials | `proc_selfpid`, `proc_selfname`, current kauth credential UID; explicit root-only policy for NVIDIA NICE/PERFMON rights. |
| Process lifetime | Real `proc_self` / `proc_rele` references, `proc_pid` translation, `proc_exiting` and `current_task == kernel_task` flags. Darwin has one kernel PID namespace. |
| Runtime helpers | OS CSPRNG `read_random`, ordinary-thread scheduler yield through an actual OS sleep, and the original x86 `sfence` write-combine ordering instruction. |
| Current CPU | Exact exported Intel `cpu_number()` SPI, backed by the original Apple declaration/export list. Requires `com.apple.kpi.unsupported`. |

There is no per-component v9 reserve limit for synchronization objects. Each
work queue has **64 pending entries**, allocated before any enqueue. A full
queue returns `NV_ERR_NO_MEMORY`; the caller retains ownership of rejected
data. Work callbacks may queue more work. A callback cannot flush or stop its
own queue because doing so would deadlock. Timer callbacks may rearm their timer
but cannot synchronously cancel themselves.

The full RM must bind a real work-item execution adapter before using its global
queue. An unbound global queue returns `NV_ERR_NOT_READY`. The work queue does
not fabricate an RM alternate stack or pretend a missing callback executed.

## Lifetime and context

Allocate and destroy objects only from schedulable thread context with
interrupts enabled. Before destruction, the owner must quiesce every external
reference and end all acquires, releases, waits, arms and cancellations. An
unlocked object or cancelled timer alone does not prove that lifetime.

Semaphore/RW conditional operations, semaphore release, completion wake,
work enqueue and timer arm use short simple-lock critical sections. They do not
allocate or sleep. Blocking operations register their wait under that state
lock, release the lock and restore interrupts before sleeping. Sleep context
checks reject interrupt context and disabled interrupts; they cannot detect
every unrelated caller-held lock.

`cpu_number()` is deliberately an explicit unsupported KPI dependency, not a
guessed private CPU layout or APIC/RDTSCP conversion. A kernel without that
export cannot load this profile. Native macOS has no equivalent public
current-CPU KPI: full-RM native tests must bind the explicit virtual-CPU fixture.
That fixture is excluded from the kernel build. Native Linux uses `sched_getcpu`
unless a test explicitly binds a fixture.

## Validation

The native suite checks the production lifecycle, allocation unwind, overlapping
readers and writer exclusion, 12,000 contended mutex updates, complete-all
wakeups, interrupt-context refusals, queue saturation, unload flush, self-flush
refusal, 4,000 concurrent producer items, timer rearm and pending/active callback
cancellation. POSIX tests establish functional behavior, not Darwin interrupt or
scheduler behavior. The kernel source is compiled separately against the pinned
SDK and compared with an independent SDK import reference.

The native suite currently performs 166 assertions, including 17 allocation
failure paths. The production lifecycle contains 37 checks. Eight provenance
checks verify original ABI signatures, reference bytes and the source-backed
CPU SPI. Native macOS execution is established by the macOS build workflow;
local Linux validation alone does not establish that result.

Native Darwin obtains the `getentropy` declaration from `<sys/random.h>`;
Linux obtains it from `<unistd.h>`. The separate kernel branch uses
`read_random`. The exact Apple declarations and their availability are retained
in the pinned `reference/apple-random.h` source.

This component performs no GPU register writes, interrupt registration,
device DMA setup, firmware upload or GPU initialization.

NVIDIA references retain their MIT notices. Apple declaration/export evidence
retains the original notices and complete [Apple license](reference/APPLE_LICENSE).
