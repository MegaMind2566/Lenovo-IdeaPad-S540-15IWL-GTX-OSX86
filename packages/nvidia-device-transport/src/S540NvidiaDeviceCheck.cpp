// SPDX-License-Identifier: MIT
#include "S540NvidiaDeviceTransport.hpp"
namespace {
using namespace S540NvidiaDeviceTransport;
void require(Result &result, bool passed) {
    ++result.checks;
    if (!passed) ++result.failures;
}
Result exercise(Session &session) {
    Result out{};
    out.owner = session.active() && session.snapshot().identity && session.snapshot().providerOwned;
    out.mapper = session.snapshot().mapper;
    require(out, out.owner);
    if (!out.owner) return out;
    const Snapshot snapshot = session.snapshot();
    out.mmio = snapshot.barMapped && snapshot.barBytes >= 0x1804;
    require(out, out.mmio);
    NvU32 untouched = 0x12345678;
    // No new GPU register loads: check invalid request boundaries only.
    require(out, session.readIdentification(1, untouched) == NV_ERR_NOT_SUPPORTED);
    require(out, untouched == 0x12345678);
    NvU64 ptes[4] = {0xabc, 0xabc, 0xabc, 0xabc};
    void *token = nullptr;
    require(out, session.allocate(4, ptes, &token) == NV_OK && token);
    if (token) {
        NvU64 firstPhysical = 0;
        require(out, session.address(token, 0, firstPhysical) == NV_OK && firstPhysical == ptes[0]);
        NvU64 before = 0x12345678;
        require(out, session.address(token, 4, before) == NV_ERR_INVALID_ARGUMENT && before == 0x12345678);
        NvU8 source[16]{}, destination[16]{};
        for (NvU32 i = 0; i < 16; ++i) source[i] = static_cast<NvU8>(i ^ 0xa5);
        require(out, session.hostWrite(token, kPageBytes - 8, source, sizeof(source)) == NV_OK);
        require(out, session.hostRead(token, kPageBytes - 8, destination, sizeof(destination)) == NV_OK);
        bool intact = true;
        for (NvU32 i = 0; i < 16; ++i) intact = source[i] == destination[i] && intact;
        require(out, intact);
        require(out, session.hostWrite(token, ~NvU64(0), source, sizeof(source)) == NV_ERR_INVALID_ARGUMENT);
        NV_STATUS mapped = session.mapDma(token, ptes);
        if (!snapshot.dmaPolicySettled || snapshot.mapper == Mapper::Unavailable) {
            out.dmaUnavailable = mapped == NV_ERR_NOT_SUPPORTED;
            require(out, out.dmaUnavailable && ptes[0] == firstPhysical);
            out.dmaLifecycle = out.dmaUnavailable;
        } else {
            out.dmaAddresses = mapped == NV_OK;
            require(out, out.dmaAddresses);
            if (mapped == NV_OK) {
                require(out, session.mapDma(token, ptes) == NV_ERR_STATE_IN_USE);
                out.dmaLifecycle = session.unmapDma(token, ptes) == NV_OK && ptes[0] == firstPhysical;
                require(out, out.dmaLifecycle);
            }
        }
        require(out, session.release(token) == NV_OK);
        require(out, session.release(token) == NV_ERR_OBJECT_NOT_FOUND);
    }
    out.interruptRefusal = session.installInterrupt(InterruptContract{}) == NV_ERR_NOT_SUPPORTED &&
        !session.interruptInstalled() && !session.interruptArmed();
    require(out, out.interruptRefusal);
    require(out, session.armInterrupt() == NV_ERR_INVALID_STATE);
    out.adapterGates = session.deliverFirmware(nullptr, 0) == NV_ERR_NOT_SUPPORTED &&
        session.transitionPower(0) == NV_ERR_NOT_SUPPORTED;
    require(out, out.adapterGates);
    out.cleanup = session.stop() == NV_OK && !session.active();
    require(out, out.cleanup);
    require(out, session.stop() == NV_OK);
    return out;
}
}
S540NvidiaDeviceTransport::Result S540NvidiaDeviceTransport::check(const Detail::Backend &backend) {
    Session session;
    const NV_STATUS status = session.start(backend);
    if (status != NV_OK) { Result out{}; out.checks = 1; out.failures = 1; return out; }
    return exercise(session);
}
#if defined(KERNEL)
S540NvidiaDeviceTransport::Result S540NvidiaDeviceTransport::check(IOPCIDevice *provider, IOService *owner) {
    Session session;
    const NV_STATUS status = session.start(provider, owner);
    if (status != NV_OK) { Result out{}; out.checks = 1; out.failures = 1; return out; }
    return exercise(session);
}
#endif
