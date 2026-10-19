# Retained Host diagnostic source profile

This fixed source profile retains every associated Host allocation from the
first transaction owner onward. A genuine logical free retires its exact
allocation record and keeps the physical backing. Planned retirement has
separate counters; it does not invent a service failure or clear an existing
one. Ordinary first-refusal retention still handles actual failures.

The policy reads the real record owner, generation and active participant. It
accepts no caller readiness flag. Pending records and immutable allocation
serials exclude duplicate frees and reuse. Live bytes remain owned bytes;
physical-free counters are unchanged. A concurrent service failure remains
sticky even if planned retirement has already been selected.

`prepare.py --composition COMPOSITION_JSON --output FRESH_OUTPUT` emits five
exact project replacements and an explicit successor manifest. The complete
composer also provides the fixed `--retained-diagnostic` source option. This is
a source selection, not permission to enter original RM or hardware.

`check.py` executes the actual transformed Host and frozen strong record with
real cancellation, queues and timers. Original callback metadata, locks and
hardware are explicit parent test endpoints. The seven cases cover the master,
actual queued worker and actual direct-timer participant, a genuine service
refusal before free, readable retained backing and competing master/worker
logical frees. The direct case also verifies retention of the real temporary
timer stack. All 29 checks pass in both ordinary and fatal ASan/UBSan/function
variants. The local Linux run disables LeakSanitizer because the executor cannot
inspect its task files; address, undefined-behavior and function checks remain
fatal. Native Apple execution is verified separately and remains pending.

Host retention is one allocation family. The real device session must acquire
its hardware-DMA hold before original initialization; DMA pages/IOVA must keep
that hold. Timer, workqueue, synchronization, context and module-text owners need
their own retained lifetime. This profile issues no hardware-stop receipt,
cleanup authorization or final release. It does not prove callback closure,
kernel stack bounds, actual kernel loading, GPU initialization or acceleration.

The combined retained/RC/shutdown source profile compiles all 55 project units
and its changed original `osapi.c` locally. That cross-compilation is separate
from the hosted runtime controls and from a complete native linked image.
