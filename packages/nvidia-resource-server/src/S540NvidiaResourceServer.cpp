// SPDX-License-Identifier: MIT
#include "S540NvidiaResourceServer.hpp"
#include "S540NvidiaResourceExercise.h"
#include "S540NvidiaResourceBackend.hpp"
#include "../../nvidia-nvport-runtime/upstream/nvport_runtime.h"
#include "../../nvidia-caller-integration/src/S540NvidiaReserve.hpp"
#include "../../nvidia-caller-integration/src/S540NvidiaMutex.hpp"
#include "../../nvidia-nvport-lifecycle/src/S540NvidiaSpinlock.hpp"
namespace {
void expect(S540NvidiaResourceServer::Result &result, bool &group, bool condition) {
    ++result.checks; if (!condition) { ++result.failures; group = false; }
}
}
S540NvidiaResourceServer::Result S540NvidiaResourceServer::check() {
    Result result{0, 0, true, false, false, false, false, true};
    const NvU32 mutexes = S540NvidiaMutex::liveObjects();
    const NvU32 spins = S540NvidiaSpinlock::liveObjects();
    expect(result, result.server, s540NvportLifecycleContextAllowed() == NV_TRUE &&
        s540NvportRuntimeIsCold() == NV_TRUE && s540RsBackendIsCold() == NV_TRUE &&
        !S540NvidiaReserve::ready() && S540NvidiaReserve::liveSlots() == 0);
    if (!result.server) { result.cleanup = false; return result; }
    expect(result, result.server, S540NvidiaReserve::initialize());
    if (!S540NvidiaReserve::ready()) return result;
    const NV_STATUS initialized = s540NvportRuntimeInitialize();
    expect(result, result.server, initialized == NV_OK);
    if (initialized == NV_OK) {
        const NV_STATUS backend = s540RsBackendInitialize();
        expect(result, result.server, backend == NV_OK);
        if (backend == NV_OK) {
            const NvU32 assertions = s540RsBackendAssertionFailures();
            S540_RESOURCE_RESULT actual{};
            s540ResourceExercise(&actual);
            result.checks += actual.checks; result.failures += actual.failures;
            result.server = result.server && actual.server;
            result.clients = actual.clients; result.resources = actual.resources;
            result.sharing = actual.sharing; result.control = actual.control;
            result.cleanup = result.cleanup && actual.cleanup;
            expect(result, result.cleanup, s540RsBackendLiveLocks() == 0 &&
                s540RsBackendLiveTlsEntries() == 0 &&
                s540RsBackendAssertionFailures() == assertions);
            expect(result, result.cleanup, s540RsBackendShutdown() == NV_TRUE);
        }
        expect(result, result.cleanup, s540NvportRuntimeShutdown() == NV_OK);
    }
    expect(result, result.cleanup, s540RsBackendIsCold() == NV_TRUE &&
        s540NvportRuntimeIsCold() == NV_TRUE && S540NvidiaReserve::liveSlots() == 0 &&
        S540NvidiaMutex::liveObjects() == mutexes && S540NvidiaSpinlock::liveObjects() == spins);
    if (S540NvidiaReserve::liveSlots() == 0 && s540NvportRuntimeIsCold() == NV_TRUE)
        expect(result, result.cleanup, S540NvidiaReserve::shutdown());
    expect(result, result.cleanup, !S540NvidiaReserve::ready() &&
        S540NvidiaReserve::liveSlots() == 0 && s540RsBackendIsCold() == NV_TRUE &&
        s540NvportRuntimeIsCold() == NV_TRUE);
    return result;
}
