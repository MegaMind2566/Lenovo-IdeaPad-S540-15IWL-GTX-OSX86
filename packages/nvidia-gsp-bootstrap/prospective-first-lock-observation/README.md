The retained first transaction observes actual API TLS, per-GPU lock ownership
and allocation-lock ownership through the selected strong original reader. It
requires the immutable ordinary master, matching global/record generations,
completed READY global construction, and stable SYS identity before and after
the observation. The selected basic lock model requires `SYS.pSema == NULL`.

Sticky errors remain intact. This observation grants neither generic callback
retirement nor a whole hardware-stop or physical-release receipt. The existing
original-C compiler profile owns the no-legacy semaphore definition; this
module adds no duplicate per-source macro.
