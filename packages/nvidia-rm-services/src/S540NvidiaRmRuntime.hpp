// SPDX-License-Identifier: MIT
#ifndef S540_NVIDIA_RM_RUNTIME_HPP
#define S540_NVIDIA_RM_RUNTIME_HPP

#include "../../nvidia-hardware-transport/src/S540NvidiaHardwareRuntime.hpp"

namespace S540NvidiaRmRuntime {
inline constexpr char kProfile[] =
    "standalone-resource-server-cached-host-readonly-pci";

struct Result {
    NvU32 checks = 0;
    NvU32 failures = 0;
    bool resourceServer = false;
    bool hostMemory = false;
    bool pciSession = false;
    bool clients = false;
    bool resources = false;
    bool sharing = false;
    bool control = false;
    bool cleanup = false;
    NvU32 resourceServerChecks = 0;
    NvU32 hostMemoryChecks = 0;
    NvU32 pciSessionChecks = 0;
    const char *profile = kProfile;

    bool passed() const {
        return checks > 0 && failures == 0 && resourceServer && hostMemory &&
            pciSession && clients && resources && sharing && control && cleanup;
    }
};

struct IntegratedResult {
    S540NvidiaHardwareRuntime::IntegratedResult v8;
    Result services;
    bool acquired = false;
};

// One existing startup lease covers the v8 regressions and this whole bundle.
// All owned objects are released before return. No full RM system or GPU is
// left initialized by this selected Resource Server/host-service checkpoint.
IntegratedResult checkIntegrated(IOPCIDevice *provider);
}
#endif
