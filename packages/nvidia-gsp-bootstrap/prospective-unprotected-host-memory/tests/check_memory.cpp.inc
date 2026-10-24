// Explicit CPU-only raw-CPUID and OS-resource endpoints. Neither hardware nor
// IOKit executes here. The complete selected Services and Session bodies do.
#include "@SERVICE_HEADER@"
#include "@COMMIT_HEADER@"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <initializer_list>
using namespace S540NvidiaDeviceTransport;
namespace MemoryFixture {
struct Registers { NvU32 eax, ebx, ecx, edx; };
struct Cpu { Registers basic, signature, structured; NvU32 calls, leaves; };
Cpu cpu{};
NvU32 checks=0, cases=0;
void expect(bool value,const char *message) {
    ++checks;
    if(!value){std::fprintf(stderr,"Memory policy assertion failed: %s\n",message);std::exit(1);}
}
void target() {
    cpu = {{7U,0x756e6547U,0x6c65746eU,0x49656e69U},
           {0x000806eaU,0,0,0},{0,0,0,0},0,0};
}
void cpuid(NvU32 leaf,NvU32 subleaf,NvU32 &a,NvU32 &b,NvU32 &c,NvU32 &d) {
    ++cpu.calls; expect(subleaf==0,"only explicit subleaf zero is observed");
    const Registers *r=nullptr;
    if(leaf==0){cpu.leaves|=1;r=&cpu.basic;}
    if(leaf==1){expect(cpu.basic.eax>=1,"signature never queried without supported leaf");cpu.leaves|=2;r=&cpu.signature;}
    if(leaf==7){expect(cpu.basic.eax>=7,"structured features never queried without supported leaf");cpu.leaves|=4;r=&cpu.structured;}
    expect(r!=nullptr,"only reviewed basic leaves are observed");a=r->eax;b=r->ebx;c=r->ecx;d=r->edx;
}
struct Resource { NvU8 *host; NvU32 pages; NvU64 physical; bool mapped; };
struct Endpoint {
    bool active=false,ordinary=true,failAllocation=false,failMap=false,failUnmap=false;
    NvU32 resources=0,allocations=0,maps=0,unmaps=0,releases=0;
    Resource *latest=nullptr;
};
bool isOrdinary(void *p){return static_cast<Endpoint*>(p)->ordinary;}
NV_STATUS start(void *p,Snapshot &s){static_cast<Endpoint*>(p)->active=true;
    s={true,true,true,true,true,true,true,64,Mapper::Device,0x1000000,0,1,0,0,true,0x10000,true,true,true,false};return NV_OK;}
NV_STATUS stop(void *p){auto&e=*static_cast<Endpoint*>(p);if(e.resources)return NV_ERR_IN_USE;e.active=false;return NV_OK;}
bool live(void *p){return static_cast<Endpoint*>(p)->active;}
NV_STATUS identity(void*,NvU32 offset,NvU32 &out){out=offset?0x1f9110de:0x167000a1;return NV_OK;}
NV_STATUS allocate(void*p,NvU32 pages,bool,NvU32,void**out,NvU8**host){
    auto&e=*static_cast<Endpoint*>(p);++e.allocations;if(e.failAllocation)return NV_ERR_NO_MEMORY;
    auto*r=new Resource{static_cast<NvU8*>(std::calloc(pages,kPageBytes)),pages,
        0x10000000ULL+NvU64(e.allocations)*0x100000ULL,false};
    if(!r->host){delete r;return NV_ERR_NO_MEMORY;}++e.resources;e.latest=r;*out=r;*host=r->host;return NV_OK;
}
NV_STATUS address(void*,void*p,NvU32 page,bool mapped,NvU64&out){auto&r=*static_cast<Resource*>(p);
    if(page>=r.pages||(mapped&&!r.mapped))return NV_ERR_INVALID_ARGUMENT;
    out=r.physical+NvU64(page)*kPageBytes+(mapped?0x40000000ULL:0);return NV_OK;}
NV_STATUS map(void*p,void*r,NvU32 bits){auto&e=*static_cast<Endpoint*>(p);++e.maps;
    if(e.failMap||bits!=64)return NV_ERR_OPERATING_SYSTEM;static_cast<Resource*>(r)->mapped=true;return NV_OK;}
NV_STATUS unmap(void*p,void*r){auto&e=*static_cast<Endpoint*>(p);++e.unmaps;
    if(e.failUnmap)return NV_ERR_OPERATING_SYSTEM;static_cast<Resource*>(r)->mapped=false;return NV_OK;}
NV_STATUS release(void*p,void*r){auto&e=*static_cast<Endpoint*>(p);auto*m=static_cast<Resource*>(r);
    if(m->mapped)return NV_ERR_IN_USE;std::free(m->host);delete m;++e.releases;--e.resources;return NV_OK;}
NV_STATUS install(void*,const InterruptContract&){return NV_ERR_NOT_SUPPORTED;}
NV_STATUS irq(void*){return NV_ERR_NOT_SUPPORTED;}
NV_STATUS policy(void*,DmaRemapPolicy &out){out=DmaRemapPolicy::MapPhysicalPagesWithoutBounce;return NV_OK;}
Detail::Backend backend(Endpoint&e){return {&e,isOrdinary,start,stop,live,identity,allocate,address,map,unmap,
    release,install,irq,irq,nullptr,nullptr,nullptr,nullptr,nullptr,nullptr,policy,nullptr};}
}
@SERVICES_BODY@
// Explicit forbidden endpoints: these tests cannot fabricate a stop receipt or
// cancellation authority; unexpected calls must fail, rather than grant either.
extern "C" NV_STATUS s540GspCancellationCommitEnterState(const void*,S540GspCancellationCommitLease*){return NV_ERR_NOT_SUPPORTED;}
extern "C" NV_STATUS s540GspCancellationCommitLeaveState(const void*,S540GspCancellationCommitLease){return NV_ERR_NOT_SUPPORTED;}
extern "C" NV_STATUS s540GspContextValidateDmaStopReceipt(const void*,const void*,NvU64,const S540GspDmaStopReceipt*){return NV_ERR_NOT_SUPPORTED;}
int main(){
    using namespace MemoryFixture;
    Endpoint endpoint;Session session;
    auto*state=reinterpret_cast<nv_state_t*>(NvUPtr(0x540));
    auto*dma=reinterpret_cast<nv_dma_device_t*>(NvUPtr(0x541));
    target();expect(session.start(backend(endpoint))==NV_OK,"actual Session starts on explicit OS fixture");
    expect(bindRmDevice(&session,state,dma)==NV_OK,"actual Services binds exact state");
    auto request=[&](NvU32 pages=2,NvU64 bytes=4096,NvBool contiguous=0,NvU32 cache=0,
                     NvBool zeroed=1,NvBool unprotected=1,NvS32 node=-1,NV_STATUS wanted=NV_ERR_NOT_SUPPORTED){
        ++cases;NvU64 ptes[2]={0x1234,0x5678};void*token=reinterpret_cast<void*>(NvUPtr(0x999));
        const auto allocations=endpoint.allocations,resources=endpoint.resources;
        NV_STATUS status=s540Global_nv_alloc_pages(state,pages,bytes,contiguous,cache,zeroed,unprotected,node,ptes,&token);
        expect(status==wanted,"exact allocation status");
        if(wanted!=NV_OK){expect(ptes[0]==0x1234&&ptes[1]==0x5678&&token==reinterpret_cast<void*>(NvUPtr(0x999)),"refusal preserves outputs");
            expect(endpoint.resources==resources,"failure preserves resource count");
            if(wanted!=NV_ERR_NO_MEMORY)expect(endpoint.allocations==allocations,"policy refusal precedes OS allocation");}
        else{expect(token!=reinterpret_cast<void*>(NvUPtr(0x999))&&ptes[0]&&!(ptes[0]&4095),"successful output publication uses actual physical page");
            expect(s540Global_nv_free_pages(state,pages,contiguous,cache,token)==NV_OK,"actual Services frees successful allocation");}
    };
    request(2,4096,0,0,1,1,-1,NV_OK);expect(cpu.calls==3&&cpu.leaves==7,"target uses actual three-leaf capture");
    target();cpu.structured.ebx=1U<<2;request(2,4096,0,0,0,1,-1,NV_OK); // SGX capability does not make ordinary pages EPC.
    for(NvU32 maximum:{0U,1U,6U}){target();cpu.basic.eax=maximum;request();expect(cpu.calls==(maximum?2U:1U),"unsupported leaves are never executed");}
    target();cpu.basic.ebx^=1;request();target();cpu.basic.edx^=1;request();target();cpu.basic.ecx^=1;request();
    for(NvU32 signature:{0x000805eaU,0x000806daU,0x000706eaU,0x00180feaU}){target();cpu.signature.eax=signature;request();}
    target();cpu.signature.ecx=1U<<31;request();target();cpu.structured.ecx=1U<<13;request();
    target();cpu.structured.ecx=(1U<<12)|(1U<<14);request(2,4096,0,0,1,1,-1,NV_OK);
    target();cpu.signature.ecx=1U<<31;cpu.structured.ecx=1U<<13;request(2,4096,0,0,1,0,-1,NV_OK);
    expect(cpu.calls==0,"ordinary protected-default request preserves previous behavior without host probe");
    target();request(2,2U*1024U*1024U);request(8193);request(2,4096,0,3);request(2,4096,0,0,1,1,0);
    request(0,4096,0,0,1,1,-1,NV_ERR_INVALID_ARGUMENT);
    request(2,4096,2,0,1,1,-1,NV_ERR_INVALID_ARGUMENT);request(2,4096,0,0,2,1,-1,NV_ERR_INVALID_ARGUMENT);
    request(2,4096,0,0,1,2,-1,NV_ERR_INVALID_ARGUMENT);
    for(bool nullPtes:{false,true}){++cases;NvU64 ptes[2]={1,2};void*token=reinterpret_cast<void*>(NvUPtr(3));
        const auto attempts=endpoint.allocations;
        expect(s540Global_nv_alloc_pages(state,2,4096,0,0,1,1,-1,nullPtes?nullptr:ptes,nullPtes?&token:nullptr)==NV_ERR_INVALID_ARGUMENT,"null output refused");
        expect(ptes[0]==1&&token==reinterpret_cast<void*>(NvUPtr(3))&&endpoint.allocations==attempts,"null refusal is atomic");}
    target();endpoint.failAllocation=true;request(2,4096,0,0,1,1,-1,NV_ERR_NO_MEMORY);endpoint.failAllocation=false;
    // Full actual Session + Services allocation/map/unmap/mapping bodies execute.
    NvU64 ptes[2]={};void*allocation=nullptr;target();
    expect(s540Global_nv_alloc_pages(state,2,4096,0,2,1,1,-1,ptes,&allocation)==NV_OK,"cache2 target allocation");
    expect(endpoint.latest&&endpoint.latest->host[0]==0&&endpoint.latest->host[8191]==0,"explicit OS endpoint returned zeroed ordinary pages");
    const NvU64 physical=ptes[0];void*mapPrivate=nullptr;
    void*host=s540Global_nv_alloc_kernel_mapping(state,allocation,0,0,8192,&mapPrivate);
    expect(host==endpoint.latest->host&&mapPrivate,"actual kernel-map body borrows same allocation");
    std::memset(host,0xa5,8192);expect(endpoint.latest->host[8191]==0xa5,"same backing identity");
    s540Global_nv_free_kernel_mapping(state,allocation,host,mapPrivate);
    endpoint.failMap=true;void*dmaToken=allocation;
    expect(s540Global_nv_dma_map_alloc(dma,2,ptes,0,0,&dmaToken)==NV_ERR_OPERATING_SYSTEM,"actual DMA map error propagates");
    expect(dmaToken==allocation&&ptes[0]==physical,"failed DMA map preserves ownership and PTE");endpoint.failMap=false;
    expect(s540Global_nv_dma_map_alloc(dma,2,ptes,0,0,&dmaToken)==NV_OK&&ptes[0]==physical+0x40000000ULL,"genuine endpoint translation published");
    endpoint.failUnmap=true;const NvU64 mapped=ptes[0];void*mappedToken=dmaToken;
    expect(s540Global_nv_dma_unmap_alloc(dma,2,ptes,&dmaToken)==NV_ERR_OPERATING_SYSTEM,"actual DMA unmap error propagates");
    expect(dmaToken==mappedToken&&ptes[0]==mapped,"failed DMA unmap preserves device ownership");endpoint.failUnmap=false;
    expect(s540Global_nv_dma_unmap_alloc(dma,2,ptes,&dmaToken)==NV_OK&&dmaToken==allocation&&ptes[0]==physical,"actual DMA unmap restores physical output");
    expect(s540Global_nv_free_pages(state,2,0,2,allocation)==NV_OK,"translated backing freed only after actual endpoint unmap");
    // A failed liveness/ordinary Session guard remains authoritative after CPU admission.
    target();endpoint.ordinary=false;request(2,4096,0,0,1,1,-1,NV_ERR_INVALID_STATE);endpoint.ordinary=true;
    target();endpoint.active=false;request(2,4096,0,0,1,1,-1,NV_ERR_INVALID_STATE);endpoint.active=true;
    // Allocation records and token generation do not acquire extra authority.
    void*held[kMaximumAllocations]{};NvU64 one[1]{};
    for(NvU32 i=0;i<kMaximumAllocations;++i)expect(s540Global_nv_alloc_pages(state,1,4096,0,0,1,1,-1,one,&held[i])==NV_OK,"bounded actual allocation records");
    request(1,4096,0,0,1,1,-1,NV_ERR_INSUFFICIENT_RESOURCES);
    for(void*token:held)expect(s540Global_nv_free_pages(state,1,0,0,token)==NV_OK,"bounded record cleanup");
    const NvU64 generation=abiGeneration;abiGeneration=~NvU64(0)>>2;
    request(1,4096,0,0,1,1,-1,NV_ERR_INSUFFICIENT_RESOURCES);abiGeneration=generation;
    for(NvU32 i=0;i<40;++i){target();cpu.structured.ecx=1U<<13;request();}
    expect(unprotectedRequestLogged==1&&allocationFailureLogs==16,"diagnostics bounded to first request plus sixteen failures");
    expect(endpoint.resources==0,"all ordinary fixture allocations released");
    expect(unbindRmDevice(&session)==NV_OK&&session.stop()==NV_OK,"actual binding and Session cleanup");
    std::printf("{\"cases\":%u,\"checks\":%u,\"synthetic_cpuid\":true,\"actual_whole_services\":true,\"actual_whole_session\":true}\n",cases,checks);
}
