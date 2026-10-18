// SPDX-License-Identifier: MIT
#include "../src/S540NvidiaDeviceTransport.hpp"
#include "../src/nv_device_services.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <initializer_list>
#include <type_traits>
#include <csignal>
#include <sys/resource.h>
#include <sys/wait.h>
#include <unistd.h>
using namespace S540NvidiaDeviceTransport;
static_assert(std::is_same<decltype(&s540Global_nv_requires_dma_remap),
    NvBool (NV_API_CALL *)(nv_state_t *)>::value, "Original NVIDIA DMA-remap ABI");
namespace {
NvU32 assertions = 0;
void expect(bool condition, const char *message) {
    ++assertions;
    if (!condition) { std::fprintf(stderr, "Device transport assertion failed: %s\n", message); std::exit(1); }
}
enum class Fault { None, Start, Allocate, Physical, Map, DeviceAddress, Unmap, Release, Install, Arm, StopIrq, Stop };
struct Memory { NvU8 *host; NvU32 pages; bool mapped; NvU64 physical; };
struct DirectFixture {
    Detail::DirectRouteFacts before{reinterpret_cast<void *>(NvUPtr(0x900)),true,false,false,true};
    Detail::DirectRouteFacts after = before;
    NV_STATUS observationStatus = NV_OK;
    NV_STATUS afterStatus = NV_OK;
    NV_STATUS factoryStatus = NV_OK;
    bool provideProbe = true;
    bool factoryActive = false;
    NvU32 factoryCalls = 0;
    NvU32 releases = 0;
    NvU32 liveProbes = 0;
};
NV_STATUS directObserve(void *opaque, Detail::DirectRouteFacts &facts) {
    auto &f = *static_cast<DirectFixture *>(opaque);
    const NV_STATUS status = f.factoryActive ? f.afterStatus : f.observationStatus;
    if (status != NV_OK) return status;
    facts = f.factoryActive ? f.after : f.before;
    return NV_OK;
}
NV_STATUS directProbe(void *opaque, void **out) {
    auto &f = *static_cast<DirectFixture *>(opaque);
    ++f.factoryCalls;
    if (f.provideProbe) {
        *out = new NvU32(0x540);
        ++f.liveProbes;
        f.factoryActive = true;
    }
    return f.factoryStatus;
}
void directRelease(void *opaque, void *probe) {
    auto &f = *static_cast<DirectFixture *>(opaque);
    delete static_cast<NvU32 *>(probe);
    ++f.releases; --f.liveProbes; f.factoryActive = false;
}
Detail::DirectRouteBackend directBackend(DirectFixture &f) {
    return Detail::DirectRouteBackend{&f,directObserve,directProbe,directRelease};
}
struct Fake {
    Fault fault = Fault::None;
    bool failRelease = false;
    bool failUnmap = false;
    bool badSnapshot = false;
    Mapper mapper = Mapper::Device;
    DirectFixture *direct = nullptr;
    DmaRemapPolicy remapPolicy = DmaRemapPolicy::MapPhysicalPagesWithoutBounce;
    NV_STATUS remapStatus = NV_OK;
    NvU32 policyQueries = 0;
    NvU32 resources = 0;
    NvU32 nextMemory = 0;
    NvU32 mapCalls = 0;
    NvU32 unmapCalls = 0;
    NvU32 releaseCalls = 0;
    NvU32 retainedValidations = 0;
    bool retainedMappingValid = true;
    NvU32 registerReads = 0;
    bool active = false;
    bool ordinary = true;
    bool readyForInterrupt = true;
    bool irq = false;
    bool armed = false;
    bool enableAttempted = false;
    bool failMask = false;
    bool failStopAfterMask = false;
    bool hardwareMaskRequired = false;
    bool retireOnMask = false;
    nv_state_t *maskState = nullptr;
    nv_dma_device_t *maskDma = nullptr;
    void *maskAllocation = nullptr;
    NvU64 maskPages[2]{};
    NvU32 maskCalls = 0;
    NvU32 topCalls = 0;
    NvU32 lockedCalls = 0;
    NvU32 unlockedCalls = 0;
    NvU16 command = 2;
    InterruptContract contract{};
};
bool ordinary(void *opaque) { return static_cast<Fake *>(opaque)->ordinary; }
NV_STATUS start(void *opaque, Snapshot &out) {
    auto &f = *static_cast<Fake *>(opaque);
    if (f.fault == Fault::Start) return NV_ERR_NOT_SUPPORTED;
    f.active = true;
    out = Snapshot{!f.badSnapshot, true, true, true, true, true, f.mapper != Mapper::Unavailable, 64, f.mapper, 0x1000000, 0, 1, 0, 0, true, 0x10000, true, true, true, false};
    return NV_OK;
}
NV_STATUS stop(void *opaque) {
    auto &f = *static_cast<Fake *>(opaque);
    if (f.fault == Fault::Stop || f.resources || f.irq) return NV_ERR_IN_USE;
    f.active = false;
    return NV_OK;
}
bool live(void *opaque) { return static_cast<Fake *>(opaque)->active; }
NV_STATUS readIdentification(void *opaque, NvU32 offset, NvU32 &out) {
    ++static_cast<Fake *>(opaque)->registerReads;
    out = offset ? 0x1f9110de : 0x167000a1;
    return NV_OK;
}
NV_STATUS allocate(void *opaque, NvU32 pages, bool, NvU32, void **out, NvU8 **host) {
    auto &f = *static_cast<Fake *>(opaque);
    if (f.fault == Fault::Allocate) return NV_ERR_NO_MEMORY;
    auto *memory = new Memory{};
    memory->host = static_cast<NvU8 *>(std::calloc(pages, kPageBytes));
    if (!memory->host) { delete memory; return NV_ERR_NO_MEMORY; }
    memory->pages = pages;
    memory->physical = 0x10000000ULL + NvU64(f.nextMemory++) * 0x100000;
    ++f.resources;
    *host = memory->host; *out = memory;
    return NV_OK;
}
NV_STATUS pageAddress(void *opaque, void *memory, NvU32 page, bool mapped, NvU64 &out) {
    auto &f = *static_cast<Fake *>(opaque);
    auto *m = static_cast<Memory *>(memory);
    if (page >= m->pages || (mapped && !m->mapped)) return NV_ERR_INVALID_ARGUMENT;
    out = m->physical + (mapped && f.mapper != Mapper::Direct ? 0x10000000ULL : 0) + NvU64(page) * kPageBytes;
    if ((!mapped && f.fault == Fault::Physical) || (mapped && f.fault == Fault::DeviceAddress)) ++out;
    return NV_OK;
}
NV_STATUS mapDma(void *opaque, void *memory, NvU32 bits) {
    auto &f = *static_cast<Fake *>(opaque);
    ++f.mapCalls;
    if (f.mapper == Mapper::Direct && (!f.direct || Detail::attestDirectRoute(directBackend(*f.direct)) != NV_OK))
        return NV_ERR_NOT_SUPPORTED;
    auto *m = static_cast<Memory *>(memory);
    if (f.fault == Fault::Map || bits < 32) return NV_ERR_OPERATING_SYSTEM;
    m->mapped = true;
    return NV_OK;
}
NV_STATUS unmapDma(void *opaque, void *memory) {
    auto &f = *static_cast<Fake *>(opaque);
    ++f.unmapCalls;
    if (f.fault == Fault::Unmap || f.failUnmap) return NV_ERR_OPERATING_SYSTEM;
    static_cast<Memory *>(memory)->mapped = false;
    return NV_OK;
}
NV_STATUS release(void *opaque, void *memory) {
    auto &f = *static_cast<Fake *>(opaque);
    ++f.releaseCalls;
    auto *m = static_cast<Memory *>(memory);
    if (f.fault == Fault::Release || f.failRelease || m->mapped) return NV_ERR_OPERATING_SYSTEM;
    std::free(m->host); delete m; --f.resources;
    return NV_OK;
}
NV_STATUS install(void *opaque, const InterruptContract &contract) {
    auto &f = *static_cast<Fake *>(opaque);
    if (f.fault == Fault::Install) return NV_ERR_OPERATING_SYSTEM;
    f.contract = contract; f.irq = true;
    return NV_OK;
}
NV_STATUS arm(void *opaque) {
    auto &f = *static_cast<Fake *>(opaque);
    f.enableAttempted = f.hardwareMaskRequired = true;
    // Model an OS controller that changes state and subsequently reports a
    // failure. The Session must retain memory even though irqArmed is false.
    f.armed = true;
    if (f.fault == Fault::Arm) return NV_ERR_OPERATING_SYSTEM;
    return NV_OK;
}
NV_STATUS stopIrq(void *opaque) {
    auto &f = *static_cast<Fake *>(opaque);
    if (f.fault == Fault::StopIrq) return NV_ERR_BUSY_RETRY;
    if (f.hardwareMaskRequired) {
        if (f.contract.maskHardware(f.contract.context) != NV_OK) return NV_ERR_OPERATING_SYSTEM;
        f.hardwareMaskRequired = false;
    }
    if (f.failStopAfterMask) return NV_ERR_BUSY_RETRY;
    f.enableAttempted = false;
    f.irq = f.armed = false;
    return NV_OK;
}
NV_STATUS configRead(void *opaque, NvU32 offset, NvU32 width, NvU32 &value) {
    auto &f = *static_cast<Fake *>(opaque);
    if (!f.active) return NV_ERR_INVALID_STATE;
    NvU32 base = 0;
    switch (offset & ~3U) {
        case 0: base = 0x1f9110de; break;
        case 4: base = f.command; break;
        case 8: base = 0x030200a1; break;
        case 0x2c: base = 0x380617aa; break;
        case 0x100: base = 0x12345678; break;
    }
    value = (base >> ((offset & 3U) * 8)) & (width == 4 ? ~NvU32(0) : ((NvU32(1) << (width * 8)) - 1));
    return NV_OK;
}
NV_STATUS configWrite(void *opaque, NvU32 offset, NvU32 width, NvU32 value) {
    auto &f = *static_cast<Fake *>(opaque);
    if (pciWriteKind(offset,width,f.command,value) == PciWriteKind::Refused)
        return NV_ERR_NOT_SUPPORTED;
    f.command = static_cast<NvU16>(value);
    return NV_OK;
}
NV_STATUS dmaRemapPolicy(void *opaque, DmaRemapPolicy &policy) {
    auto &f = *static_cast<Fake *>(opaque);
    ++f.policyQueries;
    if (f.remapStatus != NV_OK) return f.remapStatus;
    if (f.mapper == Mapper::Direct) {
        if (!f.direct) return NV_ERR_NOT_SUPPORTED;
        const NV_STATUS status = Detail::attestDirectRoute(directBackend(*f.direct));
        if (status != NV_OK) return status;
    }
    policy = f.remapPolicy;
    return NV_OK;
}
NV_STATUS validateRetainedDma(void *opaque, void *memory, NvU32 bits) {
    auto &f = *static_cast<Fake *>(opaque);
    ++f.retainedValidations;
    if (f.mapper == Mapper::Direct && (!f.direct || Detail::attestDirectRoute(directBackend(*f.direct)) != NV_OK))
        return NV_ERR_NOT_SUPPORTED;
    return f.active && f.retainedMappingValid && static_cast<Memory *>(memory)->mapped &&
           bits >= 32 && bits <= 64 ? NV_STATUS(NV_OK) : NV_STATUS(NV_ERR_INVALID_STATE);
}
Detail::Backend backend(Fake &f) {
    return Detail::Backend{&f, ordinary, start, stop, live, readIdentification,
        allocate, pageAddress, mapDma, unmapDma, release, install, arm, stopIrq,
        nullptr, nullptr, nullptr, configRead, configWrite, nullptr, dmaRemapPolicy,
        validateRetainedDma};
}
bool top(void *opaque, bool &locked, bool &unlocked) {
    ++static_cast<Fake *>(opaque)->topCalls; locked = unlocked = true; return true;
}
void locked(void *opaque) { ++static_cast<Fake *>(opaque)->lockedCalls; }
void unlocked(void *opaque) { ++static_cast<Fake *>(opaque)->unlockedCalls; }
NV_STATUS mask(void *opaque) {
    auto &f = *static_cast<Fake *>(opaque);
    ++f.maskCalls;
    if (f.retireOnMask) {
        void *allocation = f.maskAllocation;
        NV_STATUS status = s540Global_nv_dma_unmap_alloc(f.maskDma, 2, f.maskPages, &allocation);
        if (status != NV_OK) return status;
        status = s540Global_nv_free_pages(f.maskState, 2, NV_FALSE, 0, allocation);
        if (status != NV_OK) return status;
        f.retireOnMask = false;
    }
    return f.failMask ? NV_STATUS(NV_ERR_NOT_READY) : NV_STATUS(NV_OK);
}
bool ready(void *opaque) { return static_cast<Fake *>(opaque)->active && static_cast<Fake *>(opaque)->readyForInterrupt; }
InterruptContract contract(Fake &f) { return InterruptContract{&f, top, locked, unlocked, mask, ready}; }
void expectDmaPolicyFatal(nv_state_t *state, const char *message) {
    const pid_t child = fork();
    expect(child >= 0, "DMA policy refusal subprocess");
    if (!child) {
        const rlimit noCore{0, 0};
        (void)setrlimit(RLIMIT_CORE, &noCore);
        if (!std::freopen("/dev/null", "w", stderr)) _exit(13);
        const NvBool scalar = s540Global_nv_requires_dma_remap(state);
        _exit(scalar ? 11 : 12);
    }
    int status = 0;
    expect(waitpid(child, &status, 0) == child, "DMA policy refusal subprocess reaped");
    expect(WIFSIGNALED(status) && WTERMSIG(status) == SIGABRT, message);
}
void directRouteTests() {
    expect(Detail::attestDirectRoute(Detail::DirectRouteBackend{}) == NV_ERR_INVALID_ARGUMENT,
           "direct admission requires actual observation and command operations");
    for (NvU32 missing = 0; missing != 5; ++missing) {
        DirectFixture f;
        if (missing == 0) f.before.platformIdentity = nullptr;
        if (missing == 1) f.before.platformLive = false;
        if (missing == 2) f.before.platformMapperPresent = true;
        if (missing == 3) f.before.providerMapperPresent = true;
        if (missing == 4) f.before.factoryWouldNotWait = false;
        expect(Detail::attestDirectRoute(directBackend(f)) == NV_ERR_NOT_SUPPORTED &&
               !f.factoryCalls && !f.liveProbes,
               "unpublished/inactive/mapped/unresolved framework never reaches a potentially waiting factory");
    }
    {
        DirectFixture f; f.observationStatus = NV_ERR_BUSY_RETRY;
        expect(Detail::attestDirectRoute(directBackend(f)) == NV_ERR_BUSY_RETRY && !f.factoryCalls,
               "provider observation refusal cannot become direct policy");
    }
    {
        DirectFixture f; f.provideProbe = false;
        expect(Detail::attestDirectRoute(directBackend(f)) == NV_ERR_NOT_SUPPORTED &&
               f.factoryCalls == 1 && !f.releases,
               "settled-None metadata without a real accepted command never attests bypass");
    }
    {
        DirectFixture f; f.factoryStatus = NV_ERR_NOT_SUPPORTED;
        expect(Detail::attestDirectRoute(directBackend(f)) == NV_ERR_NOT_SUPPORTED &&
               f.factoryCalls == 1 && f.releases == 1 && !f.liveProbes,
               "partial factory refusal releases its resource without attesting policy");
    }
    for (NvU32 changed = 0; changed != 6; ++changed) {
        DirectFixture f;
        if (changed == 0) f.after.platformIdentity = reinterpret_cast<void *>(NvUPtr(0x901));
        if (changed == 1) f.after.platformLive = false;
        if (changed == 2) f.after.platformMapperPresent = true;
        if (changed == 3) f.after.providerMapperPresent = true;
        if (changed == 4) f.after.factoryWouldNotWait = false;
        if (changed == 5) f.afterStatus = NV_ERR_BUSY_RETRY;
        expect(Detail::attestDirectRoute(directBackend(f)) != NV_OK &&
               f.factoryCalls == 1 && f.releases == 1 && !f.liveProbes,
               "post-factory policy/provider change revokes admission and releases the probe");
    }
    {
        DirectFixture proof;
        expect(Detail::attestDirectRoute(directBackend(proof)) == NV_OK &&
               proof.factoryCalls == 1 && proof.releases == 1 && !proof.liveProbes,
               "completed framework observations and actual factory acceptance attest direct route");
        Fake f; f.mapper = Mapper::Direct; f.direct = &proof;
        Session session;
        auto *state = reinterpret_cast<nv_state_t *>(NvUPtr(0x950));
        auto *dma = reinterpret_cast<nv_dma_device_t *>(NvUPtr(0x960));
        expect(session.start(backend(f)) == NV_OK && bindRmDevice(&session,state,dma) == NV_OK,
               "attested direct route binds the exact RM owner");
        NvBool required = NV_FALSE;
        expect(queryRmDmaRemap(state,required) == NV_OK && required == NV_TRUE &&
               s540Global_nv_requires_dma_remap(state) == NV_TRUE,
               "direct IOKit route still requires NVIDIA's explicit mapping callbacks");
        NvU64 pages[2]{}; void *allocation = nullptr;
        expect(s540Global_nv_alloc_pages(state,2,4096,NV_FALSE,0,NV_TRUE,NV_FALSE,-1,pages,&allocation) == NV_OK,
               "direct mapping has real fixture-owned physical backing");
        const NvU64 physical = pages[0]; void *original = allocation;
        expect(s540Global_nv_dma_map_alloc(dma,2,pages,NV_FALSE,NV_FALSE,&allocation) == NV_OK &&
               pages[0] == physical && allocation != original &&
               session.installInterrupt(contract(f)) == NV_OK && session.armInterrupt() == NV_OK,
               "direct explicit map validates identity pages and retains distinct ownership");
        expect(s540Global_nv_dma_unmap_alloc(dma,2,pages,&allocation) == NV_OK && !f.unmapCalls,
               "direct logical unmap retains the prepared command while IRQ can run");
        proof.after.providerMapperPresent = true;
        required = NV_FALSE;
        expect(queryRmDmaRemap(state,required) == NV_ERR_NOT_SUPPORTED && required == NV_FALSE &&
               s540Global_nv_dma_map_alloc(dma,2,pages,NV_FALSE,NV_FALSE,&allocation) == NV_ERR_NOT_SUPPORTED &&
               allocation == original && pages[0] == physical && !f.unmapCalls,
               "new provider mapper revokes retained direct mapping without reclaiming addressable pages");
        proof.after.providerMapperPresent = false;
        expect(s540Global_nv_dma_map_alloc(dma,2,pages,NV_FALSE,NV_FALSE,&allocation) == NV_OK &&
               pages[0] == physical && f.mapCalls == 1 && !f.unmapCalls,
               "direct retained mapping can reactivate only after fresh framework attestation");
        expect(s540Global_nv_dma_unmap_alloc(dma,2,pages,&allocation) == NV_OK &&
               s540Global_nv_free_pages(state,2,NV_FALSE,0,allocation) == NV_OK &&
               session.stopInterrupt() == NV_OK && drainRmRetirements(&session) == NV_OK &&
               !f.resources && !proof.liveProbes && proof.factoryCalls == proof.releases,
               "direct command probes and retirement owners all finish after actual IRQ drain");
        expect(unbindRmDevice(&session) == NV_OK && session.stop() == NV_OK,
               "attested direct lifecycle cleanup");
    }
}

void dmaRemapTests() {
    auto *state = reinterpret_cast<nv_state_t *>(NvUPtr(0x300));
    auto *foreign = reinterpret_cast<nv_state_t *>(NvUPtr(0x301));
    auto *dma = reinterpret_cast<nv_dma_device_t *>(NvUPtr(0x400));
    NvBool required = NV_FALSE;
    expect(queryRmDmaRemap(state, required) == NV_ERR_INVALID_STATE && required == NV_FALSE,
           "unbound scalar admission refuses without publishing a Boolean");
    expectDmaPolicyFatal(state, "unbound scalar callback cannot fabricate false");
    {
        Fake f; Session session;
        Detail::Backend withoutPolicy = backend(f); withoutPolicy.dmaRemapPolicy = nullptr;
        expect(session.start(withoutPolicy) == NV_OK, "mapper metadata without policy start");
        required = NV_TRUE;
        expect(session.requiresDmaRemap(required) == NV_ERR_NOT_SUPPORTED && required == NV_TRUE &&
               !f.policyQueries, "published mapper alone never supplies RM policy");
        expect(session.stop() == NV_OK, "missing policy owner cleanup");
    }
    for (Mapper mapper : {Mapper::Unavailable, Mapper::Direct, Mapper::System}) {
        Fake f; f.mapper = mapper; f.remapPolicy = DmaRemapPolicy::Unavailable;
        Session session;
        expect(session.start(backend(f)) == NV_OK && bindRmDevice(&session, state, dma) == NV_OK,
               "unattested policy fixture binding");
        required = NV_TRUE;
        expect(queryRmDmaRemap(state, required) == NV_ERR_NOT_SUPPORTED && required == NV_TRUE,
               "unavailable/direct/system mapper cannot infer bypass or mapping policy");
        expectDmaPolicyFatal(state, "unknown bound scalar policy terminates without a result");
        expect(unbindRmDevice(&session) == NV_OK && session.stop() == NV_OK,
               "unattested policy fixture cleanup");
    }
    Fake f; Session session;
    expect(session.start(backend(f)) == NV_OK && bindRmDevice(&session, state, dma) == NV_OK,
           "attested policy exact device binding");
    required = NV_FALSE;
    expect(queryRmDmaRemap(foreign, required) == NV_ERR_INVALID_STATE && required == NV_FALSE &&
           !f.policyQueries, "foreign nv_state cannot query another provider's policy");
    expectDmaPolicyFatal(foreign, "foreign scalar callback cannot fabricate a policy");
    expect(queryRmDmaRemap(state, required) == NV_OK && required == NV_TRUE && f.policyQueries == 1,
           "positive provider contract requires explicit mapping of physical PTEs");
    expect(s540Global_nv_requires_dma_remap(state) == NV_TRUE && f.policyQueries == 2,
           "original scalar ABI delegates to the bound provider each time");
    f.remapStatus = NV_ERR_BUSY_RETRY; required = NV_FALSE;
    expect(queryRmDmaRemap(state, required) == NV_ERR_BUSY_RETRY && required == NV_FALSE,
           "temporarily indeterminate policy preserves caller output");
    expectDmaPolicyFatal(state, "indeterminate scalar cannot return a default Boolean");
    f.remapStatus = NV_OK; f.remapPolicy = static_cast<DmaRemapPolicy>(42);
    expect(queryRmDmaRemap(state, required) == NV_ERR_NOT_SUPPORTED && required == NV_FALSE,
           "invalid provider policy cannot publish a Boolean");
    f.remapPolicy = DmaRemapPolicy::Unavailable;
    expect(queryRmDmaRemap(state, required) == NV_ERR_NOT_SUPPORTED && required == NV_FALSE,
           "provider policy revocation is rechecked after admission");
    f.remapPolicy = DmaRemapPolicy::MapPhysicalPagesWithoutBounce;
    f.ordinary = false;
    expect(queryRmDmaRemap(state, required) == NV_ERR_INVALID_STATE && required == NV_FALSE,
           "wrong execution context refuses before scalar policy query");
    f.ordinary = true; f.active = false;
    expect(queryRmDmaRemap(state, required) == NV_ERR_INVALID_STATE && required == NV_FALSE,
           "provider departure revokes policy admission");
    expectDmaPolicyFatal(state, "departed provider scalar callback cannot reuse cached policy");
    f.active = true;
    expect(unbindRmDevice(&session) == NV_OK && session.stop() == NV_OK,
           "attested policy binding cleanup");
    expect(queryRmDmaRemap(state, required) == NV_ERR_INVALID_STATE && required == NV_FALSE,
           "stale nv_state cannot retain DMA policy");
}
void stateTests() {
    Fake f;
    Session session;
    expect(session.start(backend(f)) == NV_OK, "owner start");
    expect(session.start(backend(f)) == NV_ERR_STATE_IN_USE, "duplicate owner refusal");
    NvU64 ptes[4]{1,2,3,4}; void *token = nullptr;
    expect(session.allocate(4, ptes, &token) == NV_OK, "persistent host allocation");
    expect(ptes[0] == 0x10000000 && token, "physical allocation ownership");
    expect(session.setDmaAddressSize(31) == NV_ERR_INVALID_ARGUMENT, "invalid address width");
    expect(session.setDmaAddressSize(64) == NV_OK, "verified address width request");
    expect(session.mapDma(token, ptes) == NV_OK, "device map");
    expect(ptes[0] == 0x20000000, "device address replaces CPU physical value");
    expect(session.setDmaAddressSize(32) == NV_ERR_IN_USE, "cannot shrink active mapping");
    expect(session.installInterrupt(InterruptContract{}) == NV_ERR_NOT_SUPPORTED, "missing actual ISR refused");
    expect(session.installInterrupt(contract(f)) == NV_OK, "fixture ISR contract installed");
    f.readyForInterrupt = false;
    expect(session.armInterrupt() == NV_ERR_INVALID_STATE && !f.armed, "private RM dispatch prerequisite blocks controller enable");
    f.readyForInterrupt = true;
    expect(session.armInterrupt() == NV_OK && f.armed, "fixture controller armed");
    expect(session.release(token) == NV_ERR_IN_USE, "IRQ lifetime blocks DMA release");
    expect(session.unmapDma(token, ptes) == NV_ERR_IN_USE, "IRQ lifetime blocks unmap");
    f.fault = Fault::StopIrq;
    expect(session.stop() == NV_ERR_BUSY_RETRY && session.active() && f.resources == 1, "IRQ quarantine preserves owner and pages");
    f.fault = Fault::None;
    expect(session.stopInterrupt() == NV_OK, "successful hardware mask and ISR drain");
    expect(session.unmapDma(token, ptes) == NV_OK && ptes[0] == 0x10000000, "DMA unmap restores physical address");
    f.fault = Fault::Release;
    expect(session.release(token) == NV_ERR_OPERATING_SYSTEM && f.resources == 1, "descriptor completion quarantine");
    f.fault = Fault::None;
    expect(session.release(token) == NV_OK, "owned release recovery");
    NvU64 untouched = 123;
    expect(session.address(token, 0, untouched) == NV_ERR_OBJECT_NOT_FOUND && untouched == 123, "stale token refused");
    expect(session.stop() == NV_OK && !f.active && !f.resources && !f.registerReads, "owner cleanup without extra MMIO reads");
}
void abiTests() {
    Fake f; Session session;
    expect(session.start(backend(f)) == NV_OK, "ABI session start");
    auto *state = reinterpret_cast<nv_state_t *>(NvUPtr(0x100));
    auto *dma = reinterpret_cast<nv_dma_device_t *>(NvUPtr(0x200));
    expect(bindRmDevice(&session, state, dma) == NV_OK, "exact opaque device binding");
    expect(session.stop() == NV_ERR_IN_USE && session.active(), "RM binding pins session lifetime");
    NvU16 vendor = 0xbeef, deviceId = 0xbeef;
    void *pci = s540Global_os_pci_init_handle(0,1,0,0,&vendor,&deviceId);
    expect(pci && pci == boundPciHandle() && vendor == 0x10de && deviceId == 0x1f91, "bound provider PCI identity");
    expect(!s540Global_os_pci_init_handle(1,1,0,0,&vendor,&deviceId) && !vendor && !deviceId, "foreign PCI segment cannot alias target");
    NvU32 config = 0;
    expect(s540Global_os_pci_read_dword(pci,0x100,&config) == NV_OK && config == 0x12345678, "extended configuration ABI");
    expect(s540Global_os_pci_read_dword(pci,4095,&config) == NV_ERR_INVALID_ARGUMENT && config == 0x12345678, "configuration bounds preserve output");
    expect(s540Global_os_pci_read_dword(reinterpret_cast<void *>(NvUPtr(1)),0,&config) == NV_ERR_INVALID_STATE, "forged PCI handle refused");
    expect(s540Global_os_pci_write_word(pci,4,6) == NV_OK && f.command == 6, "original bus-master command route");
    expect(s540Global_os_pci_write_dword(pci,0x10,0) == NV_ERR_NOT_SUPPORTED, "BAR relocation denied");
    expect(s540Global_os_pci_write_word(pci,4,4) == NV_ERR_NOT_SUPPORTED, "memory decode cannot be disabled through command route");
    expect(s540Global_nv_is_gpu_accessible(state) == NV_FALSE && s540Global_nv_match_gpu_os_info(state,&f) == NV_FALSE, "absent OS user client cannot grant GPU authorization");
    NvU64 ptes[4] = {1,2,3,4}; void *allocation = reinterpret_cast<void *>(NvUPtr(99));
    expect(s540Global_nv_alloc_pages(state,4,4096,NV_FALSE,0,NV_TRUE,NV_FALSE,-1,ptes,&allocation) == NV_OK, "exact allocation ABI");
    void *original = allocation;
    expect(s540Global_nv_dma_map_alloc(dma,4,ptes,NV_FALSE,NV_TRUE,&allocation) == NV_ERR_NOT_SUPPORTED && allocation == original && ptes[0] == 0x10000000, "read-only map refusal preserves INOUT ownership");
    expect(s540Global_nv_dma_map_alloc(dma,3,ptes,NV_FALSE,NV_FALSE,&allocation) == NV_ERR_INVALID_ARGUMENT && allocation == original, "page count mismatch preserves ownership");
    expect(s540Global_nv_dma_map_alloc(dma,4,ptes,NV_FALSE,NV_FALSE,&allocation) == NV_OK && allocation != original, "successful mapping publishes separate handle");
    void *mapped = allocation;
    expect(s540Global_nv_dma_unmap_alloc(dma,3,ptes,&allocation) == NV_ERR_INVALID_ARGUMENT && allocation == mapped, "unmap mismatch preserves mapped handle");
    expect(s540Global_nv_dma_unmap_alloc(dma,4,ptes,&allocation) == NV_OK && allocation == original && ptes[0] == 0x10000000, "unmap restores original allocation token");
    void *mapPrivate = nullptr;
    void *address = s540Global_nv_alloc_kernel_mapping(state,allocation,1,8,32,&mapPrivate);
    expect(address && mapPrivate, "bounded CPU mapping");
    expect(s540Global_nv_get_kern_phys_address(reinterpret_cast<NvUPtr>(address)) == 0x10001008, "owned kernel virtual to physical");
    expect(s540Global_nv_get_kern_phys_address(1) == 0, "foreign virtual address refused");
    expect(s540Global_nv_alloc_kernel_mapping(state,allocation,3,4090,32,&mapPrivate) == nullptr, "CPU mapping crossing end refused");
    expect(s540Global_nv_free_pages(state,4,NV_FALSE,0,allocation) == NV_OK && f.resources == 1, "free deferred until final CPU map release");
    expect(unbindRmDevice(&session) == NV_ERR_IN_USE, "live mapping blocks unbind");
    s540Global_nv_free_kernel_mapping(state,allocation,address,mapPrivate);
    expect(abiStatistics().allocations == 0 && abiStatistics().mappings == 0 && f.resources == 0, "deferred free releases actual backing");
    for (NvU32 cache : {1U,2U}) {
        NvU64 contiguousPages[2] = {0xaaa,0xbbb}; void *contiguous = nullptr;
        expect(s540Global_nv_alloc_pages(state,2,4096,NV_TRUE,cache,NV_TRUE,NV_FALSE,-1,contiguousPages,&contiguous) == NV_OK && contiguousPages[1] == 0xbbb, "uncached/writecombined contiguous allocation output width");
        void *originalContiguous = contiguous;
        expect(s540Global_nv_dma_map_alloc(dma,2,contiguousPages,NV_TRUE,NV_FALSE,&contiguous) == NV_OK && contiguousPages[1] == 0xbbb, "contiguous device mapping publishes one base");
        expect(s540Global_nv_dma_unmap_alloc(dma,2,contiguousPages,&contiguous) == NV_OK && contiguous == originalContiguous && contiguousPages[1] == 0xbbb, "contiguous unmap publishes one physical base");
        expect(s540Global_nv_free_pages(state,2,NV_TRUE,cache,contiguous) == NV_OK, "exact cache type allocation release");
    }
    expect(unbindRmDevice(&session) == NV_OK, "device ABI unbind");
    expect(session.stop() == NV_OK, "ABI owner stop");
}
void failures() {
    const Fault faults[] = {Fault::Allocate, Fault::Physical, Fault::Map, Fault::DeviceAddress};
    for (Fault fault : faults) {
        Fake f; Session session; expect(session.start(backend(f)) == NV_OK, "fault owner start");
        NvU64 ptes[4]{11,12,13,14}; void *token = reinterpret_cast<void *>(NvUPtr(0x55));
        f.fault = fault;
        if (fault == Fault::Allocate || fault == Fault::Physical) {
            expect(session.allocate(4,ptes,&token) != NV_OK, "host fault observed");
            expect(ptes[0] == 11 && token == reinterpret_cast<void *>(NvUPtr(0x55)), "host failure outputs untouched");
        } else {
            f.fault = Fault::None; expect(session.allocate(4,ptes,&token) == NV_OK, "map fault host allocation");
            f.fault = fault;
            expect(session.mapDma(token,ptes) != NV_OK && ptes[0] == 0x10000000, "map failure outputs untouched");
        }
        f.fault = Fault::None; expect(session.stop() == NV_OK && !f.resources, "fault reverse cleanup");
    }
    Fake f; Session session; expect(session.start(backend(f)) == NV_OK, "unmap fault start");
    NvU64 ptes[2]{}; void *token = nullptr;
    expect(session.allocate(2,ptes,&token) == NV_OK && session.mapDma(token,ptes) == NV_OK, "unmap fault live mapping");
    f.fault = Fault::Unmap;
    expect(session.unmapDma(token,ptes) != NV_OK && ptes[0] == 0x20000000, "failed unmap outputs preserved");
    expect(session.stop() != NV_OK && session.active() && f.resources == 1, "unmap quarantine preserves backing");
    f.fault = Fault::None; expect(session.stop() == NV_OK && !f.resources, "quiescent retry cleanup");
}
void quarantineTests() {
    {
        Fake f; f.badSnapshot = true; f.fault = Fault::Stop; Session session;
        expect(session.start(backend(f)) == NV_ERR_IN_USE && session.active(), "invalid startup cleanup preserves retained owner");
        f.fault = Fault::None; expect(session.stop() == NV_OK, "startup quarantine recovery");
    }
    {
        Fake f; Session session; expect(session.start(backend(f)) == NV_OK, "physical quarantine start");
        f.fault = Fault::Physical; f.failRelease = true;
        NvU64 ptes[2]{11,12}; void *token = reinterpret_cast<void *>(NvUPtr(0x55));
        expect(session.allocate(2,ptes,&token) != NV_OK && f.resources == 1, "invalid physical table cleanup failure retains internal ownership");
        expect(ptes[0] == 11 && token == reinterpret_cast<void *>(NvUPtr(0x55)), "quarantine preserves unpublished caller outputs");
        expect(session.stop() != NV_OK && session.active() && f.resources == 1, "unpublished quarantine pins provider");
        f.fault = Fault::None; f.failRelease = false;
        expect(session.stop() == NV_OK && !f.resources, "unpublished quarantine recovery");
    }
    {
        Fake f; Session session; expect(session.start(backend(f)) == NV_OK, "invalid DMA quarantine start");
        NvU64 ptes[2]{}; void *token = nullptr;
        expect(session.allocate(2,ptes,&token) == NV_OK, "invalid DMA quarantine allocation");
        f.fault = Fault::DeviceAddress; f.failUnmap = true;
        expect(session.mapDma(token,ptes) != NV_OK && ptes[0] == 0x10000000, "invalid DMA table refusal leaves caller outputs intact");
        expect(session.stop() != NV_OK && session.active() && f.resources == 1, "invalid DMA cleanup failure retains mapped lifetime");
        f.fault = Fault::None; f.failUnmap = false;
        expect(session.stop() == NV_OK && !f.resources, "invalid DMA quarantine recovery");
    }
}

void pageCountTests() {
    auto *state = reinterpret_cast<nv_state_t *>(NvUPtr(0x710));
    auto *dma = reinterpret_cast<nv_dma_device_t *>(NvUPtr(0x810));
    Fake f; Session session;
    expect(session.start(backend(f)) == NV_OK && bindRmDevice(&session,state,dma) == NV_OK,
           "physical count exact owner");
    NvU64 pages[4]{}; void *allocation = nullptr;
    expect(s540Global_nv_alloc_pages(state,4,4096,NV_FALSE,0,NV_TRUE,NV_FALSE,-1,pages,&allocation) == NV_OK,
           "physical count backing");
    NvU32 count = 91;
    expect(s540Global_nv_get_num_phys_pages(allocation,nullptr) == NV_ERR_INVALID_ARGUMENT &&
           s540Global_nv_get_num_phys_pages(reinterpret_cast<void *>(NvUPtr(123)),&count) == NV_ERR_OBJECT_NOT_FOUND && count == 91,
           "invalid count output and foreign allocation are refused");
    expect(s540Global_nv_get_num_phys_pages(allocation,&count) == NV_OK && count == 4,
           "count comes from owned physical-page metadata");
    void *original = allocation;
    expect(s540Global_nv_dma_map_alloc(dma,4,pages,NV_FALSE,NV_FALSE,&allocation) == NV_OK &&
           s540Global_nv_get_num_phys_pages(original,&count) == NV_OK && count == 4,
           "DMA map does not replace the physical-allocation owner");
    count = 92;
    expect(s540Global_nv_get_num_phys_pages(allocation,&count) == NV_ERR_OBJECT_NOT_FOUND && count == 92,
           "DMA mapping identity cannot masquerade as a physical allocation");
    expect(s540Global_nv_dma_unmap_alloc(dma,4,pages,&allocation) == NV_OK,
           "count fixture mapping cleanup");
    void *mapping = nullptr;
    void *host = s540Global_nv_alloc_kernel_mapping(state,allocation,0,0,4096,&mapping);
    expect(host && s540Global_nv_free_pages(state,4,NV_FALSE,0,allocation) == NV_OK &&
           s540Global_nv_get_num_phys_pages(allocation,&count) == NV_ERR_OBJECT_NOT_FOUND && count == 92,
           "deferred CPU-alias free revokes public page-count access");
    f.failRelease = true;
    s540Global_nv_free_kernel_mapping(state,allocation,host,mapping);
    expect(abiStatistics().retiredAllocations == 1 && !abiStatistics().mappings && f.resources == 1 &&
           drainRmRetirements(&session) == NV_ERR_OPERATING_SYSTEM,
           "void final CPU-unmap preserves completion failure as a retirement owner");
    f.failRelease = false;
    expect(drainRmRetirements(&session) == NV_OK && !f.resources &&
           s540Global_nv_get_num_phys_pages(allocation,&count) == NV_ERR_OBJECT_NOT_FOUND && count == 92,
           "retired and stale physical allocation cannot publish a count");
    expect(unbindRmDevice(&session) == NV_OK &&
           s540Global_nv_get_num_phys_pages(allocation,&count) == NV_ERR_INVALID_STATE && count == 92 &&
           session.stop() == NV_OK, "unbound page count fails without output mutation");
}

void retirementTests() {
    auto *state = reinterpret_cast<nv_state_t *>(NvUPtr(0x510));
    auto *dma = reinterpret_cast<nv_dma_device_t *>(NvUPtr(0x610));
    {
        Fake f; Session session;
        expect(session.start(backend(f)) == NV_OK && bindRmDevice(&session,state,dma) == NV_OK &&
               session.installInterrupt(contract(f)) == NV_OK && session.armInterrupt() == NV_OK,
               "active RM retirement owner");
        NvU64 pages[2]{}; void *allocation = nullptr;
        expect(s540Global_nv_alloc_pages(state,2,4096,NV_FALSE,0,NV_TRUE,NV_FALSE,-1,pages,&allocation) == NV_OK,
               "init temporary backing allocated");
        void *original = allocation; const NvU64 physical = pages[0];
        void *cpuToken = nullptr;
        void *host = s540Global_nv_alloc_kernel_mapping(state,original,0,0,4096,&cpuToken);
        expect(host && cpuToken, "temporary CPU ownership tracked");
        expect(s540Global_nv_dma_map_alloc(dma,2,pages,NV_FALSE,NV_FALSE,&allocation) == NV_OK,
               "temporary live DMA mapping");
        void *firstMapping = allocation; const NvU64 deviceAddress = pages[0];
        expect(s540Global_nv_free_pages(state,2,NV_FALSE,0,original) == NV_ERR_IN_USE,
               "logical DMA owner must retire before backing");
        expect(s540Global_nv_dma_unmap_alloc(dma,1,pages,&allocation) == NV_ERR_INVALID_ARGUMENT &&
               allocation == firstMapping && pages[0] == deviceAddress,
               "wrong mapping geometry cannot transfer ownership");
        f.fault = Fault::Physical;
        expect(s540Global_nv_dma_unmap_alloc(dma,2,pages,&allocation) == NV_ERR_INVALID_ADDRESS &&
               allocation == firstMapping && pages[0] == deviceAddress &&
               !session.retirementStatistics().dmaMappings,
               "invalid physical table cannot acknowledge logical unmap");
        f.fault = Fault::None;
        expect(s540Global_nv_dma_unmap_alloc(dma,2,pages,&allocation) == NV_OK &&
               allocation == original && pages[0] == physical && !f.unmapCalls && !f.releaseCalls &&
               session.retirementStatistics().dmaMappings == 1,
               "active IRQ logical unmap retains exact IOVA and backing");
        NvU32 count = 91;
        expect(s540Global_nv_get_num_phys_pages(original,&count) == NV_OK && count == 2,
               "retired DMA lease does not revoke its still-owned physical allocation");
        void *stale = firstMapping;
        expect(s540Global_nv_dma_unmap_alloc(dma,2,pages,&stale) == NV_ERR_OBJECT_NOT_FOUND,
               "retired DMA token cannot unmap twice");
        f.retainedMappingValid = false;
        expect(s540Global_nv_dma_map_alloc(dma,2,pages,NV_FALSE,NV_FALSE,&allocation) == NV_ERR_INVALID_STATE &&
               allocation == original && pages[0] == physical && f.mapCalls == 1 && !f.unmapCalls,
               "revoked retained mapping preserves previous ownership");
        f.retainedMappingValid = true; f.fault = Fault::DeviceAddress;
        expect(s540Global_nv_dma_map_alloc(dma,2,pages,NV_FALSE,NV_FALSE,&allocation) == NV_ERR_INVALID_ADDRESS &&
               allocation == original && pages[0] == physical && !f.unmapCalls,
               "invalid retained address cannot trigger early backend teardown");
        f.fault = Fault::None;
        expect(s540Global_nv_dma_map_alloc(dma,2,pages,NV_FALSE,NV_FALSE,&allocation) == NV_OK &&
               allocation != firstMapping && pages[0] == deviceAddress && f.mapCalls == 1 &&
               f.retainedValidations == 3 && !session.retirementStatistics().dmaMappings,
               "same backing remap revalidates and reuses the still-owned mapping");
        expect(s540Global_nv_dma_unmap_alloc(dma,2,pages,&allocation) == NV_OK &&
               s540Global_nv_free_pages(state,2,NV_FALSE,0,allocation) == NV_OK &&
               !abiStatistics().retiredAllocations && abiStatistics().retiredDmaMappings == 1,
               "free with live CPU alias waits for that specific alias");
        void *extraCpu = nullptr;
        expect(!s540Global_nv_alloc_kernel_mapping(state,allocation,0,0,4096,&extraCpu),
               "logical free blocks new CPU aliases");
        NvU64 nextPages[1]{}; void *next = nullptr;
        expect(s540Global_nv_alloc_pages(state,1,4096,NV_FALSE,0,NV_TRUE,NV_FALSE,-1,nextPages,&next) == NV_OK &&
               nextPages[0] != physical && f.resources == 2,
               "retired backing is not recycled into another allocation");
        expect(s540Global_nv_free_pages(state,1,NV_FALSE,0,next) == NV_OK &&
               s540Global_nv_free_pages(state,1,NV_FALSE,0,next) == NV_ERR_OBJECT_NOT_FOUND,
               "unmapped temporary backing retirement invalidates only its token");
        s540Global_nv_free_kernel_mapping(state,original,host,cpuToken);
        expect(abiStatistics().retiredAllocations == 2 && !abiStatistics().mappings &&
               session.retirementStatistics().pages == 3 && !f.releaseCalls &&
               s540Global_nv_get_kern_phys_address(reinterpret_cast<NvUPtr>(host)) == 0,
               "last CPU alias transfers the original backing into retirement");
        count = 92;
        expect(s540Global_nv_get_num_phys_pages(original,&count) == NV_ERR_OBJECT_NOT_FOUND && count == 92,
               "active IRQ retired allocation cannot expose a physical-page count");
        expect(s540Global_nv_free_pages(state,2,NV_FALSE,0,original) == NV_ERR_OBJECT_NOT_FOUND &&
               unbindRmDevice(&session) == NV_ERR_IN_USE && drainRmRetirements(&session) == NV_ERR_IN_USE,
               "retired caller tokens are stale and real IRQ drain remains required");
        f.failMask = true;
        expect(session.stopInterrupt() == NV_ERR_OPERATING_SYSTEM &&
               drainRmRetirements(&session) == NV_ERR_IN_USE && f.resources == 2 && !f.unmapCalls,
               "failed hardware mask retains every retired resource");
        f.failMask = false; f.failStopAfterMask = true;
        expect(session.stopInterrupt() == NV_ERR_BUSY_RETRY &&
               drainRmRetirements(&session) == NV_ERR_IN_USE && f.resources == 2,
               "partial controller drain cannot reclaim retirement");
        f.failStopAfterMask = false;
        expect(session.stopInterrupt() == NV_OK && f.maskCalls == 2 && f.resources == 2,
               "source and controller drain preserves retirement until explicit completion");
        f.fault = Fault::Unmap;
        expect(drainRmRetirements(&session) == NV_ERR_OPERATING_SYSTEM &&
               abiStatistics().retiredAllocations == 2 && f.resources == 2 &&
               unbindRmDevice(&session) == NV_ERR_IN_USE,
               "backend unmap failure pins the exact retirement binding");
        f.fault = Fault::None; f.failRelease = true;
        expect(drainRmRetirements(&session) == NV_ERR_OPERATING_SYSTEM &&
               abiStatistics().retiredAllocations == 2 && f.resources == 2,
               "descriptor completion failure preserves already-unmapped backing");
        const NvU32 completedUnmaps = f.unmapCalls;
        f.failRelease = false;
        expect(drainRmRetirements(&session) == NV_OK && f.unmapCalls == completedUnmaps &&
               !f.resources && !abiStatistics().allocations &&
               !session.retirementStatistics().allocations && !session.retirementStatistics().dmaMappings,
               "retirement retry does not duplicate a successful backend unmap");
        expect(drainRmRetirements(&session) == NV_OK && unbindRmDevice(&session) == NV_OK && session.stop() == NV_OK,
               "completed retirement permits idempotent drain and final detach");
    }
    for (bool partialEnable : {false,true}) {
        Fake f; Session session;
        expect(session.start(backend(f)) == NV_OK && bindRmDevice(&session,state,dma) == NV_OK,
               "disable-adapter retirement owner");
        void *allocation = nullptr;
        expect(s540Global_nv_alloc_pages(state,2,4096,NV_FALSE,0,NV_TRUE,NV_FALSE,-1,f.maskPages,&allocation) == NV_OK &&
               s540Global_nv_dma_map_alloc(dma,2,f.maskPages,NV_FALSE,NV_FALSE,&allocation) == NV_OK &&
               session.installInterrupt(contract(f)) == NV_OK,
               "disable-adapter temporary DMA ownership");
        f.fault = partialEnable ? Fault::Arm : Fault::None;
        expect(session.armInterrupt() == (partialEnable ? NV_ERR_OPERATING_SYSTEM : NV_OK),
               "retirement covers successful and partial controller enable");
        f.fault = Fault::None; f.retireOnMask = true;
        f.maskState = state; f.maskDma = dma; f.maskAllocation = allocation;
        expect(session.stopInterrupt() == NV_OK && !f.retireOnMask && f.resources == 1 &&
               !f.unmapCalls && !f.releaseCalls && abiStatistics().retiredAllocations == 1,
               "original-disable-order callbacks retire while mask operation still owns the IRQ");
        expect(drainRmRetirements(&session) == NV_OK && !f.resources &&
               unbindRmDevice(&session) == NV_OK && session.stop() == NV_OK,
               "disable-order retirement completes after actual drain");
    }
    {
        Fake f; Session session;
        NvU64 pages[2]{}; void *allocation = nullptr;
        expect(session.start(backend(f)) == NV_OK && bindRmDevice(&session,state,dma) == NV_OK &&
               s540Global_nv_alloc_pages(state,2,4096,NV_FALSE,0,NV_TRUE,NV_FALSE,-1,pages,&allocation) == NV_OK &&
               s540Global_nv_dma_map_alloc(dma,2,pages,NV_FALSE,NV_FALSE,&allocation) == NV_OK &&
               session.installInterrupt(contract(f)) == NV_OK && session.armInterrupt() == NV_OK,
               "mapping-only retirement owner");
        expect(s540Global_nv_dma_unmap_alloc(dma,2,pages,&allocation) == NV_OK &&
               session.stopInterrupt() == NV_OK, "mapping-only lease reaches actual drain");
        f.failRelease = true;
        expect(s540Global_nv_free_pages(state,2,NV_FALSE,0,allocation) == NV_ERR_OPERATING_SYSTEM &&
               f.unmapCalls == 1 && f.resources == 1,
               "post-drain free failure can follow a successful retained-map completion");
        expect(drainRmRetirements(&session) == NV_OK && f.unmapCalls == 1 &&
               !session.retirementStatistics().dmaMappings && f.resources == 1,
               "mapping retirement progress does not repeat an already completed unmap");
        f.failRelease = false;
        expect(s540Global_nv_free_pages(state,2,NV_FALSE,0,allocation) == NV_OK &&
               !f.resources && unbindRmDevice(&session) == NV_OK && session.stop() == NV_OK,
               "failed synchronous free preserves caller ownership for its own retry");
    }
    {
        Fake f; Session session;
        expect(session.start(backend(f)) == NV_OK && bindRmDevice(&session,state,dma) == NV_OK &&
               session.installInterrupt(contract(f)) == NV_OK && session.armInterrupt() == NV_OK,
               "bounded retirement capacity owner");
        for (NvU32 i = 0; i < kMaximumAllocations; ++i) {
            NvU64 page = 0; void *allocation = nullptr;
            expect(s540Global_nv_alloc_pages(state,1,4096,NV_FALSE,0,NV_TRUE,NV_FALSE,-1,&page,&allocation) == NV_OK &&
                   s540Global_nv_free_pages(state,1,NV_FALSE,0,allocation) == NV_OK,
                   "retirement keeps its bounded ownership slot");
        }
        NvU64 unchanged = 91; void *unchangedToken = reinterpret_cast<void *>(NvUPtr(92));
        expect(s540Global_nv_alloc_pages(state,1,4096,NV_FALSE,0,NV_TRUE,NV_FALSE,-1,&unchanged,&unchangedToken) == NV_ERR_INSUFFICIENT_RESOURCES &&
               unchanged == 91 && unchangedToken == reinterpret_cast<void *>(NvUPtr(92)) &&
               f.resources == kMaximumAllocations && !f.releaseCalls,
               "bounded exhaustion cannot recycle retired pages or publish success");
        expect(session.stopInterrupt() == NV_OK && drainRmRetirements(&session) == NV_OK && !f.resources,
               "bounded retirement capacity reclaimed only after drain");
        expect(unbindRmDevice(&session) == NV_OK && session.stop() == NV_OK,
               "bounded retirement owner cleanup");
    }
}

void irqLifecycleTests() {
    {
        Fake f; Session session;
        NvU64 pages[2]{}; void *allocation = nullptr;
        expect(session.start(backend(f)) == NV_OK, "disabled-controller unwind owner");
        expect(session.allocate(2,pages,&allocation) == NV_OK &&
               session.mapDma(allocation,pages) == NV_OK, "disabled-controller unwind allocation");
        f.failMask = true; // Original adapter state does not exist yet.
        expect(session.installInterrupt(contract(f)) == NV_OK && !session.interruptArmed(),
               "controller registration has no enable side effects");
        f.readyForInterrupt = false;
        expect(session.armInterrupt() == NV_ERR_INVALID_STATE,
               "rejected dispatch prerequisite never attempts enable");
        expect(session.unmapDma(allocation,pages) == NV_OK && pages[0] == 0x10000000,
               "original-init unwind can unmap with a never-enabled controller");
        expect(session.release(allocation) == NV_OK && !f.resources,
               "original-init unwind can free before controller deregistration");
        expect(session.stopInterrupt() == NV_OK && !f.maskCalls && !f.irq,
               "never-enabled controller teardown does not call original hardware mask");
        expect(session.stop() == NV_OK, "disabled-controller owner cleanup");
    }
    {
        Fake f; Session session;
        NvU64 pages[2]{}; void *allocation = nullptr;
        expect(session.start(backend(f)) == NV_OK &&
               session.allocate(2,pages,&allocation) == NV_OK &&
               session.mapDma(allocation,pages) == NV_OK, "partial-enable owner and allocation");
        expect(session.installInterrupt(contract(f)) == NV_OK, "partial-enable registration");
        f.fault = Fault::Arm;
        expect(session.armInterrupt() == NV_ERR_OPERATING_SYSTEM && f.armed &&
               !session.interruptArmed(), "controller enable may take effect before reporting failure");
        expect(session.armInterrupt() == NV_ERR_STATE_IN_USE,
               "uncertain enable cannot be retried before a drain");
        expect(session.unmapDma(allocation,pages) == NV_ERR_IN_USE && pages[0] == 0x20000000 &&
               session.release(allocation) == NV_ERR_IN_USE && f.resources == 1,
               "failed enable retains DMA addresses and backing");
        f.fault = Fault::None; f.failMask = true;
        expect(session.stopInterrupt() == NV_ERR_OPERATING_SYSTEM && session.interruptInstalled(),
               "failed original mask retains the registered controller");
        expect(session.release(allocation) == NV_ERR_IN_USE,
               "mask refusal retains addressable memory");
        f.failMask = false; f.failStopAfterMask = true;
        expect(session.stopInterrupt() == NV_ERR_BUSY_RETRY && f.maskCalls == 2,
               "controller drain failure follows successful original masking");
        expect(session.release(allocation) == NV_ERR_IN_USE,
               "incomplete controller drain retains addressable memory");
        f.failStopAfterMask = false;
        expect(session.stopInterrupt() == NV_OK && f.maskCalls == 2 && !f.armed,
               "drain retry does not disable original adapter twice");
        expect(session.unmapDma(allocation,pages) == NV_OK &&
               session.release(allocation) == NV_OK && !f.resources,
               "only complete drain permits DMA reclamation");
        expect(session.stop() == NV_OK, "partial-enable owner cleanup");
    }
}

}
int main() {
    expect(selectMapperPolicy(false,false,true) == Mapper::Direct, "framework-attested direct admission");
    expect(selectMapperPolicy(false,false,false) == Mapper::Unavailable, "unknown/required/live unbound system mapper refused");
    expect(selectMapperPolicy(true,false,true) == Mapper::Unavailable, "unresolved provider mapper cannot fall back direct");
    expect(selectMapperPolicy(true,true,false) == Mapper::Device, "published device mapper admission");
    for (NvUPtr systemMapper : {NvUPtr(1), NvUPtr(2), NvUPtr(0x1000)})
        expect(selectMapperPolicy(false,false,systemMapper == 0) == Mapper::Unavailable, "unknown required or live unbound system mapper cannot become direct");
    expect(dmaPageMatches(0x1000,0x2000,0x1000,32), "mapped page resolves original backing");
    expect(dmaPageMatches(0x1000,0x1000,0x1000,64), "direct page aliases original backing");
    expect(!dmaPageMatches(0x1000,0x2000,0x3000,64), "bounce buffer refused for shared GSP bytes");
    expect(!dmaPageMatches(0x1000,0x100000000ULL,0x1000,32), "device address width enforced");
    expect(!dmaPageMatches(0x1000,~NvU64(0),0x1000,64), "device page wrap refused");
    expect(!dmaPageMatches(0x1000,0x2001,0x1000,64), "device page alignment enforced");
    expect(!dmaPageMatches(0x1000,0x2000,0x1000,0), "unknown requested address width refused");
    expect(pciWriteKind(4,2,2,6) == PciWriteKind::CommandBusMaster, "reviewed bus master enable");
    expect(pciWriteKind(4,2,6,2) == PciWriteKind::CommandBusMaster, "reviewed bus master disable");
    expect(pciWriteKind(4,2,2,7) == PciWriteKind::Refused, "unreviewed IO decode enable refused");
    expect(pciWriteKind(0x30,4,0xffff0000,0) == PciWriteKind::RomDisable, "exact original ROM disable request");
    expect(pciWriteKind(0x30,4,0,0x100001) == PciWriteKind::Refused, "ROM relocation or enable refused");
    expect(pciWriteKind(0xc,4,0,0xf800) == PciWriteKind::LatencySetup, "exact original latency setup");
    expect(pciWriteKind(0xc,4,0,0xf900) == PciWriteKind::Refused, "unreviewed legacy command refused");
    expect(pciWriteKind(0x10,4,0,0) == PciWriteKind::Refused, "BAR mutation refused");
    expect(pciWriteKind(0x80,4,0,0) == PciWriteKind::Refused, "capability mutation lacks reviewed TU117 caller");
    directRouteTests(); dmaRemapTests(); stateTests(); abiTests(); failures(); quarantineTests(); irqLifecycleTests(); retirementTests(); pageCountTests();
    for (NvU32 i = 0; i < 128; ++i) {
        Fake f;
        Result result = check(backend(f));
        expect(result.passed() && result.checks == 21 && result.dmaAddresses && !result.deviceTransferVerified && !f.resources && !f.active && !f.registerReads, "complete lifecycle regression");
    }
    Fake unavailable; unavailable.mapper = Mapper::Unavailable;
    Result result = check(backend(unavailable));
    expect(result.passed() && result.checks == 19 && result.dmaUnavailable && !result.dmaAddresses, "unavailable mapper is explicit refusal evidence");
    std::printf("{\"format\":1,\"component\":\"nvidia-device-transport\",\"status\":\"passed\",\"failures\":0,\"execution\":\"native-user-space\",\"kernel_execution\":\"not_tested\",\"gpu_access\":false,\"checks\":%u,\"lifecycle_cycles\":128,\"production_checks\":21,\"unavailable_mapper_checks\":19,\"device_dma_verified\":false,\"hardware_interrupt_delivery\":false,\"gpu_initialized\":false}\n",assertions);
}
