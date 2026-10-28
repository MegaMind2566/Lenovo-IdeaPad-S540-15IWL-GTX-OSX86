    NV_STATUS prepareTopology();
    void *topologyHandle(NvU32 segment, NvU8 bus, NvU8 device, NvU8 function,
        NvU16 *vendor, NvU16 *deviceId);
    NV_STATUS readTopology(void *handle, NvU32 offset, NvU32 width, NvU32 &value);
    NV_STATUS validateTopology(const S540PciTopologyGspFacts &facts);
    bool topologyReady() const;
