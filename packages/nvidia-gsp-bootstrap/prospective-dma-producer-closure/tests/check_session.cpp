/* SPDX-License-Identifier: MIT
 * Complete actual Session implementation + genuine PM cancellation source.
 * Provider PCI I/O and platform/thread observations are explicit fixtures. */
#include "S540NvidiaDeviceTransport.hpp"
#include "S540NvidiaDmaProducer.h"
#include "S540NvidiaDarwinServices.h"
#include <cstdio>
#include <cstdlib>
#include <initializer_list>
using namespace S540NvidiaDeviceTransport;
static NvU64 tid=1, now=100;
static int nv, other;
static S540GspCancellationToken token;
static NvU32 checks,failures;
static void expect(bool v,const char *why){++checks;if(!v){++failures;std::fprintf(stderr,"session: %s\n",why);}}
extern "C" NV_STATUS NV_API_CALL s540Darwin_os_get_current_thread(NvU64 *out){*out=tid;return NV_OK;}
extern "C" NvBool NV_API_CALL s540Darwin_os_semaphore_may_sleep(void){return NV_TRUE;}
extern "C" NvU64 NV_API_CALL s540Darwin_os_get_monotonic_time_ns(void){return now;}
extern "C" NV_STATUS NV_API_CALL s540Darwin_os_delay(NvU32){return NV_OK;}
extern "C" NV_STATUS s540FirstTxnIrqReadEnteredScope(const void *,NvU32,NvU32 *){return NV_ERR_INVALID_STATE;}
struct Platform {bool live=false,revoke=false,foreign=false;NvU32 writes=0;NV_STATUS status=NV_OK;};
static Detail::Backend makeBackend(Platform &p){
    Detail::Backend b{};b.context=&p;
    b.ordinary=[](void *){return true;};
    b.start=[](void *p,Snapshot &s)->NV_STATUS{static_cast<Platform *>(p)->live=true;s={};s.identity=s.providerOwned=s.memoryDecode=s.powerD0=s.barMapped=true;s.barBytes=0x1000000;return NV_OK;};
    b.stop=[](void *p)->NV_STATUS{static_cast<Platform *>(p)->live=false;return NV_OK;};
    b.live=[](void *p){return static_cast<Platform *>(p)->live;};
    b.readIdentification=[](void *,NvU32,NvU32 &)->NV_STATUS{return NV_ERR_NOT_SUPPORTED;};
    b.allocate=[](void *,NvU32,bool,NvU32,void **,NvU8 **)->NV_STATUS{return NV_ERR_NOT_SUPPORTED;};
    b.pageAddress=[](void *,void *,NvU32,bool,NvU64 &)->NV_STATUS{return NV_ERR_NOT_SUPPORTED;};
    b.mapDma=[](void *,void *,NvU32)->NV_STATUS{return NV_ERR_NOT_SUPPORTED;};
    b.unmapDma=[](void *,void *)->NV_STATUS{return NV_ERR_NOT_SUPPORTED;};
    b.releaseAllocation=[](void *,void *)->NV_STATUS{return NV_ERR_NOT_SUPPORTED;};
    b.installInterrupt=[](void *,const InterruptContract &)->NV_STATUS{return NV_ERR_NOT_SUPPORTED;};
    b.armInterrupt=[](void *)->NV_STATUS{return NV_ERR_NOT_SUPPORTED;};
    b.stopInterrupt=[](void *)->NV_STATUS{return NV_OK;};
    b.configWrite=[](void *opaque,NvU32 offset,NvU32 width,NvU32 value)->NV_STATUS{
        auto &p=*static_cast<Platform *>(opaque);++p.writes;
        if(s540DmaConfigWriteEnablesBusMaster(offset,width,value)&&token){
            S540GspCancellationCommitSnapshot facts{};
            expect(s540GspCancellationCommitReadState(&nv,&facts)==NV_OK&&facts.inFlight,"actual endpoint retains commit");
        }
        if(p.revoke)expect(s540GspCancellationRevoke(token)==NV_OK,"actual endpoint-time revoke");
        if(p.foreign)tid=2;
        return p.status;
    };
    return b;
}
int main(int argc,char **argv){
    int scenario=argc>1?std::atoi(argv[1]):0;
    Platform p;Session session;
    expect(session.start(makeBackend(p))==NV_OK,"actual Session starts");
    if(scenario==0){
        expect(session.writeConfig(4,2,6)==NV_OK&&p.writes==1,"unbound startup semantics preserved");
        expect(session.stop()==NV_OK,"preowner stops normally");
    }else{
        expect(s540GspCancellationBind(&nv,&token)==NV_OK,"real exact cancellation bind");
        expect(s540GspCancellationBegin(token)==NV_OK,"real current operation");
        expect(session.setRmBinding(true)==NV_OK,"actual RM conservative binding");
        if(scenario!=1)expect(session.beginHardwareDmaLifetime(scenario==2?&other:&nv)==NV_OK,"actual conservative lifetime hold");
        if(scenario==1||scenario==2){
            expect(session.writeConfig(4,2,6)!=NV_OK&&!p.writes,"hold or rmBound is never identity authority");
        }else if(scenario==3){
            for(NvU32 width: {1U,2U,4U})expect(session.writeConfig(4,width,6)==NV_OK,"actual supported enable accepted");
            expect(s540GspCancellationRevoke(token)==NV_OK,"actual revoke before next write");
            NvU32 before=p.writes;
            for(NvU32 width: {1U,2U,4U})expect(session.writeConfig(4,width,6)!=NV_OK&&p.writes==before,"post-revoke enable has no endpoint");
            expect(session.writeConfig(4,2,2)==NV_OK&&p.writes==before+1,"BME clear remains genuine cleanup operation");
        }else if(scenario==4){
            p.revoke=true;
            expect(session.writeConfig(4,2,6)==NV_OK&&p.writes==1,"accepted-before-revoke write returns actual result");
            S540GspCancellationCommitSnapshot facts{};
            expect(s540GspCancellationCommitReadState(&nv,&facts)==NV_OK&&facts.revoked&&!facts.inFlight,"reservation ends only after endpoint return");
            expect(session.writeConfig(4,2,6)!=NV_OK&&p.writes==1,"next enable is closed");
        }else if(scenario==5||scenario==6){
            p.status=NV_ERR_OPERATING_SYSTEM;p.foreign=scenario==6;
            expect(session.writeConfig(4,2,6)==NV_ERR_OPERATING_SYSTEM,"actual endpoint first error preserved, including double failure");
            tid=1;S540GspCancellationCommitSnapshot facts{};
            expect(s540GspCancellationCommitReadState(&nv,&facts)==NV_OK,"actual post-error reservation observation");
            expect(bool(facts.inFlight)==(scenario==6),"failed completion retains reservation; endpoint error alone does not");
        }else if(scenario==7){
            NvU32 before=p.writes;
            expect(session.writeConfig(3,2,0x400)!=NV_OK&&p.writes==before,"misaligned command overlap refuses before endpoint");
            expect(session.writeConfig(4095,4,6)!=NV_OK&&p.writes==before,"overflow span refuses");
            expect(session.writeConfig(4,3,6)!=NV_OK&&p.writes==before,"unknown width refuses");
        }
        expect(session.stop()!=NV_OK&&session.hardwareDmaLifetimeHeld()==(scenario!=1),"CPU guard never authorizes release or hardware stop");
    }
    if(scenario==0)for(NvU32 offset=0;offset<17;++offset)for(NvU32 width: {1U,2U,4U})for(NvU32 bit=0;bit<32;++bit){
        NvU32 value=1U<<bit;bool expected=false;
        for(NvU32 lane=0;lane<width;++lane)if(offset+lane==4&&((value>>(lane*8))&4U))expected=true;
        expect(bool(s540DmaConfigWriteEnablesBusMaster(offset,width,value))==expected,"little endian command bit classifier");
    }
    std::printf("{\"scenario\":%d,\"checks\":%u,\"failures\":%u,\"writes\":%u}\n",scenario,checks,failures,p.writes);
    return failures?1:0;
}
