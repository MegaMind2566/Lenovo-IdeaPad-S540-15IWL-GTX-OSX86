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
}

#if defined(KERNEL)
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
