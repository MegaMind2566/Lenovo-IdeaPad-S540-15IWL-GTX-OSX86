# Prospective external-bindata consumption boundary

Status: **design-not-implemented**. Evidence: **source-only**. Retirement while IRQs remain active: **pending**. No receipt issuer, verifier, production admission change, or hardware test authorization is provided here.

The pinned NVIDIA host source frees the copied `pExternalBindata` radix3 root after a successful synchronous `GMCAPI_CMD_GSP_INIT` response and successful static-info decoding, while GSP remains running. This is an original consumption boundary for one buffer. It does not attest a session DMA stop, stopped GPU engines, completed GSP unload, or safe retirement of other allocations.

`first-transaction-dma-buffer-ledger.json` records the root allocation, all radix tables and copied data pages, address publication, IOVA/backing release paths, failure paths, other bootstrap buffer families, limitations, and a candidate per-record capability design. The candidate remains unimplemented. The original response-flag assertion, void free paths, aliases, repeated exposure, stale cached arguments, and actual backend completion require a checked integration before any gate can change.

`source-freeze.json` binds 24 reviewed source files to both the original upstream commit `1a82fbfda8f321b056eb3568850f9316c5e465c5` and the V3 source tree digest `fa8498c3958a559a3466ef6dd4e541bfcea9f55d8809d0a422c784cacd703029`. Paths are relative to the upstream repository root. `source-anchors.json` binds 41 V3 line ranges by SHA256. The firmware basename refers to the generic NVIDIA `ucodes_tu10x.bin` input identified by its size and SHA256; firmware bytes are not copied into this package.

`PROVENANCE.json` preserves the original scratch ledger SHA256 and lists the exact persistence transformations. The source freeze and anchors are byte-identical copies. `STATUS.json` keeps every runtime and hardware admission claim false. `FROZEN-SHA256.json` covers the exact package inventory, excluding itself.

This package contains no SPX or machine-specific hardware identifiers and requires no execution. It is evidence for a future reviewed successor.
