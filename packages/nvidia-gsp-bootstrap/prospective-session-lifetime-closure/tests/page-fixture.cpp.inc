struct RetainedPageFixture { void *token = nullptr; NvU8 *bytes = nullptr; };
NV_STATUS retireDiagnosticPage(void *opaque, void *) {
    auto &page = *static_cast<RetainedPageFixture *>(opaque);
    auto *session = S540NvidiaDeviceTransport::boundRmSession();
    expect(session && session->hardwareDmaLifetimeHeld(), "real bound session exposes actual hardware hold");
    NvU64 addresses[1] = {};
    expect(session->allocate(1, addresses, &page.token) == NV_OK && page.token && addresses[0],
        "real Session allocates fixture physical page through genuine backend");
    const NvU8 value = 0x5a;
    void *bytes = nullptr;
    expect(session->hostWrite(page.token, 0, &value, 1) == NV_OK &&
        session->borrowHost(page.token, 0, 1, &bytes) == NV_OK && bytes,
        "real Session CPU mapping contains owned bytes");
    page.bytes = static_cast<NvU8 *>(bytes);
    expect(session->mapDma(page.token, addresses) == NV_OK,
        "real Session publishes fixture device mapping before retirement");
    expect(session->unmapDma(page.token, addresses) == NV_ERR_IN_USE,
        "ordinary unmap cannot discard an addressable mapping while hold exists");
    bool deferred = false;
    expect(session->unmapRmDma(page.token, addresses, deferred) == NV_OK && deferred,
        "logical RM unmap retains actual mapped backing");
    deferred = false;
    expect(session->releaseRmAllocation(page.token, deferred) == NV_OK && deferred,
        "logical RM release retains actual physical allocation");
    const auto retired = session->retirementStatistics();
    expect(retired.allocations == 1 && retired.dmaMappings == 1 && retired.pages == 1 &&
        session->reclaimRmRetirement(page.token) == NV_ERR_IN_USE &&
        session->checkRmRetirementDrain() == NV_ERR_IN_USE &&
        S540NvidiaDeviceTransport::unbindRmDevice(session) == NV_ERR_IN_USE && page.bytes[0] == value,
        "real hold independently prevents retirement reclamation and device unbind");
    return NV_OK;
}
