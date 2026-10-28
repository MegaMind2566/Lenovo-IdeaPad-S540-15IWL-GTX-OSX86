/* This validates the actual GPU edge, independently of cached topology bus
 * numbers. The existing retained provider owns its lifetime; arbitration is
 * held only for these scalar identity reads, never across ancestor reads.
 */
NV_STATUS verifyTopologyGpu(Platform *p, const Snapshot &snapshot) {
    if (!ordinary(p) || !live(p) || !snapshot.segmentKnown) return NV_ERR_INVALID_STATE;
    auto *provider = p->provider;
    if (!provider->lockForArbitration(false)) return NV_ERR_BUSY_RETRY;
    bool usable = live(p) && p->provider == provider &&
        provider->getBusNumber() == snapshot.bus &&
        provider->getDeviceNumber() == snapshot.device &&
        provider->getFunctionNumber() == snapshot.function;
    NvU32 identity = 0U, revision = 0U, subsystem = 0U;
    if (usable) {
        identity = provider->configRead32(static_cast<UInt8>(0U));
        revision = provider->configRead32(static_cast<UInt8>(8U));
        subsystem = provider->configRead32(static_cast<UInt8>(0x2cU));
    }
    usable = usable && live(p) && p->provider == provider &&
        identity == 0x1f9110deU && revision == 0x030000a1U && subsystem == 0x380617aaU;
    provider->unlockForArbitration();
    return usable ? NV_OK : NV_ERR_INVALID_STATE;
}
/* Called only in ordinary pre-original Session preparation. Actual resource
 * ancestry is bounded and retained; the original exhaustive DBDF scan later
 * sees only a fixed table, never a global registry or hardware enumeration.
 */
NV_STATUS topologyRawRead(void *opaque,
    const S540NvidiaPciTopology::Candidate &candidate,
    NvU32 offset, NvU32 width, NvU32 &value) {
    auto *p = static_cast<Platform *>(opaque);
    if (!ordinary(p) || !live(p) || !candidate.resource ||
        (width != 1U && width != 2U && width != 4U) || offset >= 4096U ||
        width > 4096U - offset || (offset & (width - 1U))) return NV_ERR_INVALID_STATE;
    NvU32 captured = 0U;
    if (candidate.rootConfig) {
        if (candidate.segment || candidate.bus || candidate.device || candidate.function ||
            offset >= 256U || width > 256U - offset) return NV_ERR_NOT_SUPPORTED;
        auto *bridge = static_cast<IOPCIBridge *>(candidate.resource);
        if (bridge->isInactive() || bridge->firstBusNum() != 0U ||
            bridge->lastBusNum() < p->topology.gpuBus || !bridge->lockForArbitration(false))
            return NV_ERR_INVALID_STATE;
        const bool usable = !bridge->isInactive() && live(p) && bridge->firstBusNum() == 0U &&
            bridge->lastBusNum() >= p->topology.gpuBus;
        if (usable) {
            IOPCIAddressSpace space{};
            space.s.busNum = candidate.bus; space.s.deviceNum = candidate.device;
            space.s.functionNum = candidate.function;
            if (width == 1U) captured = bridge->configRead8(space, static_cast<UInt8>(offset));
            else if (width == 2U) captured = bridge->configRead16(space, static_cast<UInt8>(offset));
            else captured = bridge->configRead32(space, static_cast<UInt8>(offset));
        }
        bridge->unlockForArbitration();
        if (!usable) return NV_ERR_INVALID_STATE;
    } else {
        auto *device = static_cast<IOPCIDevice *>(candidate.resource);
        if (device->isInactive() || !device->lockForArbitration(false)) return NV_ERR_INVALID_STATE;
        const bool usable = !device->isInactive() && live(p) &&
            device->getBusNumber() == candidate.bus && device->getDeviceNumber() == candidate.device &&
            device->getFunctionNumber() == candidate.function;
        if (usable) {
            if (width == 1U) captured = device->extendedConfigRead8(offset);
            else if (width == 2U) captured = device->extendedConfigRead16(offset);
            else captured = device->extendedConfigRead32(offset);
        }
        device->unlockForArbitration();
        if (!usable) return NV_ERR_INVALID_STATE;
    }
    value = captured;
    return NV_OK;
}
void releaseTopologyCandidates(S540NvidiaPciTopology::Candidate *candidates, NvU32 count) {
    for (NvU32 i = 0U; i != count; ++i) {
        if (candidates[i].resource) {
            static_cast<OSObject *>(candidates[i].resource)->release();
            candidates[i].resource = nullptr;
        }
    }
}
void releaseDarwinTopology(Platform *p) {
    for (NvU32 i = 0U; i != p->topology.count; ++i)
        if (p->topology.records[i].candidate.resource)
            static_cast<OSObject *>(p->topology.records[i].candidate.resource)->release();
    S540NvidiaPciTopology::clear(p->topology);
}
NV_STATUS prepareTopology(Platform *p, const void *owner, const Snapshot &snapshot) {
    using namespace S540NvidiaPciTopology;
    if (!ordinary(p) || !live(p) || !owner || !snapshot.segmentKnown ||
        snapshot.segment > 0xffffU || p->topology.owner) return NV_ERR_INVALID_STATE;
    if (p->provider->getBusNumber() != snapshot.bus || p->provider->getDeviceNumber() != snapshot.device ||
        p->provider->getFunctionNumber() != snapshot.function) return NV_ERR_INVALID_STATE;
    Candidate *candidates = p->topologyCandidates;
    for (NvU32 i = 0U; i != kMaximumRecords; ++i) candidates[i] = Candidate{};
    Candidate host{};
    NvU32 bridges = 0U, depth = 0U;
    IOPCIBridge *rootBridge = nullptr;
    NV_STATUS status = NV_OK;
    IORegistryEntry *entry = p->provider;
    entry->retain();
    while (entry && depth++ != kMaximumAncestry) {
        /* Retained copy, including across a concurrent registry detach. */
        IORegistryEntry *parent = entry->copyParentEntry(gIOServicePlane);
        auto *device = OSDynamicCast(IOPCIDevice, entry);
        if (device && device != p->provider) {
            if (device->isInactive() || !device->lockForArbitration(false)) status = NV_ERR_INVALID_STATE;
            else {
                const bool usable = !device->isInactive() && live(p);
                const NvU32 identity = usable ? device->configRead32(static_cast<UInt8>(0U)) : ~0U;
                const NvU32 revision = usable ? device->configRead32(static_cast<UInt8>(8U)) : ~0U;
                Candidate candidate{device, snapshot.segment, device->getBusNumber(),
                    device->getDeviceNumber(), device->getFunctionNumber(), false};
                device->unlockForArbitration();
                if (!usable || !identity || identity == ~0U || revision == ~0U) status = NV_ERR_INVALID_DATA;
                else if (((revision >> 16U) & 0xffffU) == 0x0604U) {
                    if (bridges == kMaximumBridges || host.resource) status = NV_ERR_NOT_SUPPORTED;
                    else { device->retain(); candidates[bridges++] = candidate; }
                } else if (((revision >> 16U) & 0xffffU) == 0x0600U) {
                    if (host.resource) status = NV_ERR_INVALID_DATA;
                    else { device->retain(); host = candidate; }
                } else status = NV_ERR_NOT_SUPPORTED;
            }
        }
        auto *bridge = OSDynamicCast(IOPCIBridge, entry);
        if (status == NV_OK && bridge && parent && !OSDynamicCast(IOPCIDevice, parent) &&
            !bridge->isInactive() && bridge->firstBusNum() == 0U && bridge->lastBusNum() >= snapshot.bus) {
            if (rootBridge && rootBridge != bridge) status = NV_ERR_INVALID_DATA;
            else if (!rootBridge) { bridge->retain(); rootBridge = bridge; }
        }
        entry->release(); entry = parent;
        if (status != NV_OK) break;
    }
    if (entry) { entry->release(); if (status == NV_OK) status = NV_ERR_INSUFFICIENT_RESOURCES; }
    if (status == NV_OK && !bridges) status = NV_ERR_NOT_SUPPORTED;
    if (status == NV_OK && !host.resource) {
        if (snapshot.segment || !rootBridge) status = NV_ERR_NOT_SUPPORTED;
        else {
            host = Candidate{rootBridge, 0U, 0U, 0U, 0U, true};
            rootBridge = nullptr; /* Transfer this retained reference. */
        }
    }
    if (rootBridge) rootBridge->release();
    if (status == NV_OK) {
        candidates[bridges] = host; host.resource = nullptr;
        status = S540NvidiaPciTopology::prepare(p->topology, owner, snapshot.segment, snapshot.bus,
            Reader{p, topologyRawRead}, candidates, bridges + 1U);
        if (status != NV_OK) releaseTopologyCandidates(candidates, bridges + 1U);
        else for (NvU32 i = 0U; i != bridges + 1U; ++i) candidates[i] = Candidate{};
    } else releaseTopologyCandidates(candidates, bridges);
    if (host.resource) static_cast<OSObject *>(host.resource)->release();
    return status;
}
