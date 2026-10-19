# Isolated prospective combined profile

This profile composes the verified ten-patch source with the statusful adapter,
wait cancellation, GSP teardown, RM lock cancellation, Falcon reset and optional
capability-minor guards. It leaves the approved ten-patch profile and default
compiler behavior unchanged. The two patches and source contract identify the
complete raw-to-combined result and the additional changes against verified ten.

Every standalone patch is checked against pinned raw bytes. Composition merges
only disjoint edits in raw-source coordinates and records line offsets. Both
reconstructed patches are then replayed exactly, without fuzz or offset search.
The helper rejects any changed pinned project source, bridge header or generator.

Run after preparing the verified ten-patch tree and baseline namespace:

```sh
python3 packages/nvidia-gsp-bootstrap/prospective/check_combined_profile.py \
  --repo . --upstream build-src/nvidia-upstream \
  --checked-source build/nvidia-execution/original-rm/checked-source \
  --namespace build/nvidia-execution/original-rm/original/contract/S540GlobalRmNamespace.h \
  --cc /usr/bin/clang \
  --output build/nvidia-execution/prospective-checks/combined-profile
```

The default requires Intel macOS and uses the native kernel compilation flags.
An explicit `--cross-probe` uses the separate PIC cross-compilation profile.
Use a fresh output directory. The output audit records the compiler, exact source
and object hashes, real include dependencies and five additive private aliases.
The original namespace header is not modified. Strong project cancellation
bridges retain their distinct names.

Local Clang 18 validation compiled **19 changed original C units and two project
C bridges**, with warnings treated as errors and an individual 4096-byte frame
limit. This is **not all 1100 units** affected by the shared header changes. It
does not prove a complete call-chain stack bound, target KXLD compatibility,
PM acknowledgement, DMA quiescence or successful GSP initialization. No kernel
or GPU code was executed. This profile does not approve a test package or issue
a DMA-stop receipt.

Later memory-publication/indirect-peer fixes and log/participant prototypes are
outside this first frozen prospective composition.
