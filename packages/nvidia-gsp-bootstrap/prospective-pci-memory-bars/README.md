This separate B5 profile corrects the classification of PCI BARs in the exact
B4 platform producer. A nonzero BAR with its PCI I/O-space bit set is skipped
before memory-kind checks and the memory-aperture counter. Port I/O is neither
accessed nor mapped.

The authentic NVIDIA-enabled registry dump describes three memory apertures at
registers 0x10, 0x14 and 0x1c, plus a 128-byte I/O resource at 0x24. B4 rejected
that I/O resource after collecting its three memory apertures. The 0x30 ROM
resource remains outside the unchanged 0x10–0x24 scan.

The same dump reports IOPCIExpressCapabilities=18 (0x12). Apple's pinned
IOPCIFamily producer copies the actual PCIe flags from capability offset +2
into this property. Its Device/Port Type is 1, Legacy PCIe Endpoint. B5 accepts
only endpoint types 0 and 1 using that already-read flags value; root ports,
switches, bridges and other port types remain refused. No capability read is
added. Apple's public source defines both endpoint types in IOPCIPrivate.h
under IOPCIFamily (the exact path and revision are in SOURCE-CONTRACT.json).

Exactly three memory BARs are still required. Every existing memory type,
physical-address, descriptor-length, contiguous-span, overflow, PCI identity,
segment, D0 and console guard remains. PCIe endpoint classification includes
the real legacy endpoint without admitting any port or bridge. No PCI read or
write is added.
This profile grants no original-entry or production admission by itself.

The profile follows preparation-observation and precedes experimental-target-
control. Its input hash is recorded in BASE-SHA256SUMS. CPU fixtures execute
the actual original and transformed producer bodies. Native compilation and
the B5 Lenovo initialization test remain separate evidence.
