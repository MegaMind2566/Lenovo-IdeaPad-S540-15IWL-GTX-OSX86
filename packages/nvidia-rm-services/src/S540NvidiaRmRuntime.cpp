// SPDX-License-Identifier: MIT
#include "S540NvidiaRmRuntime.hpp"
#include "../../nvidia-resource-server/src/S540NvidiaResourceServer.hpp"
#include "../memory/S540NvidiaRmMemory.hpp"
#include "../pci/S540NvidiaProviderSession.hpp"
#include "../../nvidia-caller-integration/src/S540NvidiaReserve.hpp"
#include "../../nvidia-nvport-runtime/upstream/nvport_runtime.h"

namespace {
using S540NvidiaRmRuntime::Result;

void check(Result &result, bool &component, bool condition)
{
    ++result.checks;
    if (!condition) {
        ++result.failures;
        component = false;
    }
}

bool cpuCold()
{
    return s540NvportRuntimeIsCold() == NV_TRUE &&
        !S540NvidiaReserve::ready() && S540NvidiaReserve::liveSlots() == 0;
}

struct Context { IOPCIDevice *provider; Result *result; };

void runServices(void *opaque)
{
    auto &context = *static_cast<Context *>(opaque);
    auto &result = *context.result;
    result = {};
    result.cleanup = true;
    check(result, result.cleanup, cpuCold());
    if (!result.cleanup)
        return;

    // This is NVIDIA's selected standalone Resource Server profile with real
    // NVOC objects and application callbacks. It is not coreInitializeRm().
    const auto server = S540NvidiaResourceServer::check();
    result.resourceServerChecks = server.checks;
    result.checks += server.checks;
    result.failures += server.failures;
    result.resourceServer = server.server;
    result.clients = server.clients;
    result.resources = server.resources;
    result.sharing = server.sharing;
    result.control = server.control;
    result.cleanup = server.cleanup;
    check(result, result.resourceServer, server.passed());
    check(result, result.cleanup, server.cleanup && cpuCold());
    if (!result.cleanup)
        return;

    const auto memory = S540NvidiaRmMemory::check();
    result.hostMemoryChecks = memory.checks;
    result.checks += memory.checks;
    result.failures += memory.failures;
    result.hostMemory = true;
    check(result, result.hostMemory, memory.passed());
    check(result, result.cleanup, memory.cleanup && !S540NvidiaRmMemory::ready());
    if (!result.cleanup)
        return;

#if defined(KERNEL)
    const auto pci = S540NvidiaRmPci::check(context.provider);
#else
    const auto pci = S540NvidiaRmPci::check();
#endif
    result.pciSessionChecks = pci.checks;
    result.checks += pci.checks;
    result.failures += pci.failures;
    result.pciSession = true;
    check(result, result.pciSession, pci.passed());
    check(result, result.cleanup, pci.cleanup && cpuCold());
}
}

S540NvidiaRmRuntime::IntegratedResult
S540NvidiaRmRuntime::checkIntegrated(IOPCIDevice *provider)
{
    IntegratedResult result{};
    // A refused preceding stage has explicit failed/unrun service evidence.
    result.services.checks = 1;
    result.services.failures = 1;
    Context context{provider, &result.services};
    result.v8 = S540NvidiaHardwareRuntime::checkIntegrated(
        provider, runServices, &context);
    result.acquired = result.v8.acquired;
    return result;
}
