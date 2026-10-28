/* Check completed original chipset facts without invoking chipset discovery
 * again. CS_UNKNOWN is supported when all real identities are verified.
 * A failed check precedes bInInit, FRTS/FWSEC and any GSP firmware boot.
 */
static NV_STATUS _s540RequirePciTopology(OBJGPU *pGpu)
{
    OBJSYS *pSys = SYS_GET_INSTANCE();
    OBJCL *pCl = pSys ? SYS_GET_CL(pSys) : NULL;
    OBJOS *pOs = pSys ? SYS_GET_OS(pSys) : NULL;
    S540PciTopologyGspFacts facts = {0};
    if (pGpu == NULL || pCl == NULL || pOs == NULL ||
        !pOs->getProperty(pOs, PDB_PROP_OS_DOES_NOT_ALLOW_DIRECT_PCIE_MAPPINGS) ||
        !pCl->FHBAddr.valid || pCl->FHBAddr.handle == NULL ||
        !pCl->chipsetIDBusAddr.valid || pCl->chipsetIDBusAddr.handle == NULL ||
        !pGpu->gpuClData.upstreamPort.addr.valid ||
        pGpu->gpuClData.upstreamPort.addr.handle == NULL)
        return NV_ERR_NOT_SUPPORTED;
    facts.format = 1U;
    facts.bytes = sizeof(facts);
    facts.fhb.handle = pCl->FHBAddr.handle;
    facts.fhb.segment = pCl->FHBAddr.domain;
    facts.fhb.bus = pCl->FHBAddr.bus;
    facts.fhb.device = pCl->FHBAddr.device;
    facts.fhb.function = pCl->FHBAddr.func;
    facts.fhb.vendor = pCl->FHBBusInfo.vendorID;
    facts.fhb.deviceId = pCl->FHBBusInfo.deviceID;
    facts.chipset.handle = pCl->chipsetIDBusAddr.handle;
    facts.chipset.segment = pCl->chipsetIDBusAddr.domain;
    facts.chipset.bus = pCl->chipsetIDBusAddr.bus;
    facts.chipset.device = pCl->chipsetIDBusAddr.device;
    facts.chipset.function = pCl->chipsetIDBusAddr.func;
    facts.chipset.vendor = pCl->chipsetIDInfo.vendorID;
    facts.chipset.deviceId = pCl->chipsetIDInfo.deviceID;
    facts.upstream.handle = pGpu->gpuClData.upstreamPort.addr.handle;
    facts.upstream.segment = pGpu->gpuClData.upstreamPort.addr.domain;
    facts.upstream.bus = pGpu->gpuClData.upstreamPort.addr.bus;
    facts.upstream.device = pGpu->gpuClData.upstreamPort.addr.device;
    facts.upstream.function = pGpu->gpuClData.upstreamPort.addr.func;
    facts.upstream.vendor = pGpu->gpuClData.upstreamPort.VendorID;
    facts.upstream.deviceId = pGpu->gpuClData.upstreamPort.DeviceID;
    return s540PciTopologyValidateForGsp(pGpu->pOsGpuInfo, &facts);
}
