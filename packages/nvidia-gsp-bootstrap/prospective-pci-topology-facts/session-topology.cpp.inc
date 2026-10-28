NV_STATUS Session::prepareTopology() {
    if (!ordinary() || !live() || !snapshot_.segmentKnown) return NV_ERR_INVALID_STATE;
#if defined(KERNEL)
    if (!platformOwned_) return NV_ERR_NOT_SUPPORTED;
    return prepareDarwinTopology(backend_.context, this, snapshot_);
#else
    return NV_ERR_NOT_SUPPORTED;
#endif
}
void *Session::topologyHandle(NvU32 segment, NvU8 bus, NvU8 device, NvU8 function,
    NvU16 *vendor, NvU16 *deviceId) {
    if (!ordinary() || !live() || !snapshot_.segmentKnown || segment != snapshot_.segment) return nullptr;
#if defined(KERNEL)
    if (platformOwned_) return darwinTopologyHandle(backend_.context, this, segment,
        bus, device, function, vendor, deviceId);
#else
    (void)bus; (void)device; (void)function; (void)vendor; (void)deviceId;
#endif
    return nullptr;
}
NV_STATUS Session::readTopology(void *handle, NvU32 offset, NvU32 width, NvU32 &value) {
    if (!ordinary() || !live()) return NV_ERR_INVALID_STATE;
#if defined(KERNEL)
    if (platformOwned_) return readDarwinTopology(backend_.context, this, handle, offset, width, value);
#else
    (void)handle; (void)offset; (void)width; (void)value;
#endif
    return NV_ERR_NOT_SUPPORTED;
}
NV_STATUS Session::validateTopology(const S540PciTopologyGspFacts &facts) {
    if (!ordinary() || !live()) return NV_ERR_INVALID_STATE;
#if defined(KERNEL)
    if (platformOwned_) return validateDarwinTopology(backend_.context, this, snapshot_, facts);
#else
    (void)facts;
#endif
    return NV_ERR_NOT_SUPPORTED;
}
bool Session::topologyReady() const {
    if (!ordinary() || !live()) return false;
#if defined(KERNEL)
    return platformOwned_ && darwinTopologyReady(backend_.context, this);
#else
    return false;
#endif
}
