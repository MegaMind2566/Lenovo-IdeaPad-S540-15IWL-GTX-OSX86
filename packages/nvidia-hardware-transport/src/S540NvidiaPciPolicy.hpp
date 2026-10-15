// SPDX-License-Identifier: MIT
#ifndef S540_NVIDIA_PCI_POLICY_HPP
#define S540_NVIDIA_PCI_POLICY_HPP
#include "S540NvidiaPci.hpp"
// PCI capability layout reference: Linux include/uapi/linux/pci_regs.h,
// commit 0fcb05b72344f40806cbe810de8872f1698bf053. No Linux implementation
// or interrupt registration code is linked into this Darwin profile.
namespace S540NvidiaPci {
constexpr NvU32 kStandardConfigBytes = 256;
constexpr NvU32 kMaximumCapabilities = 48;
inline bool validAccess(NvU32 offset, NvU32 width) {
    return (width == 1 || width == 2 || width == 4) &&
           offset < kStandardConfigBytes &&
           width <= kStandardConfigBytes - offset &&
           (offset & (width - 1)) == 0;
}
inline bool validCapabilityOffset(NvU32 offset) {
    return offset >= 0x40 && offset <= 0xfc && (offset & 3U) == 0;
}
inline bool withinCapabilitySpace(NvU32 offset, NvU32 bytes) {
    return validCapabilityOffset(offset) && bytes <= kStandardConfigBytes - offset;
}
// Classify only assigned memory BAR bases. Walking from BAR0 is essential:
// the upper address word of a preceding 64-bit BAR is never a new BAR.
// Return PCI memory type encoding 0 (32-bit), 2 (64-bit), or -1 (invalid).
inline NvS32 memoryBarType(const NvU32 bars[6], NvU8 bar) {
    if (!bars || bar > 5) return -1;
    for (NvU32 index = 0; index < 6; ++index) {
        const NvU32 raw = bars[index];
        const NvU32 type = (raw >> 1) & 3U;
        if ((raw & 1U) != 0) {
            if (index == bar) return -1;
            continue;
        }
        if (type == 2) {
            if (index == 5 || index + 1 == bar) return -1;
            if (index == bar)
                return ((raw & 0xfffffff0U) != 0 || bars[index + 1] != 0) ? 2 : -1;
            ++index;
        } else if (index == bar) {
            return type == 0 && (raw & 0xfffffff0U) != 0 ? 0 : -1;
        }
    }
    return -1;
}

// Match the assigned IOPCI descriptor's register and address-space encoding.
// Bit 30 carries prefetchability and is accepted for either memory type.
inline bool descriptorTagMatches(NvU64 tag, NvU8 bar, NvS32 type) {
    if (bar > 5 || (type != 0 && type != 2)) return false;
    const NvU64 expectedSpace = type == 0 ? 0x02000000ULL : 0x03000000ULL;
    return (tag & 0xffU) == NvU64{0x10U + 4U * bar} &&
           (tag & 0x03000000ULL) == expectedSpace;
}
inline bool exactTarget(NvU32 vendorDevice, NvU32 revisionClass, NvU32 subsystem) {
    return vendorDevice == 0x1f9110deU && revisionClass == 0x030000a1U &&
           subsystem == 0x380617aaU;
}
}
#endif
