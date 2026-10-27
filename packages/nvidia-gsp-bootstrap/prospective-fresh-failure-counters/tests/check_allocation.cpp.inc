// Explicit CPU-only kernel primitives, raw CPUID and resource endpoints.
// Complete actual KERNEL-branch Services and complete actual Session execute;
// no Darwin SDK, IOKit, controller or GPU executes in this host control.
#include "@SERVICE_HEADER@"
#include "@COMMIT_HEADER@"
#include "@ALLOCATION_HEADER@"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <initializer_list>
#include <thread>
#include <atomic>
#include "@RECORD_HEADER@"
#include <IOKit/IOLib.h>
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
NV_STATUS install(void*,const InterruptContract&){return NV_OK;}
NV_STATUS irq(void*){return NV_OK;}
NV_STATUS policy(void*,DmaRemapPolicy &out){out=DmaRemapPolicy::MapPhysicalPagesWithoutBounce;return NV_OK;}
Detail::Backend backend(Endpoint&e){return {&e,isOrdinary,start,stop,live,identity,allocate,address,map,unmap,
    release,install,irq,irq,nullptr,nullptr,nullptr,nullptr,nullptr,nullptr,policy,nullptr};}
}

static bool fixtureInInterrupt, fixtureInterruptsEnabled = true;
static NvU32 fixtureLogs;
extern "C" int ml_at_interrupt_context(void) { return fixtureInInterrupt; }
extern "C" int ml_get_interrupts_enabled(void) { return fixtureInterruptsEnabled; }
extern "C" [[noreturn]] void panic(const char *, ...) { std::abort(); }
extern "C" void IOLog(const char *format, ...) {
    ++fixtureLogs;
    MemoryFixture::expect(format && !std::strstr(format,"%p"),"kernel logger receives scalar-only format");
}
@SERVICES_BODY@
extern "C" NV_STATUS s540GspCancellationCommitEnterState(const void*,S540GspCancellationCommitLease*){return NV_ERR_NOT_SUPPORTED;}
extern "C" NV_STATUS s540GspCancellationCommitLeaveState(const void*,S540GspCancellationCommitLease){return NV_ERR_NOT_SUPPORTED;}
extern "C" NV_STATUS s540GspContextValidateDmaStopReceipt(const void*,const void*,NvU64,const S540GspDmaStopReceipt*){return NV_ERR_NOT_SUPPORTED;}
namespace S540NvidiaDeviceTransport {
void destroyDarwinBackend(void *) { std::abort(); }
}
static bool fixtureTop(void *, bool &, bool &) { std::abort(); }
static void fixtureBottom(void *) { std::abort(); }
static NV_STATUS fixtureMask(void *) { std::abort(); }
static bool fixtureReady(void *) { return true; }

static const void *fixtureRecordNv;
static S540FirstTxnSnapshot fixtureRecord;
static NV_STATUS fixtureRecordStatus=NV_ERR_INVALID_STATE, fixtureThreadStatus=NV_OK;
static NvU64 fixtureThread=0x123;
extern "C" NV_STATUS s540FirstTxnGetSnapshot(const void *state,S540FirstTxnSnapshot *out) {
    if(fixtureRecordStatus!=NV_OK)return fixtureRecordStatus;
    if(!out||state!=fixtureRecordNv)return NV_ERR_INVALID_ARGUMENT;
    *out=fixtureRecord;return NV_OK;
}
extern "C" NV_STATUS NV_API_CALL s540Darwin_os_get_current_thread(NvU64 *out) {
    if(fixtureThreadStatus!=NV_OK)return fixtureThreadStatus;
    if(!out)return NV_ERR_INVALID_ARGUMENT;*out=fixtureThread;return NV_OK;
}
static void readable(const void *state) {
    fixtureRecordNv=state;fixtureRecordStatus=fixtureThreadStatus=NV_OK;fixtureThread=0x123;
    fixtureRecord={};fixtureRecord.masterThread=fixtureThread;fixtureRecord.originalReturned=NV_TRUE;
}
static S540DeviceAllocationDiagnostics capture(const void *state) {
    using namespace MemoryFixture;S540DeviceAllocationDiagnostics result;
    ++cases;const auto logs=fixtureLogs;const auto cpuCalls=MemoryFixture::cpu.calls;
    expect(s540DeviceReadAllocationDiagnostics(state,&result)==NV_OK,"actual atomic diagnostic getter succeeds after returned master wrapper");
    expect(result.format==1&&result.bytes==112,"private C-compatible diagnostic shape");
    expect(result.observedMask&S540_DEVICE_ALLOC_DIAG_COUNTS,"counts explicitly observed");
    expect(fixtureLogs==logs&&MemoryFixture::cpu.calls==cpuCalls,"scalar getter emits no nested log or new CPUID");return result;
}
static S540DeviceAllocationFailure concurrentFailure(unsigned i) {
    S540DeviceAllocationFailure value{};value.stage=1+i%6;value.status=NV_ERR_OPERATING_SYSTEM+i;
    value.pages=101+i;value.contiguous=i%2;value.cache=i%3;value.zeroed=i%2;
    value.unprotected=(i+1)%2;value.node=-1-static_cast<NvS32>(i);value.pageBytes=4096ULL*(i+1);
    value.cpuObservedMask=7;value.maxBasic=0x10+i;value.vendorEbx=0x100+i;value.vendorEdx=0x200+i;
    value.vendorEcx=0x300+i;value.signature=0x400+i;value.family=6;value.model=0x8e + i;
    value.leaf1Ecx=0x500+i;value.leaf7Ecx=0x600+i;return value;
}
static int concurrentControl(void) {
    using namespace MemoryFixture;auto *state=reinterpret_cast<void *>(NvUPtr(0x540));readable(state);
    constexpr unsigned workers=8,iterations=1000;std::atomic<bool> start{false};std::thread threads[workers];
    for(unsigned i=0;i<workers;++i)threads[i]=std::thread([&,i](){
        auto failure=concurrentFailure(i);
        while(!start.load(std::memory_order_acquire))std::this_thread::yield();
        for(unsigned j=0;j<iterations;++j){observeAllocationAttempt(101+i);observeAllocationFailure(failure);}
    });
    start.store(true,std::memory_order_release);
    for(unsigned spin=0;spin<100000&&__atomic_load_n(&allocationObservation.firstFailureState,__ATOMIC_ACQUIRE)!=2;++spin)std::this_thread::yield();
    expect(__atomic_load_n(&allocationObservation.firstFailureState,__ATOMIC_ACQUIRE)==2,"one concurrent failure writer publishes");
    auto initial=capture(state);NvU32 previousAttempts=0,previousFailures=0,previousLargest=0;
    for(unsigned i=0;i<1000;++i){auto value=capture(state);
        expect(value.observedMask==3&&value.firstFailureState==2,"published tuple explicitly observed");
        expect(value.firstFailure.pages>=101&&value.firstFailure.pages<101+workers,"first tuple belongs to actual concurrent writer");
        auto wanted=concurrentFailure(value.firstFailure.pages-101);
        expect(!std::memcmp(&value.firstFailure,&wanted,sizeof(wanted)),"all stage, request and CPU scalar fields come from one publication winner");
        expect(!std::memcmp(&value.firstFailure,&initial.firstFailure,sizeof(wanted)),"published tuple immutable under later failures");
        expect(value.allocationAttemptsLifetime>=previousAttempts&&value.allocationAttemptsLifetime<=workers*iterations&&
            value.allocationFailuresLifetime>=previousFailures&&value.allocationFailuresLifetime<=workers*iterations&&
            value.largestRequestedPagesLifetime>=previousLargest&&value.largestRequestedPagesLifetime<=108,"independently sampled counters individually monotonic");
        previousAttempts=value.allocationAttemptsLifetime;previousFailures=value.allocationFailuresLifetime;previousLargest=value.largestRequestedPagesLifetime;
    }
    for(auto &thread:threads)thread.join();auto final=capture(state);
    expect(final.allocationAttemptsLifetime==workers*iterations&&final.allocationFailuresLifetime==workers*iterations&&
        final.largestRequestedPagesLifetime==108&&!final.entryRejectionsLifetime,"atomic increments preserve all concurrent observations");
    __atomic_store_n(&allocationObservation.attempts,~NvU32(0),__ATOMIC_RELAXED);
    __atomic_store_n(&allocationObservation.failures,~NvU32(0),__ATOMIC_RELAXED);
    __atomic_store_n(&allocationObservation.entryRejections,~NvU32(0),__ATOMIC_RELAXED);
    auto later=concurrentFailure(0);observeAllocationAttempt(1);observeAllocationFailure(later);recordAllocationEntryRejection();
    final=capture(state);expect(final.allocationAttemptsLifetime==~NvU32(0)&&final.allocationFailuresLifetime==~NvU32(0)&&
        final.entryRejectionsLifetime==~NvU32(0)&&!std::memcmp(&final.firstFailure,&initial.firstFailure,sizeof(later)),"numeric-boundary injection cannot wrap or replace first tuple");
    std::printf("{\"status\":\"passed\",\"cases\":%u,\"checks\":%u,\"writers\":8}\n",cases,checks);return 0;
}
static int reservedControl(void) {
    using namespace MemoryFixture;auto *state=reinterpret_cast<void *>(NvUPtr(0x540));readable(state);
    std::memset(&allocationObservation.firstFailure,0xa5,sizeof(allocationObservation.firstFailure));
    __atomic_store_n(&allocationObservation.firstFailureState,1U,__ATOMIC_RELEASE);
    auto value=capture(state);S540DeviceAllocationFailure zero{};
    expect(value.firstFailureState==1&&value.observedMask==1&&!std::memcmp(&value.firstFailure,&zero,sizeof(zero)),"reserved unpublished tuple remains unavailable without torn data");
    std::printf("{\"status\":\"passed\",\"cases\":%u,\"checks\":%u}\n",cases,checks);return 0;
}
static int firstStageControl(unsigned stage) {
    using namespace MemoryFixture;Endpoint endpoint;Session session;
    auto *state=reinterpret_cast<nv_state_t *>(NvUPtr(0x540));auto *dma=reinterpret_cast<nv_dma_device_t *>(NvUPtr(0x541));
    readable(state);target();expect(session.start(backend(endpoint))==NV_OK&&bindRmDevice(&session,state,dma)==NV_OK,"actual stage fixture binds");
    NvU64 ptes[3]={};void *allocation=nullptr;NvU32 pages=2;NvU64 bytes=4096;NV_STATUS wanted=NV_ERR_NOT_SUPPORTED;
    void *held[kMaximumAllocations]{};NvU64 one[1]{};const auto generation=abiGeneration;
    if(stage==1){pages=0;wanted=NV_ERR_INVALID_ARGUMENT;}
    if(stage==2)bytes=2097152;
    if(stage==3)cpu.structured.ecx=1U<<13;
    if(stage==4){for(NvU32 i=0;i<kMaximumAllocations;++i)expect(s540Global_nv_alloc_pages(state,1,4096,0,0,1,1,-1,one,&held[i])==NV_OK,"real records fill");wanted=NV_ERR_INSUFFICIENT_RESOURCES;}
    if(stage==5){abiGeneration=~NvU64(0)>>2;wanted=NV_ERR_INSUFFICIENT_RESOURCES;}
    if(stage==6){endpoint.failAllocation=true;pages=3;wanted=NV_ERR_NO_MEMORY;}
    expect(s540Global_nv_alloc_pages(state,pages,bytes,0,0,1,1,-1,ptes,&allocation)==wanted,"actual stage refusal preserves selected status");
    auto value=capture(state);auto &f=value.firstFailure;
    expect(value.firstFailureState==2&&value.observedMask==3&&f.stage==stage&&f.status==wanted&&f.pages==pages&&f.pageBytes==bytes,"exact failure site and geometry observed");
    expect(f.contiguous==0&&f.cache==0&&f.zeroed==1&&f.unprotected==1&&f.node==-1,"actual request flags copied without clearing");
    expect(f.cpuObservedMask==(stage<=2?0U:7U),"only existing request CPU observations copied");
    if(stage>2)expect(f.maxBasic==7&&f.vendorEbx==0x756e6547U&&f.vendorEdx==0x49656e69U&&f.vendorEcx==0x6c65746eU&&
        f.signature==0x806eaU&&f.family==6&&f.model==0x8e&&f.leaf1Ecx==0&&f.leaf7Ecx==(stage==3?1U<<13:0),"actual captured raw CPU evidence and decode");
    if(stage==5)abiGeneration=generation;endpoint.failAllocation=false;
    if(stage==4)for(auto *entry:held)expect(s540Global_nv_free_pages(state,1,0,0,entry)==NV_OK,"real filled records release");
    expect(unbindRmDevice(&session)==NV_OK&&session.stop()==NV_OK&&!endpoint.resources,"stage fixtures release all actual resources");
    std::printf("{\"status\":\"passed\",\"cases\":%u,\"checks\":%u}\n",cases,checks);return 0;
}
int main(int argc,char **argv) {
    using namespace MemoryFixture;
    if(argc==2&&std::strcmp(argv[1],"--concurrency")==0)return concurrentControl();
    if(argc==2&&std::strcmp(argv[1],"--reserved")==0)return reservedControl();
    if(argc==2&&std::strncmp(argv[1],"--stage-",8)==0)return firstStageControl(static_cast<unsigned>(std::atoi(argv[1]+8)));
    Endpoint endpoint;Session session;auto *state=reinterpret_cast<nv_state_t *>(NvUPtr(0x540));
    auto *other=reinterpret_cast<nv_state_t *>(NvUPtr(0x549));auto *dma=reinterpret_cast<nv_dma_device_t *>(NvUPtr(0x541));
    S540DeviceAllocationDiagnostics observation,before;
    auto unavailable=[&](const void *identity,NV_STATUS wanted){++cases;std::memset(&observation,0xa5,sizeof(observation));before=observation;
        expect(s540DeviceReadAllocationDiagnostics(identity,&observation)==wanted,"diagnostic refusal status");
        expect(!std::memcmp(&observation,&before,sizeof(before)),"refused diagnostic preserves outputs");};
    unavailable(state,NV_ERR_INVALID_STATE);unavailable(nullptr,NV_ERR_INVALID_ARGUMENT);
    expect(s540DeviceReadAllocationDiagnostics(state,nullptr)==NV_ERR_INVALID_ARGUMENT,"null output refused");
    readable(state);fixtureRecord.originalReturned=NV_FALSE;unavailable(state,NV_ERR_NOT_READY);
    fixtureRecord.originalReturned=NV_TRUE;fixtureRecord.originalInFlight=NV_TRUE;unavailable(state,NV_ERR_NOT_READY);
    fixtureRecord.originalInFlight=NV_FALSE;fixtureThread=0x124;unavailable(state,NV_ERR_INVALID_STATE);
    fixtureThread=0;unavailable(state,NV_ERR_INVALID_STATE);fixtureThread=0x123;
    fixtureThreadStatus=NV_ERR_TIMEOUT;unavailable(state,NV_ERR_TIMEOUT);fixtureThreadStatus=NV_OK;
    unavailable(other,NV_ERR_INVALID_ARGUMENT);
    NvU64 ptes[3]={11,22,33};void *allocation=reinterpret_cast<void *>(NvUPtr(9));
    expect(s540Global_nv_alloc_pages(state,2,4096,0,0,1,0,-1,ptes,&allocation)==NV_ERR_INVALID_STATE,"unbound actual allocator entry refused");
    auto value=capture(state);expect(!value.allocationAttemptsLifetime&&!value.allocationFailuresLifetime&&value.entryRejectionsLifetime==1&&value.observedMask==1,"observer distinguishes invalid entry from validated geometry");
    target();expect(session.start(backend(endpoint))==NV_OK&&bindRmDevice(&session,state,dma)==NV_OK,"actual Session and Services bind");
    expect(s540Global_nv_alloc_pages(state,2,4096,0,0,1,0,-1,ptes,&allocation)==NV_OK,"actual ordinary allocation");
    value=capture(state);expect(value.allocationAttemptsLifetime==1&&!value.allocationFailuresLifetime&&value.largestRequestedPagesLifetime==2&&endpoint.resources==1,"observer records real attempt without reading owned arrays");
    void *mapping=nullptr;void *host=s540Global_nv_alloc_kernel_mapping(state,allocation,0,0,8192,&mapping);
    expect(host&&mapping,"actual CPU mapping");void *dmaToken=allocation;
    expect(s540Global_nv_dma_map_alloc(dma,2,ptes,0,0,&dmaToken)==NV_OK&&s540Global_nv_dma_unmap_alloc(dma,2,ptes,&dmaToken)==NV_OK,"actual translated DMA map and unmap");
    s540Global_nv_free_kernel_mapping(state,allocation,host,mapping);
    expect(s540Global_nv_free_pages(state,2,0,0,allocation)==NV_OK&&!endpoint.resources,"actual ordinary resource release");
    ptes[0]=11;allocation=reinterpret_cast<void *>(NvUPtr(9));
    expect(s540Global_nv_alloc_pages(state,2,2097152,0,0,1,1,-1,ptes,&allocation)==NV_ERR_NOT_SUPPORTED&&ptes[0]==11&&allocation==reinterpret_cast<void *>(NvUPtr(9)),"actual huge-geometry refusal preserves outputs");
    value=capture(state);expect(value.allocationAttemptsLifetime==2&&value.allocationFailuresLifetime==1&&value.observedMask==3&&value.firstFailureState==2&&value.firstFailure.status==NV_ERR_NOT_SUPPORTED&&value.firstFailure.pages==2&&value.firstFailure.pageBytes==2097152,"first real failed geometry is published exactly");
    target();endpoint.failAllocation=true;
    expect(s540Global_nv_alloc_pages(state,3,4096,0,0,1,1,-1,ptes,&allocation)==NV_ERR_NO_MEMORY,"actual allocation backend error");endpoint.failAllocation=false;
    target();cpu.structured.ecx=1U<<13;const auto allocations=endpoint.allocations;
    expect(s540Global_nv_alloc_pages(state,1,4096,0,0,1,1,-1,ptes,&allocation)==NV_ERR_NOT_SUPPORTED&&endpoint.allocations==allocations,"TME gate still precedes backend");
    value=capture(state);expect(value.allocationAttemptsLifetime==4&&value.allocationFailuresLifetime==3&&value.largestRequestedPagesLifetime==3&&
        value.firstFailure.status==NV_ERR_NOT_SUPPORTED&&value.firstFailure.pages==2&&value.firstFailure.pageBytes==2097152,"later backend and policy failures cannot replace first tuple");
    expect(s540Global_nv_alloc_pages(other,2,4096,0,0,1,0,-1,ptes,&allocation)==NV_ERR_INVALID_STATE,"actual wrong-identity allocator entry");
    fixtureInInterrupt=true;unavailable(state,NV_ERR_INVALID_STATE);
    expect(s540Global_nv_alloc_pages(state,2,4096,0,0,1,0,-1,ptes,&allocation)==NV_ERR_INVALID_STATE,"interrupt allocator entry rejected");fixtureInInterrupt=false;
    fixtureInterruptsEnabled=false;unavailable(state,NV_ERR_INVALID_STATE);
    expect(s540Global_nv_alloc_pages(state,2,4096,0,0,1,0,-1,ptes,&allocation)==NV_ERR_INVALID_STATE,"interrupt-disabled allocator entry rejected");fixtureInterruptsEnabled=true;
    value=capture(state);expect(value.allocationAttemptsLifetime==4&&value.allocationFailuresLifetime==3&&value.entryRejectionsLifetime==4,"invalid entries never capture unvalidated geometry");
    target();expect(s540Global_nv_alloc_pages(state,2,4096,0,0,1,0,-1,ptes,&allocation)==NV_OK,"backing for actual retirement");dmaToken=allocation;
    expect(s540Global_nv_dma_map_alloc(dma,2,ptes,0,0,&dmaToken)==NV_OK,"actual resource map before retirement");
    InterruptContract contract{};contract.context=&endpoint;contract.top=fixtureTop;
    contract.lockedBottomHalf=fixtureBottom;contract.unlockedBottomHalf=fixtureBottom;contract.maskHardware=fixtureMask;contract.readyToArm=fixtureReady;
    expect(session.installInterrupt(contract)==NV_OK&&session.armInterrupt()==NV_OK,"actual Session tracks explicit CPU-only controller endpoint");
    expect(s540Global_nv_dma_unmap_alloc(dma,2,ptes,&dmaToken)==NV_OK&&s540Global_nv_free_pages(state,2,0,0,allocation)==NV_OK,"actual controller-held ownership retires");
    const auto retained=session.retirementStatistics();expect(retained.allocations==1&&retained.dmaMappings==1&&endpoint.resources==1,"actual resources remain held");
    value=capture(state);expect(value.allocationAttemptsLifetime==5&&value.allocationFailuresLifetime==3&&endpoint.resources==1,"atomic observer grants no ownership or reclamation");
    expect(drainRmRetirements(&session)==NV_ERR_IN_USE&&endpoint.resources==1,"read success cannot authorize drain");
    expect(session.stopInterrupt()==NV_OK&&drainRmRetirements(&session)==NV_OK&&!endpoint.resources,"actual pre-original controller release before backing drain");
    expect(unbindRmDevice(&session)==NV_OK&&session.stop()==NV_OK,"actual binding and Session cleanup");
    value=capture(state);expect(value.allocationAttemptsLifetime==5&&value.allocationFailuresLifetime==3&&value.firstFailure.pageBytes==2097152,"post-return atomic observer needs no live binding arrays");
    expect(session.start(backend(endpoint))==NV_OK&&bindRmDevice(&session,state,dma)==NV_OK,"second actual binding");
    value=capture(state);expect(value.allocationAttemptsLifetime==5&&value.allocationFailuresLifetime==3&&value.entryRejectionsLifetime==4,"module-lifetime observation survives binding reset");
    expect(unbindRmDevice(&session)==NV_OK&&session.stop()==NV_OK&&!endpoint.resources,"all explicit host resources released");
    std::printf("{\"status\":\"passed\",\"cases\":%u,\"checks\":%u,\"actual_whole_services\":true,\"actual_whole_session\":true}\n",cases,checks);return 0;
}
