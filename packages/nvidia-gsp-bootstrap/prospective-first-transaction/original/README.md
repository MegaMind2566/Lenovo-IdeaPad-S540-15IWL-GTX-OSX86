# Original first-transaction boundaries

This opt-in package replays the frozen eight-file first-transaction patch on the exact prospective V3 source inventory. It preserves the public original ABI, records failed initialization for outer cleanup, retains firmware and ambiguous inner allocations, and checks selected destruction paths before their first mutation. It does not enable original entry or grant hardware admission.

`SOURCE-CONTRACT.json` pins raw upstream, exact V2/V3 inputs, candidate outputs and the unchanged source patch. The promoted C bridge and control sources only change package-relative includes. The runners locate the repository from their own file location. Generated source copies, extracted bodies, binaries, objects and logs belong in the supplied output directory, separate from all inputs. Repository output is allowed only under its canonical `build/` directory; outside output is also supported. Other repository paths, upstream overlap and existing output symlinks are rejected.

Use `check.py` and `compile_full.py` with explicit paths:

```sh
python3 packages/nvidia-gsp-bootstrap/prospective-first-transaction/original/check.py \
  --upstream "$UPSTREAM" --namespace "$NAMESPACE" --v3-root "$V3_ROOT" \
  --output "$OUTPUT/original" --cc "$CC" --cxx "$CXX"
python3 packages/nvidia-gsp-bootstrap/prospective-first-transaction/original/compile_full.py \
  --upstream "$UPSTREAM" --namespace "$NAMESPACE" --v3-root "$V3_ROOT" \
  --output "$OUTPUT/original" --cc "$CC" --cxx "$CXX" --sdk "$SDK"
```

`V3_ROOT` contains the complete materialized `source/` tree. All 4,005 files are verified. Omitting `--v3-root` reconstructs and verifies the same V3 inventory from pinned upstream and the repository's frozen raw-to-V3 patch. `prepare.py` only needs `--upstream`, `--output` and optional `--v3-root`.

Default execution requires Intel macOS and the actual Apple compiler. Explicit `--host-control` selects Linux x86_64 CPU controls and Mach-O cross-compilation; those results are not authoritative Darwin execution. Preserve the compiler driver's lexical path, especially `clang++`. The original C compile probe requires `--sdk` in cross mode. A supplied SDK must be a clean pinned Git checkout, or an exact pinned archive extraction accompanied by `--sdk-archive`. Native C probes without a supplied SDK make no kernel-SDK identity claim.

The controls extract 11 complete bodies: nine original functions/wrappers and two new source helpers. They run 74 checks in both normal and fatal sanitizer variants. The original wrapper, four RM API-lock bodies, four NVOC bodies and timer constructor are source-backed; GPU initialization, GPU-lock endpoints, thread/runtime transitions and record admission endpoints are explicitly isolated fixtures. Actual Host, Memory and Crypto counter implementations are linked. The separate sibling record suite exercises the strong record with actual queue/timer companion services. The full compile probe builds eight complete original translation units and the typed bridge against the exact V3 headers.

The generic lock predicate checks real API/GPU ownership and then returns `NV_ERR_NOT_SUPPORTED`: actual RM-semaphore ownership remains unproved. Unknown owner/callback descriptors, unreviewed inner cleanup and constructor families, service/borrower closure and hardware stop remain admission gates. The historical inner-cleanup audit covered 25 boundaries and 78 complete function spans; this is a bounded source review, not transitive closure. Neither control results nor successful compilation discharge those gates.
