# Typed NVIDIA RC and nano-timer bridge

This C translation unit is compiled with the complete pinned original `nv.h`
and full-RM namespace header. It implements the six original timer entry points
using the real Darwin timer backend. The production callbacks invoke the actual
original `rm_run_rc_callback` and `rm_run_nano_timer_callback` functions.

The one-second RC timer uses the real `nv_state_t.rc_timer_enabled` field,
refuses duplicate starts/stops with the original return convention, and rearms
only after the original callback returns `NV_OK`. Nano timers preserve the
opaque original handle and event argument. Every callback allocates a separate
tracked heap `nvidia_stack_t`, initializes `size` and `top` exactly as Linux does,
invokes the original RM callback and frees the stack after return. A 12 KiB
alternate stack is never placed on the Darwin kernel stack.
The allocation includes alignment padding so every alternate stack is 16-byte
aligned; the original tracked allocation base is retained for freeing.

Bind the device after host services initialization and before original adapter
initialization. `s540GspTimersStop` closes new timer admission and synchronously
cancels every software timer before adapter/global state destruction. Original
RM users must relinquish all timer references before Unbind. Unbind also frees
stopped leftover timer objects. All Bind/Stop/Unbind calls are externally
serialized by the outer driver startup/teardown lease; a snapshot is taken
within that same lifetime.

Registry state uses a short spinlock. No timer cancellation, callback wait,
heap allocation or RM execution happens while holding that lock. Timer arm is
allocation-free and may execute under the registry lock. Cancellation closes
arm admission before releasing the registry lock and waiting for the callback.
Stop prevents timer list mutation while it drains callbacks. A cancellation
failure quarantines the session and retains the callback data, timers and
binding. Unbind refuses to release a quarantined session.
RC stop closes private admission first, drains the original callback, and then
clears the original `rc_timer_enabled` field before returning. This avoids a
concurrent write while the unmodified original callback reads that field.

Native tests compile this same C bridge against full original NVIDIA headers
and explicit typed RM callback fixtures. They validate ABI stack initialization,
argument propagation, actual ordinary-context timer execution, cancellation,
rearm, session stop and cleanup. They do not establish GPU behavior or execution
of the original RM callback bodies. Production uses the original callback
symbols, with the exact original declarations checking those call sites.
An isolated child fixture triggers actual self-cancellation refusal and verifies
that quarantine retains ownership. It exits with those deliberately retained
objects; that failure profile is not reported as successful cleanup. The normal
parent lifecycle must release every object.

Original reference excerpts retain NVIDIA's MIT notices. Reference byte hashes,
source paths and line ranges are recorded in [PROVENANCE.json](PROVENANCE.json).
