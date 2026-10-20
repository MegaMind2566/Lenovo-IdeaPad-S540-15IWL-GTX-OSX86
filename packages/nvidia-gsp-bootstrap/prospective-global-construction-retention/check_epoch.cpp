// SPDX-License-Identifier: MIT; actual full original global construction.
#include "S540NvidiaGspFirstTransaction.h"
#include "S540NvidiaGlobalRm.h"
#include "S540NvidiaGlobalRmHostRetention.h"
#include "S540NvidiaDarwinServices.h"
#include <cstdio>
#include <cstdlib>
#include <thread>
#include <unistd.h>
extern "C" {
extern unsigned s540GlobalEpochControlScenario,s540GlobalEpochControlCoreReturns;
extern NV_STATUS s540GlobalEpochControlHookStatus;
extern unsigned s540ConstructionControlCaptures,s540ConstructionControlGuards;
extern unsigned s540ConstructionControlMismatches;
NvBool s540ConstructionControlBytesMatch(void);
NV_STATUS s540GlobalEpochControlStartPort(void);
NvBool s540GlobalEpochControlPortLive(void);
}
static unsigned checks,failures;
static int owner;
static void expect(bool v,const char *why){++checks;if(!v){++failures;std::fprintf(stderr,"global epoch: %s\n",why);}}
int main(int argc,char **argv)
{
    if(argc!=2&&argc!=3)return 2;
    const unsigned scenario=static_cast<unsigned>(std::strtoul(argv[1],nullptr,10));
    if(scenario>9||(argc==3&&scenario!=6&&scenario!=7))return 2;
    const NvU64 ordinal=argc==3?std::strtoull(argv[2],nullptr,10):0;
    s540GlobalEpochControlScenario=scenario;
    S540NvidiaGlobalRmPlatformFacts facts={};facts.format=1;facts.known=S540_GLOBAL_FACT_ALL;
    facts.cpuCount=1;facts.cpuFrequencyHz=2000000000ULL;facts.osMajor=25;
    facts.osVersion=facts.osDate="explicit-global-epoch-cpu-fixture";
#if defined(__APPLE__)
    S540NvidiaDarwinServicesNative::setCpuFixture(0);
#else
    facts.cpuCount=static_cast<NvU32>(sysconf(_SC_NPROCESSORS_CONF));
#endif
    expect(s540GlobalRmHostInitialize(&facts)==NV_OK,"actual Host starts cold");
    S540FirstTxnHostIdentity identity={&owner,999},before={};
    expect(s540FirstTxnMasterIdentity(&identity)!=NV_OK&&identity.owner==&owner&&identity.generation==999,
        "unbound master query refuses without touching output");
    if(scenario==1){
        S540NvidiaGlobalRmResult unbound={};
        expect(s540GlobalRmInitialize(&unbound)!=NV_OK&&!s540GlobalEpochControlCoreReturns,
            "unbound global initialize executes no original core");
    }
    expect(s540FirstTxnGlobalOriginalReturned(NV_OK)!=NV_OK,
        "a completion without a genuine global claim is refused");
    expect(s540FirstTxnBeginOwner(&owner)==NV_OK,"BeginOwner precedes every original global allocation");
    expect(s540FirstTxnMasterIdentity(&before)==NV_OK&&before.owner==&owner&&before.generation,
        "true ordinary master pulls immutable owner generation before nv exists");
    if(scenario==2){
        NV_STATUS query=NV_OK,entry=NV_OK;S540FirstTxnHostIdentity foreign={&owner,999};
        std::thread thread([&]{S540NvidiaGlobalRmResult result={};
            query=s540FirstTxnMasterIdentity(&foreign);entry=s540GlobalRmInitialize(&result);});
        thread.join();
        expect(query!=NV_OK&&entry!=NV_OK&&foreign.owner==&owner&&foreign.generation==999,
            "actual foreign ordinary thread cannot pull master or enter and cannot modify output");
        expect(!s540GlobalEpochControlCoreReturns,"foreign refusal executes no original core");
    }
    if(scenario==3)S540NvidiaGlobalRmNative::failAllocationAt(1);
    if(scenario==4)s540GlobalRmRecordUnavailable(0);
    if(scenario==5)expect(s540GlobalEpochControlStartPort()==NV_OK,"real foreign portable epoch is created before global claim");
    if(scenario==6||(scenario==7&&ordinal))S540NvidiaGlobalRmNative::failAllocationAt(
        argc==3?std::strtoull(argv[2],nullptr,10):2);
    S540NvidiaGlobalRmResult result={};
    const NV_STATUS status=s540GlobalRmInitialize(&result);
    S540FirstTxnGlobalSnapshot epoch={};s540FirstTxnGlobalGetSnapshot(&epoch);
    S540NvidiaGlobalRmHostSnapshot host={};s540GlobalRmHostSnapshot(&host);
    S540GlobalRmHostRetentionSnapshot retention={};s540GlobalRmHostRetentionSnapshot(&retention);
    expect(epoch.owner==before.owner&&epoch.generation==before.generation&&!epoch.nv,
        "global transaction preserves exact original owner generation without attaching nv");
    if(scenario<3||scenario==9){
        expect(status==NV_OK&&result.initialized&&s540GlobalRmIsInitialized(),"actual full global epoch succeeds");
        expect(result.systemObject&&result.children&&result.presentChildren==15&&
            result.resourceServer&&result.memoryExportClient,"all actual original global result invariants hold");
        expect(epoch.state==S540_FIRST_GLOBAL_READY&&epoch.originalReturned&&epoch.validated&&
            !epoch.originalStatus&&!epoch.validationStatus&&!epoch.firstStatus,"real original return and postcore query complete cleanly");
        const NvU64 allocations=host.allocations;
        S540NvidiaGlobalRmResult duplicate={};
        expect(s540GlobalRmInitialize(&duplicate)!=NV_OK,"one-shot duplicate cannot execute original core again");
        s540GlobalRmShutdown(&result);s540GlobalRmHostSnapshot(&host);
        expect(s540GlobalRmIsInitialized()&&!result.cleanShutdown&&host.allocations==allocations&&
            s540GlobalEpochControlCoreReturns==1,"shutdown preserves every global and duplicate has no side effects");
        expect(!host.frees&&host.originalLiveAllocations==host.allocations&&
            retention.diagnosticRetiredAllocations&&retention.diagnosticRetiredBytes,
            "all real Host backing remains alive while temporary frees retire logically");
        if(scenario==9)expect(s540GlobalEpochControlHookStatus==NV_ERR_IN_USE,
            "duplicate global entry is rejected while actual original completion is pending");
    }else{
        expect(status!=NV_OK&&!result.initialized&&!s540GlobalRmIsInitialized(),"refused epoch never publishes initialized globals");
        expect(epoch.firstStatus!=NV_OK,"actual refusal stays sticky");
        if(scenario==3||scenario==6||(scenario==7&&ordinal)){
            expect(status==NV_ERR_NO_MEMORY&&epoch.firstStatus==NV_ERR_NO_MEMORY,
                "real Host allocation failure remains stronger than any original fallback");
            expect(epoch.originalReturned&&epoch.state==S540_FIRST_GLOBAL_RETAINED&&
                !epoch.validated&&s540GlobalEpochControlCoreReturns==1,"actual original outcome recorded once and retained without shutdown");
            if(scenario==7)expect(epoch.originalStatus==NV_OK&&s540GlobalEpochControlHookStatus!=NV_OK,
                "actual postcore TLS allocation fails after original success; statuses stay distinct");
            if(ordinal==154){
                S540FirstTxnGlobalConstructionRetention captured={};
                expect(s540FirstTxnGlobalGetConstructionRetention(&captured)==NV_OK&&captured.system&&
                    captured.owner==before.owner&&captured.generation==before.generation&&
                    captured.masterThread==epoch.masterThread&&captured.originalFailure==NV_ERR_NO_MEMORY,
                    "actual failed system is captured under the exact owner generation");
                expect(s540ConstructionControlCaptures==1&&s540ConstructionControlGuards==3&&
                    !s540ConstructionControlMismatches&&s540ConstructionControlBytesMatch(),
                    "both whole ancestor cleanup guards preserve every original system byte");
                expect(epoch.originalStatus==NV_ERR_NO_MEMORY,"original constructor error returns unchanged");
            }
            if(scenario==3)expect(epoch.originalStatus==NV_ERR_NO_MEMORY,"first true original allocation failure preserves original status");
        }else if(scenario==4){
            expect(epoch.state==S540_FIRST_GLOBAL_UNUSED&&!epoch.originalReturned&&
                !s540GlobalEpochControlCoreReturns,"historical real service refusal prevents any global claim or core execution");
        }else if(scenario==5){
            expect(epoch.state==S540_FIRST_GLOBAL_RETAINED&&!epoch.originalReturned&&
                !s540GlobalEpochControlCoreReturns&&s540GlobalEpochControlPortLive(),
                "foreign portable runtime is preserved; pre-core refusal never destroys it");
        }else{
            expect(s540GlobalEpochControlHookStatus==NV_OK&&status==NV_ERR_INVALID_LOCK_STATE&&
                epoch.originalStatus==NV_OK&&epoch.validationStatus==NV_ERR_INVALID_LOCK_STATE,
                "genuine postcore API or allocation-only ownership prevents publication");
            expect(epoch.originalReturned&&!epoch.validated&&epoch.state==S540_FIRST_GLOBAL_RETAINED,
                "postcore ownership refusal preserves actual successful original outcome separately");
        }
    }
    expect(!host.frees,"no physical Host release occurs on any outcome");
    if(!ordinal||ordinal!=154)expect(!s540ConstructionControlCaptures&&!s540ConstructionControlGuards,
        "constructor retention does not impersonate a failure boundary on other cases");
    expect(!host.invalidFrees,"no actual Host invalid free occurs");
    if(epoch.firstStatus){
        identity={&owner,999};
        expect(s540FirstTxnMasterIdentity(&identity)==epoch.firstStatus&&
            identity.owner==&owner&&identity.generation==999,
            "genuine failed master sees the actual sticky error with unchanged output");
    }
    expect(!s540GlobalRmHostShutdown(),"permanent owner prevents Host shutdown on every outcome");
    std::printf("{\"allocation_ordinal\":%llu,\"scenario\":%u,\"checks\":%u,\"failures\":%u,\"status\":%u,"
        "\"epoch_state\":%u,\"record_status\":%u,\"original_status\":%u,\"validation_status\":%u,"
        "\"original_returned\":%s,\"validated\":%s,\"original_core_returns\":%u,"
        "\"global_initialized\":%s,\"original_live_allocations\":%u,\"physical_frees\":%llu,"
        "\"diagnostic_retired_allocations\":%llu,\"kernel_execution\":false,\"gpu_access\":false}\n",
        static_cast<unsigned long long>(ordinal),scenario,checks,failures,status,epoch.state,epoch.firstStatus,epoch.originalStatus,
        epoch.validationStatus,epoch.originalReturned?"true":"false",epoch.validated?"true":"false",
        s540GlobalEpochControlCoreReturns,s540GlobalRmIsInitialized()?"true":"false",host.originalLiveAllocations,
        static_cast<unsigned long long>(host.frees),static_cast<unsigned long long>(retention.diagnosticRetiredAllocations));
    std::fflush(stdout);_Exit(failures?1:0);
}
