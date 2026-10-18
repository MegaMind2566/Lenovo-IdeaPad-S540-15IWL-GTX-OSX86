// SPDX-License-Identifier: MIT
#ifndef S540_NVIDIA_GSP_PLATFORM_HPP
#define S540_NVIDIA_GSP_PLATFORM_HPP

#include "../../nvidia-global-rm/src/S540NvidiaGlobalRm.h"
#include "../../nvidia-os-adapter/upstream/include/nv-kernel-interface-api.h"
#include "../src/S540NvidiaGspContext.h"

class IOPCIDevice;
typedef struct nv_state_t nv_state_t;

namespace S540NvidiaGspPlatform {
constexpr NvU32 kMaximumRomBytes = 16U * 1024U * 1024U;
constexpr NvU32 kMaximumRomChunk = 64U * 1024U;

// Bounded byte decoders shared by the real Darwin path and native tests.
bool decodeChassis(const void *table, NvU64 bytes, bool &notebook);
bool decodeFadt(const void *table, NvU64 bytes, bool &lowPowerS0);
bool romRequestValid(NvU32 offset, NvU32 bytes);
struct ConsoleOwnership {
    NvU32 frames, intelOwners, targetOwners, unknownOwners;
    bool overflow;
};
void observeConsoleOwner(ConsoleOwnership &, bool ownerKnown, NvU32 vendor,
                         NvU32 classCode, bool boundTarget);
bool consoleExcludesTarget(const ConsoleOwnership &, bool complete);

struct Evidence {
    NvU32 known;
    NvU32 missing;
    NvU32 pciDevices;
    NvU32 acpiDevices;
    NvU32 romCalls;
    NvU32 romFailures;
    bool acpiCompanion;
    bool romAvailable;
    bool s0ixHardwareKnown;
    bool s0ixHardware;
    bool s0ixPolicyEnabled;
};

// One externally serialized, ordinary-thread context belongs to the retained
// adapter session. It retains the exact provider and its published ACPI alias.
// Keep it alive until original adapter shutdown and every callback has drained.
class Context {
public:
    Context();
    ~Context();
    NV_STATUS initialize(IOPCIDevice *provider, nv_state_t *state = nullptr);
    NV_STATUS bindState(nv_state_t *state);
    // Detach the ROM callback's exact state identity while keeping provider
    // facts alive through transport/DMA cleanup and power-domain release.
    NV_STATUS unbindState(nv_state_t *state);
    NV_STATUS shutdown();
    NV_STATUS collect(S540NvidiaGlobalRmPlatformFacts *out);
    NV_STATUS collectSegment(NvU32 &segment);
    // A null PCI handle is permitted during the pre-state facts phase. The
    // adapter owner installs the real transport token before ContextPrepare.
    NV_STATUS collectDeviceFacts(S540GspDeviceFacts *out, void *pciHandle = nullptr);
    NV_STATUS readRom(nv_state_t *state, const NvU32 *input, NvU32 *output);
    Evidence evidence() const;
    bool active() const;
private:
    struct Impl;
    Impl *impl_;
    Context(const Context &) = delete;
    Context &operator=(const Context &) = delete;
};
}

extern "C" NV_STATUS NV_API_CALL s540Global_nv_acpi_rom_method(
    nv_state_t *state, NvU32 *input, NvU32 *output);

#endif
