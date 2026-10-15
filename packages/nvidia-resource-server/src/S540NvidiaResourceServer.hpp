// SPDX-License-Identifier: MIT
#ifndef S540_NVIDIA_RESOURCE_SERVER_HPP
#define S540_NVIDIA_RESOURCE_SERVER_HPP
#include "../../nvidia-os-adapter/upstream/include/nvtypes.h"
namespace S540NvidiaResourceServer {
struct Result {
    NvU32 checks, failures;
    bool server, clients, resources, sharing, control, cleanup;
    bool passed() const { return checks != 0 && failures == 0 && server && clients &&
        resources && sharing && control && cleanup; }
};
// Requires the outer startup lease, an ordinary thread, and all CPU services
// initially cold. Starts the existing bounded reserve/checked NVPort core,
// executes actual NVIDIA RS_STANDALONE/NVOC, then releases every owned service.
// This initializes a real ResourceServer subsystem, not the global/GPU RM.
Result check();
}
#endif
