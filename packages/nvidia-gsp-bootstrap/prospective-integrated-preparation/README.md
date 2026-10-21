# Integrated RM/GSP preparation

The next target milestone combines callback/resource/stack prerequisites with
the first actual RM/GSP/GPU initialization attempt. The completed closed idle
loader checkpoint remains the baseline; it is not another initialization test.

This source-only successor combines three opt-in changes in a fixed order:

1. Retain the genuine failed global system before OOM cleanup can loop. Keep
   the actual constructor failure and exact system/owner/generation identities.
2. Retain the operational Owner, Session, DMA resources and module text before
   any future original entry. Preserve the real PM cancellation timestamp and
   its existing 30-second deadline. Check genuine GPU cancellation while the
   TX queue waits for space and before publishing its staged fragments. Preserve
   an already accepted send result if revocation races the actual TX_HEAD commit.
3. Replace the direct IRQ bottom-half private thread-call backend with the
   public workloop callback backend; track genuine IRQ/nested cancellation
   scopes, pending-work origin and retained direct backend lifetime. Include
   typed original interrupt-mask and queued-1Hz drain helpers.

`builders/prepare_nvidia_integrated_successor.py` verifies a complete closed
public-callback parent, writes a fresh companion tree, records overlapping
edits and exact helper/source hashes, and rechecks all inputs. It preserves
4,005 original source files and selects 61 project translation units: the
parent's 60 plus one original-ABI IRQ helper. The actual loader stop guards
are included with the session lifetime change. Parent source bytes remain
unchanged. Header consumers must be rebuilt or pass the existing exact full
dependency cache checks; previous objects are not automatically reusable.
The reviewed parent manifest SHA256 is
`1392052eda0733713e345e938033a06c539669d4b443ba5c3104c70ae171e298`;
a consistently rehashed replacement parent is also refused.

Example preparation, with paths to previously verified local inputs:

```sh
python3 builders/prepare_nvidia_integrated_successor.py \
  --composition build/integrated-inputs/compose-check-public \
  --output build/integrated-successor
python3 builders/prepare_nvidia_integrated_successor.py \
  --output build/integrated-successor --verify-only
S540_INTEGRATED_PARENT="$PWD/build/integrated-inputs/compose-check-public" \
  python3 -m unittest discover -s builders/tests \
  -p test_nvidia_integrated_successor.py -v
```

`builders/compile_nvidia_integrated_successor.py` independently replays the
complete ordered source/metadata transformation in memory. It evaluates the
existing mapping guard on the exact unchanged parent and relocates its compiler
paths into the proven successor. It compiles 61 fresh Mach-O objects with the
pinned SDK, checks dependencies, compiler stack sidecars and unique strong
ownership of every new declared C export. The optional
`--compile-changed-original` selects the three actual changed original units.
This Linux cross-compilation receipt explicitly grants no final symbol closure,
native execution or aggregate stack proof. Frozen builders/guards remain intact.

Source composition does not provide runtime admission. The operational
`Owner::initialize` refusal, global kernel lifecycle gate and loader request
policy stay closed. No runtime entry coordinator is installed. A future
coordinator must first establish stack and PM prerequisites, then acquire the
actual permanent operational lifetime before beginning the record epoch and
binding cancellation to the exact original state. Session DMA generation and
first-record generation are distinct identities. A permanent lifetime hold
must never be acquired merely to test a still-closed entry gate.

The remaining admission obligations include complete aggregate stack bounds
for intended global/adapter/IRQ/callback paths, real revocation-to-hardware-stop
completion within the declared PM deadline, and integrated callback ordering.
The historical closed-image graph and individual frame warnings do not prove
the future activated graph. Retaining resources alone does not meet a power
deadline or establish hardware DMA quiescence.

This successor has no installable ZIP, native CI request or target execution.
The existing idle linker deliberately continues to enforce its own frozen
source/profile contract. A new integrated link/package contract is required
only after the local admission obligations genuinely pass. Do not widen the
two-callback idle cache cost guard or start that workflow for this preparation.

Component checkers and compact validation receipts live beside each source
profile. `PREPARATION-STATUS.json` records this checkpoint's actual validation
scope and remaining blockers. No acceleration, original initialization or
target success is inferred from CPU fixtures or kernel cross-compilation.
