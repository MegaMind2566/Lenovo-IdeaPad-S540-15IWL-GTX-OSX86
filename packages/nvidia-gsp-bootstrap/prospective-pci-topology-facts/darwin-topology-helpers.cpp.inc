NV_STATUS S540NvidiaDeviceTransport::prepareDarwinTopology(void *opaque,
    const void *owner, const Snapshot &snapshot) {
    return ::prepareTopology(static_cast<Platform *>(opaque), owner, snapshot);
}
void *S540NvidiaDeviceTransport::darwinTopologyHandle(void *opaque, const void *owner,
    NvU32 segment, NvU8 bus, NvU8 device, NvU8 function, NvU16 *vendor, NvU16 *deviceId) {
    auto *p = static_cast<Platform *>(opaque);
    if (!ordinary(p) || !live(p)) return nullptr;
    return S540NvidiaPciTopology::find(p->topology, owner, segment, bus, device, function, vendor, deviceId);
}
NV_STATUS S540NvidiaDeviceTransport::readDarwinTopology(void *opaque, const void *owner,
    void *handle, NvU32 offset, NvU32 width, NvU32 &value) {
    auto *p = static_cast<Platform *>(opaque);
    if (!ordinary(p) || !live(p)) return NV_ERR_INVALID_STATE;
    return S540NvidiaPciTopology::read(p->topology, owner, handle, offset, width, value);
}
NV_STATUS S540NvidiaDeviceTransport::validateDarwinTopology(void *opaque,
    const void *owner, const Snapshot &snapshot, const S540PciTopologyGspFacts &facts) {
    auto *p = static_cast<Platform *>(opaque);
    NV_STATUS status = verifyTopologyGpu(p, snapshot);
    if (status != NV_OK) return status;
    status = S540NvidiaPciTopology::validate(p->topology, owner, facts);
    if (status != NV_OK) return status;
    return verifyTopologyGpu(p, snapshot);
}
bool S540NvidiaDeviceTransport::darwinTopologyReady(void *opaque, const void *owner) {
    auto *p = static_cast<Platform *>(opaque);
    return ordinary(p) && live(p) && S540NvidiaPciTopology::ready(p->topology, owner);
}
