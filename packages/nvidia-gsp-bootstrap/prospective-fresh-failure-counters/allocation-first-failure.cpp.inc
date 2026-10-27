static void observeAllocationFailureRequest(NvU32 pages, NvU64 pageBytes,
    NvBool contiguous, NvU32 cache, NvBool zeroed, NvBool unprotected, NvS32 node,
    const UnprotectedCpuObservation &cpu, NvU32 stage, NV_STATUS status) {
    S540DeviceAllocationFailure failure{};
    failure.stage = stage;
    failure.status = status;
    failure.pages = pages;
    failure.pageBytes = pageBytes;
    failure.contiguous = contiguous;
    failure.cache = cache;
    failure.zeroed = zeroed;
    failure.unprotected = unprotected;
    failure.node = node;
    // These are only the observations already taken by this exact request.
    // No extra CPUID instruction, encryption operation or pointer is recorded.
    failure.cpuObservedMask = cpu.observedMask;
    failure.maxBasic = cpu.basic.eax;
    failure.vendorEbx = cpu.basic.ebx;
    failure.vendorEdx = cpu.basic.edx;
    failure.vendorEcx = cpu.basic.ecx;
    failure.signature = cpu.signature.eax;
    failure.family = cpu.family;
    failure.model = cpu.model;
    failure.leaf1Ecx = cpu.signature.ecx;
    failure.leaf7Ecx = cpu.structured.ecx;
    observeAllocationFailure(failure);
}
