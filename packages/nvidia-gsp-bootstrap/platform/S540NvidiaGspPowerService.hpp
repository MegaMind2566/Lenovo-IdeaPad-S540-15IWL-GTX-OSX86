// SPDX-License-Identifier: MIT
// Private kernel layout shared ONLY with the independent SDK metaclass codegen
// reference. No PM logic or metaclass initializer is defined in this header.
#ifndef S540_NVIDIA_GSP_POWER_SERVICE_HPP
#define S540_NVIDIA_GSP_POWER_SERVICE_HPP
#if !defined(KERNEL)
#error This private power service requires the real kernel SDK
#endif
#include "S540NvidiaGspPower.hpp"
#include <IOKit/IOLib.h>
#include <IOKit/IOService.h>
namespace S540GspPowerKernel {
using namespace S540NvidiaGspPower;
class S540NvidiaGspPowerService final : public IOService {
    OSDeclareDefaultStructors(S540NvidiaGspPowerService);
public:
    IOLock *guard = nullptr;
    IOPCIDevice *endpoint = nullptr;
    Revocation revocation{};
    Detail::Protocol protocol;
    NvU32 revocationHooksInFlight = 0;
    bool pmInitialized = false, attached = false, closing = false;
    bool init(OSDictionary *properties = nullptr) override;
    void free() override;
    bool join(IOPCIDevice *provider, const Revocation &action);
    bool exactDomain() const;
    IOReturn setPowerState(unsigned long ordinal, IOService *device) override;
    void powerChangeDone(unsigned long previous) override;
    NV_STATUS waitOn();
    Snapshot snapshot() const;
    NV_STATUS acknowledge();
    NV_STATUS finish();
};
}
#endif
