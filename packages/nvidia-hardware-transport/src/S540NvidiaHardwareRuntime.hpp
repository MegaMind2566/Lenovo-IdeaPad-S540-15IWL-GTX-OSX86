// SPDX-License-Identifier: MIT
#ifndef S540_NVIDIA_HARDWARE_RUNTIME_HPP
#define S540_NVIDIA_HARDWARE_RUNTIME_HPP

#include "../../nvidia-nvport-runtime/src/S540NvidiaSupportRuntime.hpp"
class IOPCIDevice;

namespace S540NvidiaHardwareRuntime {
constexpr NvU32 kFormatVersion = 1;

struct Result {
    NvU32 checks;
    NvU32 failures;
    bool hostDma;
    bool pciReadAdapter;
    bool interruptInventory;
    bool firmwareParser;
    bool firmwareRpc;
    bool cleanup;
    const char *dmaMode;
    const char *dmaReason;
    NvU64 dmaBytes;
    NvU32 dmaSegments;
    const char *pciReason;
    NvU32 pciCapabilities;
    NvU32 msiVectors;
    NvU32 msixVectors;
    bool msiObservedEnabled;
    bool msixObservedEnabled;

    bool passed() const {
        return checks != 0 && failures == 0 && hostDma && pciReadAdapter &&
               interruptInventory && firmwareParser && firmwareRpc && cleanup;
    }
};

struct IntegratedResult {
    S540NvidiaSupportRuntime::IntegratedResult v7;
    Result preparation;
    bool acquired;
};

// The kernel path uses the actual borrowed PCI provider and its nonblocking
// arbitration guard. Native CI substitutes an explicit PCI fixture and host
// DMA backend. Both execute the same finite aggregate and shared lease.
// No GPU command, interrupt enable, firmware load or MMIO operation is added.
IntegratedResult checkIntegrated(IOPCIDevice *provider);
}
#endif
