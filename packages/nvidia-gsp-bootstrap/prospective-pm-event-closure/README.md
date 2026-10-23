# Actual PM event cancellation

This isolated source successor couples the genuine Power lease to one fixed
cancellation state and generation while it is idle. The PM guard closes that
binding before publishing the event timestamp, unlocking, or invoking an
external stop hook. A delayed dispatcher hook therefore cannot leave original
operation acceptance open. The fixed hold prevents unbind and Power-service
destruction until its owner explicitly releases the coupling.

Invalid monotonic clock observations still close operation acceptance. They
leave the cleanup deadline at zero and cannot fabricate permission to continue
hardware teardown. Repeated events cannot replace the first published deadline.
Existing producer commits retain their real serial and can leave after revoke.

`check.py` compiles the whole actual cancellation and native Power translation
units and an extracted exact live kernel `setPowerState` body. Plain and fatal
ASan/UBSan/function controls cover blocked external hooks, real commit lifetime,
generation and identity mismatch, coupling destruction, zero/backward clocks,
and PM events before binding. Compiled negative controls deliberately restore
the old failure modes. These are CPU fixtures, not execution on Darwin or proof
of GPU quiescence, physical-release authority, or a PM scheduler deadline.
