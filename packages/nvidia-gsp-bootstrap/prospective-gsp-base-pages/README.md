# GSP shared queue on real base pages

This isolated retained child changes one exact B6 original source. The GSP
shared queue requests `RM_PAGE_SIZE` (4 KiB) before its first allocation,
matching the selected Darwin backend. It removes the huge-page-specific
out-of-memory fallback because an initial base-page failure must propagate
without repeating the same allocation.

Both default queues remain 256 KiB. Their shared allocation remains 528,384
bytes: one 4 KiB page table plus the command and status queues, represented
by 129 base pages. Descriptor, page-table, mapping, cancellation and cleanup
logic outside the selected allocation block is byte-for-byte unchanged.

The CPU controls extract the actual queue-sizing/initialization and original
page-size/OS allocation bodies. Their OS/DMA/resource endpoints are explicit
fixtures. They separately model the unprotected-host-memory admission change;
this page-size profile alone does not implement that capability. The controls
do not execute IOKit, original GPU hardware operations, native Apple code or
prove DMA cessation. The native build and physical Lenovo test remain separate.
