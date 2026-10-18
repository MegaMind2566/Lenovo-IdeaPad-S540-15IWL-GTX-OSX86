// SPDX-License-Identifier: MIT
// Independent loader-code reference. The shared declaration pins the exact
// class layout; only Apple's required metaclass registration is instantiated.
// Runtime method bodies and other global objects are deliberately absent.
#include "../platform/S540NvidiaGspPowerService.hpp"
namespace S540GspPowerKernel {
OSDefineMetaClassAndStructors(S540NvidiaGspPowerService, IOService);
}
