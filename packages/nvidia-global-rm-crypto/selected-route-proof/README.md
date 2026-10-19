# Checkpoint3 rotation entry proof

This separate evidence excludes `knvlinkRotateEncryptionKeys_IMPL` from the exact
reviewed checkpoint3 entry closure. It leaves `CRYPTO-REACHABILITY.json` unchanged:
that fixed record still contains 63 guarded exclusions and one partial randomness
entry. This proof addresses that rotation route only. Other randomness routes
retain their SPDM and single-device source conditions. No crypto operation,
complete crypto admission, stack budget or hardware execution is established.

Run against the complete extracted Apple-native checkpoint3 artifact and the
exact ten-overlay composed source tree:

```sh
python packages/nvidia-global-rm-crypto/selected-route-proof/prove_rotation_entry.py \
  --artifact-root /path/to/extracted-checkpoint3 \
  --repo /path/to/repository \
  --source-tree /path/to/exact-ten-overlay-checked-source \
  --output /path/to/rechecked-rotation-proof.json
```

The script discovers LLVM Mach-O objdump or Apple's `otool`; an explicit
`--decoder COMMAND ...` can select another compatible disassembler. It never
executes an object. Reports contain relative artifact/source identities, hashes
and counts, without machine paths or embedded object bytes.

`checkpoint3-proof.json` fixes the reviewed native report, source manifest,
composed tree, proof/parser identities, actual bridge identity and expected
source/root inventory. Every run hashes all 4,005 composed source files and all
1,100 actual original objects. No cached object verification is accepted.

The evidence requires all of the following:

- The complete source inventory has no caller, address use or NVOC member for
  rotation. The generated method is a static alias; a disabled inline stub
  alone is not the exclusion argument.
- All original code/data relocation tables have zero incoming rotation symbol
  references. Same-object local relocations and decoded direct branches cannot
  target the implementation either.
- The actual compiled KernelNvlink reflection export atom has 16 zero bytes and
  no relocations: no exported callable method exists there.
- The actual project Mach-O imports derive exactly 23 original roots, with two
  explicit source-gated global lifecycle roots added separately. Rotation is
  absent, and project production sources contain no reference.

The final linked image is identified by the native report; this artifact retains
the actual project object and original inputs, rather than final image bytes.
No independent rescan of absent final-image bytes is claimed.

A changed report, source, object, parser, caller, export or root fails the check.
Future profiles must repeat source and actual compiled-image analysis and review
their own identities. Do not update only the hashes to reuse this conclusion or
reuse the checkpoint3 object hashes as evidence for new compilation.
