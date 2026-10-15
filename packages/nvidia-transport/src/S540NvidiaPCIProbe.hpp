// SPDX-License-Identifier: MIT
#ifndef S540_NVIDIA_PCI_PROBE_HPP
#define S540_NVIDIA_PCI_PROBE_HPP

#include <stdint.h>

// The runtime hardware identity, rather than registry labels, gates attachment.
// Keep this small policy independent of IOKit for negative host-side tests.
namespace S540NvidiaPCIProbePolicy {
struct Identity {
    uint32_t vendorDevice;
    uint32_t revisionClass;
    uint32_t subsystem;
};

inline bool matches(const Identity &identity) {
    return identity.vendorDevice == 0x1f9110deU
        && identity.revisionClass == 0x030000a1U
        && identity.subsystem == 0x380617aaU;
}

// A descriptor must describe the already assigned, non-prefetchable, 32-bit
// BAR0 aperture observed on this exact laptop. Never size or repair a BAR.
inline const char *validateBar0(uint32_t rawBar, uint64_t tag,
                                uint64_t address, uint64_t length) {
    if (rawBar == UINT32_MAX || (rawBar & 0xfU) != 0 || rawBar == 0)
        return "bar0-configuration-invalid";
    if ((tag & 0xffU) != 0x10U
        || (tag & 0x03000000U) != 0x02000000U
        || (tag & 0x40000000U) != 0
        || length != 0x01000000U || address == 0
        || (address & 0x00ffffffU) != 0
        || address != static_cast<uint64_t>(rawBar & 0xfffffff0U))
        return "bar0-descriptor-invalid";
    return nullptr;
}

// Config reads are injected for host negative tests. The kernel reader rejects
// unaligned/out-of-range offsets. Walk only the standard PCI capability list;
// there is no polling, extended config access, or power-state transition.
template <typename Reader>
const char *requireD0(Reader &read) {
    uint32_t commandStatus = 0, header = 0, pointerWord = 0;
    if (!read(0x04, commandStatus) || !read(0x0c, header))
        return "pci-config-unavailable";
    if ((commandStatus & 0x00100000U) == 0)
        return "pm-capability-unavailable";
    if (((header >> 16) & 0x7fU) != 0)
        return "pm-capability-malformed";
    if (!read(0x34, pointerWord))
        return "pci-config-unavailable";
    uint32_t offset = pointerWord & 0xffU;
    uint64_t visited = 0;
    for (unsigned int links = 0; links < 48; ++links) {
        if (offset == 0)
            return "pm-capability-unavailable";
        if (offset < 0x40 || offset > 0xfc || (offset & 3U) != 0)
            return "pm-capability-malformed";
        const uint64_t bit = UINT64_C(1) << ((offset - 0x40) / 4);
        if ((visited & bit) != 0)
            return "pm-capability-malformed";
        visited |= bit;
        uint32_t capability = 0;
        if (!read(offset, capability))
            return "pci-config-unavailable";
        const uint32_t identifier = capability & 0xffU;
        if (identifier == 0 || identifier == 0xffU)
            return "pm-capability-malformed";
        if (identifier == 1) {
            const uint32_t version = (capability >> 16) & 7U;
            if (version < 1 || version > 3)
                return "pm-capability-unsupported";
            if (offset > 0xf8)
                return "pm-capability-malformed";
            uint32_t pmcsr = 0;
            if (!read(offset + 4, pmcsr))
                return "pci-config-unavailable";
            return (pmcsr & 3U) == 0 ? nullptr : "pci-not-d0";
        }
        offset = (capability >> 8) & 0xffU;
    }
    return "pm-capability-malformed";
}

inline uint32_t architecture(uint32_t boot0) {
    return (((boot0 >> 8) & 1U) << 5) | ((boot0 >> 24) & 0x1fU);
}

inline uint32_t implementation(uint32_t boot0) {
    return (boot0 >> 20) & 0xfU;
}

inline const char *identifyBoot0(uint32_t boot0) {
    if (boot0 == 0)
        return "zero-value";
    if (boot0 == UINT32_MAX)
        return "all-ones-value";
    if (architecture(boot0) != 0x16U)
        return "architecture-mismatch";
    if (implementation(boot0) != 7U)
        return "implementation-mismatch";
    return "tu117-identified";
}

// BOOT42 has a contiguous six-bit architecture field. BOOT0's extension bit
// layout must not be reused for this second register.
inline uint32_t boot42Architecture(uint32_t boot42) {
    return (boot42 >> 24) & 0x3fU;
}

inline uint32_t boot42Implementation(uint32_t boot42) {
    return (boot42 >> 20) & 0xfU;
}

inline uint32_t boot42ChipID(uint32_t boot42) {
    return (boot42 >> 20) & 0x3ffU;
}

inline const char *identifyBoot42(uint32_t boot42) {
    if (boot42 == 0)
        return "zero-value";
    if (boot42 == UINT32_MAX)
        return "all-ones-value";
    if (boot42Architecture(boot42) != 0x16U)
        return "architecture-mismatch";
    if (boot42Implementation(boot42) != 7U)
        return "implementation-mismatch";
    return "tu117-identified";
}

inline bool boot0IsTU117(uint32_t boot0) {
    return boot0 != 0 && boot0 != UINT32_MAX
        && architecture(boot0) == 0x16U && implementation(boot0) == 7U;
}

inline bool boot42IsTU117(uint32_t boot42) {
    return boot42 != 0 && boot42 != UINT32_MAX
        && boot42Architecture(boot42) == 0x16U
        && boot42Implementation(boot42) == 7U
        && boot42ChipID(boot42) == 0x167U;
}

// This reproduces only the pinned TU117 table predicate. It does not create
// an NVIDIA RM object or HAL instance, nor initialize any hardware.
inline int selectHALVariant(uint32_t boot0, uint32_t boot42) {
    return boot0IsTU117(boot0) && boot42IsTU117(boot42) ? 41 : -1;
}
}

#if defined(KERNEL)
#if !defined(__x86_64__)
#error "The read-only PCI prototype supports Intel x86_64 only."
#endif
#include <IOKit/IOService.h>
#include <IOKit/pci/IOPCIDevice.h>

// An observational attachment prototype. It does not initialize the GPU.
class S540NvidiaPCIProbe : public IOService {
    OSDeclareDefaultStructors(S540NvidiaPCIProbe)

public:
    IOService *probe(IOService *provider, SInt32 *score) override;
    bool start(IOService *provider) override;
    void stop(IOService *provider) override;
};
#endif

#endif
