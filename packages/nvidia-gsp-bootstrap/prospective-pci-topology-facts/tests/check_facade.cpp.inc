/* SPDX-License-Identifier: MIT; actual DeviceServices facade bodies with
 * typed Session endpoints delegating non-GPU operations to the actual engine.
 * The kernel Session/backend and physical PCI resources are not executed.
 */
#include <cstdio>
#include <cstring>
#include "../../nvidia-device-transport/src/nv_device_services.h"
#include "actual-engine.cpp"
using namespace S540NvidiaPciTopology;
struct nv_state_t { unsigned marker; };
namespace fixture {
unsigned checks, failures, cases, reads, gpuReads, gpuWrites, accessibleCalls;
unsigned refusalCalls, aggregateCalls, order;
NvU32 refusalDomain, refusalSymbol, aggregateService;
NV_STATUS refusalStatus;
NV_STATUS authorityStatus=NV_OK, changedAuthorityStatus=NV_OK;
unsigned authorityCalls, authorityFlipAt, generationFlipAt;
bool ordinary = true, active = true, accessible = true;
NvU32 failOffset = ~0U;
int owner;
struct Node { NvU32 config[1024]; } bridge{}, host{};
void expect(bool v, int line) { ++checks; if (!v) { ++failures; std::fprintf(stderr,"PCI facade control line %d\n",line); } }
NV_STATUS read(void *, const Candidate &candidate, NvU32 offset, NvU32 width, NvU32 &value) {
    ++reads;
    if (offset == failOffset) { value = ~0U; return NV_ERR_TIMEOUT; }
    auto *node = static_cast<Node *>(candidate.resource);
    const NvU32 word = node->config[offset / 4U];
    value = word >> ((offset & 3U) * 8U);
    if (width == 1U) value &= 0xffU;
    if (width == 2U) value &= 0xffffU;
    return NV_OK;
}
}
#define EXPECT(v) fixture::expect(bool(v), __LINE__)
struct Snapshot { NvU32 segment; NvU8 bus,device,function; bool segmentKnown; };
class Session {
public:
    State topology{};
    bool active() const { return fixture::active; }
    Snapshot snapshot() const { return {0U,2U,0U,0U,true}; }
    bool accessible() { ++fixture::accessibleCalls; return fixture::accessible; }
    NV_STATUS readConfig(NvU32, NvU32, NvU32 &value) {
        ++fixture::gpuReads; value=0x55U; return NV_OK;
    }
    NV_STATUS writeConfig(NvU32, NvU32, NvU32) { ++fixture::gpuWrites; return NV_OK; }
    void *topologyHandle(NvU32 segment,NvU8 bus,NvU8 device,NvU8 function,NvU16 *vendor,NvU16 *deviceId) {
        return active() ? find(topology,this,segment,bus,device,function,vendor,deviceId) : nullptr;
    }
    NV_STATUS readTopology(void *handle,NvU32 offset,NvU32 width,NvU32 &value) {
        return active() ? S540NvidiaPciTopology::read(topology,this,handle,offset,width,value) : NV_STATUS(NV_ERR_INVALID_STATE);
    }
    NV_STATUS validateTopology(const S540PciTopologyGspFacts &facts) {
        return validate(topology,this,facts);
    }
    bool topologyReady() const { return active() && ready(topology,this); }
};
static Session session;
static nv_state_t nv{},foreign{};
static struct { Session *session; nv_state_t *state; void *pciHandle; } binding{};
static bool ordinary() { return fixture::ordinary; }
extern "C" NV_STATUS s540FirstTxnOptionalNvlinkActive(const void *state,NvU64 *generation) {
    EXPECT(state==&nv);++fixture::authorityCalls;*generation=0;
    NV_STATUS status=fixture::authorityCalls==fixture::authorityFlipAt ? fixture::changedAuthorityStatus : fixture::authorityStatus;
    if(status!=NV_OK)return status;
    *generation=fixture::authorityCalls==fixture::generationFlipAt ? 20U : 19U;
    return NV_OK;
}
extern "C" void s540FirstTxnObserveServiceRefusal(NvU32 domain,NvU32 symbol,NV_STATUS status) {
    EXPECT(fixture::order==0); fixture::order=1; ++fixture::refusalCalls;
    fixture::refusalDomain=domain;fixture::refusalSymbol=symbol;fixture::refusalStatus=status;
}
extern "C" void s540GlobalRmRecordUnavailable(NvU32 service) {
    EXPECT(fixture::order==1);fixture::order=2;++fixture::aggregateCalls;fixture::aggregateService=service;
}
#include "actual-facade.inc"
static void *handleFor(NvU8 bus,NvU8 device) {
    NvU16 vendor=0,deviceId=0;
    void *out=session.topologyHandle(0,bus,device,0,&vendor,&deviceId);
    EXPECT(out && vendor==0x8086U);return out;
}
int main(void) {
    ++fixture::cases;
    EXPECT(!s540PciTopologyUsesOsConfig(&nv));
    fixture::bridge.config[0]=0x9d188086U;fixture::bridge.config[2]=0x060400a1U;
    fixture::bridge.config[3]=0x00010000U;fixture::bridge.config[6]=0x00020200U;
    fixture::bridge.config[0x100/4]=0x11223344U;
    fixture::host.config[0]=0x3e348086U;fixture::host.config[2]=0x0600000cU;
    Candidate candidates[2]={{&fixture::bridge,0,0,29,0,false},{&fixture::host,0,0,0,0,true}};
    EXPECT(prepare(session.topology,&session,0,2,Reader{&fixture::owner,fixture::read},candidates,2)==NV_OK);
    binding={&session,&nv,reinterpret_cast<void *>(NvUPtr(1ULL<<63))};
    EXPECT(s540PciTopologyUsesOsConfig(&nv) && !s540PciTopologyUsesOsConfig(&foreign) && !s540PciTopologyUsesOsConfig(nullptr));
    ++fixture::cases;
    S540PciTopologyGspFacts facts{};facts.format=1;facts.bytes=sizeof(facts);
    facts.fhb={handleFor(0,0),0,0,0,0,0,0x8086,0x3e34};facts.chipset=facts.fhb;
    facts.upstream={handleFor(0,29),0,0,29,0,0,0x8086,0x9d18};
    EXPECT(s540PciTopologyValidateForGsp(&nv,&facts)==NV_OK);
    EXPECT(s540PciTopologyValidateForGsp(&foreign,&facts)==NV_ERR_INVALID_STATE);
    EXPECT(s540PciTopologyValidateForGsp(&nv,nullptr)==NV_ERR_INVALID_ARGUMENT);
    facts.bytes=0;EXPECT(s540PciTopologyValidateForGsp(&nv,&facts)==NV_ERR_INVALID_ARGUMENT);facts.bytes=sizeof(facts);
    facts.format=2;EXPECT(s540PciTopologyValidateForGsp(&nv,&facts)==NV_ERR_INVALID_ARGUMENT);facts.format=1;
    ++fixture::cases;
    NvU16 vendor=0xffff,deviceId=0xffff;
    unsigned before=fixture::reads,access=fixture::accessibleCalls;
    EXPECT(!s540Global_os_pci_init_handle(0,0,31,7,&vendor,&deviceId));
    EXPECT(!vendor && !deviceId && fixture::reads==before && fixture::accessibleCalls==access);
    EXPECT(!s540Global_os_pci_init_handle(1,0,29,0,nullptr,nullptr));
    EXPECT(fixture::reads==before && fixture::accessibleCalls==access);
    EXPECT(s540Global_os_pci_init_handle(0,0,29,0,&vendor,&deviceId)==facts.upstream.handle);
    EXPECT(vendor==0x8086 && deviceId==0x9d18 && fixture::reads>before && fixture::accessibleCalls==access);
    ++fixture::cases;
    EXPECT(s540Global_os_pci_init_handle(0,2,0,0,&vendor,&deviceId)==binding.pciHandle);
    EXPECT(vendor==0x10de && deviceId==0x1f91 && fixture::accessibleCalls==access+1U);
    fixture::accessible=false;EXPECT(!s540Global_os_pci_init_handle(0,2,0,0,nullptr,nullptr));fixture::accessible=true;
    ++fixture::cases;
    NvU8 byte=0x6d;NvU16 word=0x6d6d;NvU32 dword=0x6d6d6d6d;
    EXPECT(s540Global_os_pci_read_byte(facts.upstream.handle,0,&byte)==NV_OK && byte==0x86);
    EXPECT(s540Global_os_pci_read_word(facts.upstream.handle,0,&word)==NV_OK && word==0x8086);
    EXPECT(s540Global_os_pci_read_dword(facts.upstream.handle,0x100,&dword)==NV_OK && dword==0x11223344);
    EXPECT(!fixture::gpuReads);
    EXPECT(s540Global_os_pci_read_dword(binding.pciHandle,0,&dword)==NV_OK && dword==0x55 && fixture::gpuReads==1);
    ++fixture::cases;
    dword=0x6d6d6d6d;before=fixture::reads;
    EXPECT(s540Global_os_pci_read_dword(facts.fhb.handle,0x100,&dword)==NV_ERR_NOT_SUPPORTED);
    EXPECT(dword==0x6d6d6d6d && fixture::reads==before);
    EXPECT(s540Global_os_pci_read_dword(reinterpret_cast<void *>(NvUPtr(0x7654)),0,&dword)==NV_ERR_OBJECT_NOT_FOUND);
    EXPECT(dword==0x6d6d6d6d && fixture::reads==before);
    EXPECT(s540Global_os_pci_read_byte(nullptr,0,&byte)==NV_ERR_INVALID_STATE);
    EXPECT(s540Global_os_pci_read_word(facts.fhb.handle,0,nullptr)==NV_ERR_INVALID_ARGUMENT);
    ++fixture::cases;
    fixture::failOffset=0x20;byte=0x6d;word=0x6d6d;dword=0x6d6d6d6d;
    EXPECT(s540Global_os_pci_read_byte(facts.upstream.handle,0x20,&byte)==NV_ERR_TIMEOUT && byte==0x6d);
    EXPECT(s540Global_os_pci_read_word(facts.upstream.handle,0x20,&word)==NV_ERR_TIMEOUT && word==0x6d6d);
    EXPECT(s540Global_os_pci_read_dword(facts.upstream.handle,0x20,&dword)==NV_ERR_TIMEOUT && dword==0x6d6d6d6d);
    fixture::failOffset=~0U;
    ++fixture::cases;
    before=fixture::reads;
    EXPECT(s540Global_os_pci_write_byte(facts.upstream.handle,4,0)==NV_ERR_INVALID_STATE);
    EXPECT(s540Global_os_pci_write_word(facts.fhb.handle,4,0)==NV_ERR_INVALID_STATE);
    EXPECT(s540Global_os_pci_write_dword(facts.upstream.handle,4,0)==NV_ERR_INVALID_STATE);
    EXPECT(!fixture::gpuWrites && fixture::reads==before);
    EXPECT(s540Global_os_pci_write_word(binding.pciHandle,4,0)==NV_OK && fixture::gpuWrites==1);
    ++fixture::cases;
    fixture::ordinary=false;
    EXPECT(!s540PciTopologyUsesOsConfig(&nv));
    EXPECT(s540PciTopologyValidateForGsp(&nv,&facts)==NV_ERR_INVALID_STATE);
    dword=0x6d6d6d6d;before=fixture::reads;
    EXPECT(s540Global_os_pci_read_dword(facts.fhb.handle,0,&dword)==NV_ERR_INVALID_STATE && dword==0x6d6d6d6d && fixture::reads==before);
    fixture::ordinary=true;
    ++fixture::cases;
    fixture::authorityStatus=NV_ERR_NOT_SUPPORTED;before=fixture::reads;
    EXPECT(s540PciTopologyValidateForGsp(&nv,&facts)==NV_ERR_NOT_SUPPORTED && fixture::reads==before);
    EXPECT(!s540PciTopologyUsesOsConfig(&nv));fixture::authorityStatus=NV_OK;
    ++fixture::cases;
    fixture::authorityFlipAt=fixture::authorityCalls+2U;fixture::changedAuthorityStatus=NV_ERR_OPERATION_ABORTED;
    EXPECT(s540PciTopologyValidateForGsp(&nv,&facts)==NV_ERR_OPERATION_ABORTED);fixture::authorityFlipAt=0;
    ++fixture::cases;
    fixture::generationFlipAt=fixture::authorityCalls+2U;
    EXPECT(s540PciTopologyValidateForGsp(&nv,&facts)==NV_ERR_INVALID_STATE);fixture::generationFlipAt=0;
    ++fixture::cases;
    fixture::authorityFlipAt=fixture::authorityCalls+2U;
    EXPECT(!s540PciTopologyUsesOsConfig(&nv));fixture::authorityFlipAt=0;
    ++fixture::cases;
    s540PciTopologyRecordFailure(5,NV_OK);EXPECT(!fixture::refusalCalls && !fixture::aggregateCalls);
    s540PciTopologyRecordFailure(5,NV_ERR_TIMEOUT);
    EXPECT(fixture::refusalCalls==1 && fixture::aggregateCalls==1 && fixture::order==2);
    EXPECT(fixture::refusalDomain==7 && fixture::refusalSymbol==605 && fixture::aggregateService==605 && fixture::refusalStatus==NV_ERR_TIMEOUT);
    fixture::order=0;s540PciTopologyRecordFailure(~0U,NV_ERR_NOT_SUPPORTED);
    EXPECT(fixture::refusalSymbol==600 && fixture::aggregateService==600 && fixture::refusalStatus==NV_ERR_NOT_SUPPORTED);
    ++fixture::cases;
    fixture::active=false;
    EXPECT(!s540PciTopologyUsesOsConfig(&nv));
    EXPECT(s540PciTopologyValidateForGsp(&nv,&facts)==NV_ERR_INVALID_STATE);
    fixture::active=true;
    printf("{\"cases\":%u,\"checks\":%u,\"failures\":%u}\n",fixture::cases,fixture::checks,fixture::failures);
    return fixture::failures ? 1 : 0;
}
