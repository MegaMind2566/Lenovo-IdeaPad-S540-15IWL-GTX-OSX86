// CPU fixture. Method fragments below are extracted from the actual input or
// transformed Owner source. Every external dependency is deliberately fake.
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <string>
#include <vector>
#include "@HEADER@"
#include "@STATUS@"
#define KERNEL 1
enum { S540_GLOBAL_FACT_NOTEBOOK=1, S540_GLOBAL_FACT_BATTERY=2,
 S540_GLOBAL_FACT_EFI=4, S540_GLOBAL_FACT_VGPU_HYPERVISOR=8,
 S540_GLOBAL_FACT_NVSWITCH=16, S540_GLOBAL_FACT_S0IX=32,
 S540_GLOBAL_FACT_CPU=64, S540_GLOBAL_FACT_OS_VERSION=128,
 S540_GLOBAL_FACT_ALL=255 };
static void require(bool value) { if (!value) std::abort(); }
struct Fixture {
 NvU32 fail=0, hostKnown=255, deviceBits=127, cleanupCalls=0, deleted=0;
 NV_STATUS failure=NV_ERR_NOT_READY, cleanup=NV_OK;
 bool ordinary=true, invalidHost=false, invalidDevice=false, requireDma=true;
 std::vector<NvU32> calls;
} fixture;
static NV_STATUS step(NvU32 stage) {
 fixture.calls.push_back(stage); return fixture.fail==stage ? fixture.failure : NV_STATUS(NV_OK);
}
struct IOPCIDevice {}; struct IOService {};
struct nv_state_t {}; struct nv_dma_device_t {};
struct S540GspContext { nv_state_t nv; nv_dma_device_t dma; };
struct S540GspContextDetacher { void *owner; NV_STATUS (*detach)(void *,void *,void *); };
using S540GspCancellationToken=NvU64;
struct S540NvidiaGlobalRmPlatformFacts { NvU32 known=0; const char *osVersion=nullptr,*osDate=nullptr; };
struct S540GspDeviceFacts {
 NvU32 segment=0; void *pciHandle=nullptr;
 bool segmentKnown=false,pciConfigurationRead=false,barsVerified=false,poweredD0=false;
 bool intelConsoleVerified=false,nvidiaConsoleExcluded=false,noCoherentGpuMemoryProfile=false;
};
static NV_STATUS s540Darwin_os_acquire_mutex(void *) { return NV_OK; }
static NV_STATUS s540Darwin_os_release_mutex(void *) { return NV_OK; }
static NV_STATUS s540Darwin_os_alloc_mutex(void **out) {
 const auto status=step(S540_PREP_SNAPSHOT_MUTEX); *out=status==NV_OK?reinterpret_cast<void *>(1):nullptr; return status;
}
static void s540Darwin_os_free_mutex(void *) {}
static bool ordinary(NvU64 &thread) { thread=1; return fixture.ordinary; }
static void *allocateOwner(NvU64 bytes) { return step(S540_PREP_ALLOCATE_OWNER)==NV_OK?std::malloc(bytes):nullptr; }
static void releaseOwner(void *p,NvU64) { std::free(p); }
static bool copyText(char *out,NvU32 capacity,const char *in) {
 if (fixture.calls.empty() || fixture.calls.back()!=S540_PREP_HOST_STRINGS) fixture.calls.push_back(S540_PREP_HOST_STRINGS);
 if (fixture.fail==S540_PREP_HOST_STRINGS || !in || std::strlen(in)>=capacity) return false;
 std::strcpy(out,in); return true;
}
static void copyBytes(void *out,const void *in,NvU64 bytes) {
 fixture.calls.push_back(S540_PREP_COPY_FIRMWARE);std::memcpy(out,in,bytes);
}
namespace S540NvidiaFirmwareAssets {
 struct Result { bool value; bool passed() const { return value; } };
 static Result verifyPair(const void *,NvU64,const void *,NvU64) { return {step(S540_PREP_VERIFY_FIRMWARE)==NV_OK}; }
}
namespace S540NvidiaGspPower {
 struct Revocation { void *owner; NV_STATUS (*requestStop)(void *); };
 struct Lease {
  NV_STATUS start(IOPCIDevice *,const Revocation &) { return step(S540_PREP_POWER_START); }
  NV_STATUS coupleCancellation(const void *,NvU64) { return step(S540_PREP_POWER_CANCELLATION); }
  struct Snapshot { bool revoked; NvU64 revokedAtNs; };
  Snapshot snapshot() const { step(S540_PREP_POWER_REVOKE_CHECK); return {fixture.fail==S540_PREP_POWER_REVOKE_CHECK,123}; }
  NV_STATUS status() const { return step(S540_PREP_FINAL_POWER); }
  S540PreparationPowerObservation preparationObservation() const {
   S540PreparationPowerObservation out{}; out.format=1;out.bytes=sizeof(out);
   out.stage=S540_PREP_POWER_WAIT_READY;out.observedMask=S540_PREP_PM_OBS_READY;
   if (fixture.fail==S540_PREP_POWER_START) {
    out.firstFailureStage=out.stage;out.firstFailureStatus=fixture.failure;
   } else out.flags=S540_PREP_PM_OBS_READY;
   return out;
  }
 };
}
namespace S540NvidiaGspPlatform {
 struct Context {
  NV_STATUS initialize(IOPCIDevice *) { return step(S540_PREP_PLATFORM_INITIALIZE); }
  NV_STATUS collect(S540NvidiaGlobalRmPlatformFacts *out) {
   auto status=step(S540_PREP_HOST_FACTS); if(fixture.invalidHost)return NV_ERR_INVALID_STATE;
   out->known=fixture.hostKnown;out->osVersion="25.6.0";out->osDate="date";return status;
  }
  NV_STATUS collectDeviceFacts(S540GspDeviceFacts *out) {
   auto status=step(S540_PREP_DEVICE_FACTS);if(fixture.invalidDevice)return NV_ERR_INVALID_STATE;
   out->segmentKnown=fixture.deviceBits&1;out->pciConfigurationRead=fixture.deviceBits&2;
   out->barsVerified=fixture.deviceBits&4;out->poweredD0=fixture.deviceBits&8;
   out->intelConsoleVerified=fixture.deviceBits&16;out->nvidiaConsoleExcluded=fixture.deviceBits&32;
   out->noCoherentGpuMemoryProfile=fixture.deviceBits&64;return status;
  }
  NV_STATUS bindState(void *) { return step(S540_PREP_PLATFORM_BIND); }
 };
}
namespace S540NvidiaDeviceTransport {
 namespace Detail { struct Backend {}; }
 struct Session {
  NV_STATUS start(IOPCIDevice *,IOService *) { return step(S540_PREP_TRANSPORT_START); }
  NV_STATUS setPciSegment(NvU32) { return step(S540_PREP_PCI_SEGMENT); }
  NV_STATUS requiresDmaRemap(NvBool &required) { required=fixture.requireDma;return step(S540_PREP_DMA_REMAP); }
  void *pciHandle() const { return reinterpret_cast<void *>(2); }
 };
 static NV_STATUS bindRmDevice(Session *,void *,void *) { return step(S540_PREP_RM_BIND); }
 static NV_STATUS queryRmDmaRemap(void *,NvBool &required) { required=fixture.requireDma;return step(S540_PREP_RM_DMA_REMAP); }
}
static NV_STATUS s540GlobalRmHostInitialize(const S540NvidiaGlobalRmPlatformFacts *) { return step(S540_PREP_HOST_INITIALIZE); }
static unsigned allocationNumber=0;
static void *s540GlobalRmHostAllocate(NvU64 bytes) {
 const auto stage=allocationNumber++?S540_PREP_ALLOCATE_UCODES:S540_PREP_ALLOCATE_GSP;
 return step(stage)==NV_OK?std::malloc(bytes):nullptr;
}
static NV_STATUS s540GspContextCreate(const S540GspDeviceFacts *,S540GspContext **out) {
 const auto status=step(S540_PREP_CONTEXT_CREATE); if(status==NV_OK)*out=new S540GspContext;return status;
}
static NV_STATUS s540GspContextSetDetacher(S540GspContext *,const S540GspContextDetacher *) { return step(S540_PREP_CONTEXT_DETACHER); }
static void *s540GspContextState(S540GspContext *context) { return &context->nv; }
static void *s540GspContextDmaDevice(S540GspContext *context) { return &context->dma; }
static NV_STATUS s540GspCancellationBind(void *,NvU64 *token) { *token=1;return step(S540_PREP_CANCELLATION_BIND); }
static NV_STATUS s540GspCancellationRevokeAt(NvU64,NvU64) { return NV_OK; }
static NV_STATUS s540GspTimersBind(void *) { return step(S540_PREP_TIMERS_BIND); }
namespace S540NvidiaGspFirmware {
 struct Store { NV_STATUS initialize(void *,NvU64,void *,NvU64,void *,NvU64) { return step(S540_PREP_FIRMWARE_STORE); } };
 static NV_STATUS bind(Store *) { return step(S540_PREP_FIRMWARE_BIND); }
}
struct S540BootstrapPlacement { void *address; };
void *operator new(decltype(sizeof(0)),S540BootstrapPlacement p) noexcept { return p.address; }
namespace S540NvidiaGspBootstrap {
constexpr NvU64 kGspBytes=8,kUcodesBytes=8;
enum { Prepare=1,Stop=3 };
struct Images { const void *gsp=nullptr;NvU64 gspBytes=0;const void *ucodes=nullptr;NvU64 ucodesBytes=0; };
struct Snapshot {
 NvU32 format=1;S540PreparationObservation preparation{};NV_STATUS preparationStatus=0;
 bool ownsResources=false,prepared=false,preparationCompleted=false,cleanupComplete=false;
 bool firmwareCopied=false,dmaPolicyAdmitted=false,workerActive=false;
};
@HELPERS@
class Owner {
public:
 struct Impl;
 Impl *impl_=nullptr;Snapshot state_{};
 NV_STATUS prepareCommon(IOPCIDevice *,IOService *,const Images &,const S540NvidiaDeviceTransport::Detail::Backend *);
 NV_STATUS stop();
 Snapshot snapshot() const;
};
struct Dispatcher {
 NV_STATUS (*action)(void *,NvU32)=nullptr;void *context=nullptr;
 NV_STATUS start(NV_STATUS(*callback)(void *,NvU32),void *owner) {
  action=callback;context=owner;return step(S540_PREP_DISPATCHER_START);
 }
 NV_STATUS invoke(NvU32 command) {
  if(command==Prepare){const auto status=step(S540_PREP_DISPATCH_PREPARE);if(status!=NV_OK)return status;}
  return action(context,command);
 }
 NV_STATUS stop() { fixture.calls.push_back(102);return NV_OK; }
};
struct Owner::Impl {
 Snapshot state{},published{};S540PreparationObservation preparationDispatchFallback{};
 Dispatcher dispatcher;S540NvidiaDeviceTransport::Session transport;S540NvidiaGspPlatform::Context platform;
 S540NvidiaGspPower::Lease power;S540NvidiaGspFirmware::Store firmware;
 S540GspContext *context=nullptr;void *snapshotGuard=nullptr,*gsp=nullptr,*ucodes=nullptr;
 NvU64 thread=1,cancellationToken=0;char osVersion[128]{},osDate[128]{};
 bool host=false,platformBound=false,deviceBound=false,firmwareBound=false,timersBound=false,nativeFixture=false;
 IOPCIDevice *provider=nullptr;IOService *service=nullptr;Images images{};
 const S540NvidiaDeviceTransport::Detail::Backend *nativeBackend=nullptr;
 ~Impl() { ++fixture.deleted;std::free(gsp);std::free(ucodes);delete context; }
 static NV_STATUS postRevocation(void *) { return NV_OK; }
 static NV_STATUS detach(void *,void *,void *) { return NV_OK; }
 static NV_STATUS action(void *opaque,NvU32 command) {
  auto *self=static_cast<Impl *>(opaque);
  const auto status=command==Prepare?self->prepare():self->stop();self->published=self->state;return status;
 }
 NV_STATUS stop() { ++fixture.cleanupCalls;fixture.calls.push_back(101);state.cleanupComplete=fixture.cleanup==NV_OK;return fixture.cleanup; }
 @DISPATCH_RETURN@
 @READ@
 @FAILED@
 @PREPARE@
};
@COMMON@
@STOP@
Snapshot Owner::snapshot() const { return impl_?impl_->read():state_; }
}
static void outputCase(unsigned number,NV_STATUS status,const S540NvidiaGspBootstrap::Snapshot &snapshot) {
 std::cout<<number<<":"<<status<<":"<<fixture.cleanupCalls<<":"<<fixture.deleted<<":";
 for(auto call:fixture.calls)std::cout<<call<<",";
 std::cout<<"\n";
 (void)snapshot;
}
int main() {
 using namespace S540NvidiaGspBootstrap;
 const unsigned failures[]={0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,27,28,29,30};
 unsigned caseNumber=0,assertions=0;
 for(unsigned failedStage:failures) {
  fixture=Fixture{};fixture.fail=failedStage;fixture.ordinary=failedStage!=S540_PREP_VALIDATE;
  if(failedStage==S540_PREP_HOST_FACTS)fixture.hostKnown=255U&~NvU32(S540_GLOBAL_FACT_CPU);
  if(failedStage==S540_PREP_DEVICE_FACTS)fixture.deviceBits=127U&~NvU32(S540_PREP_DEVICE_D0);
  allocationNumber=0;Owner owner;IOPCIDevice provider;IOService service;const NvU64 bytes=0;
  Images images{&bytes,kGspBytes,&bytes,kUcodesBytes};
  const auto status=owner.prepareCommon(&provider,&service,images,nullptr);
  if(owner.impl_)require(owner.stop()==NV_OK);
  const auto observed=owner.snapshot();
#if OBSERVATIONS
  require(observed.preparation.format==1 && observed.preparation.bytes==104);++assertions;
  if(!failedStage) {
   require(status==NV_OK && observed.preparation.stage==S540_PREP_COMPLETE && observed.preparation.lastCompleted==S540_PREP_COMPLETE);
   require(!(observed.preparation.observedMask&S540_PREP_OBS_FIRST_FAILURE));assertions+=2;
  } else {
   require(observed.preparation.firstFailureStage==failedStage && observed.preparation.firstFailureStatus!=NV_OK);
   require(observed.preparation.observedMask&S540_PREP_OBS_FIRST_FAILURE);
   require(observed.preparation.lastCompleted<failedStage);assertions+=3;
  }
  if(failedStage==S540_PREP_HOST_FACTS) {
   require(observed.preparation.firstFailureStatus==85 && observed.preparation.hostMissing==S540_GLOBAL_FACT_CPU);
   require(observed.preparation.observedMask&S540_PREP_OBS_HOST_FACTS);assertions+=2;
  }
  if(failedStage==S540_PREP_DEVICE_FACTS) {
   require(observed.preparation.firstFailureStatus==85 && observed.preparation.deviceObserved==127);
   require(!(observed.preparation.devicePredicates&S540_PREP_DEVICE_D0));assertions+=2;
  }
#endif
  outputCase(caseNumber++,status,observed);
 }
 // A failed cleanup changes the original facade return, but cannot erase the
 // first preparation refusal. A later real stop copies it before deletion.
 fixture=Fixture{};fixture.fail=S540_PREP_HOST_FACTS;fixture.cleanup=NV_ERR_BUSY_RETRY;allocationNumber=0;
 Owner owner;IOPCIDevice provider;IOService service;const NvU64 bytes=0;Images images{&bytes,8,&bytes,8};
 const auto status=owner.prepareCommon(&provider,&service,images,nullptr);
 require(status==NV_ERR_BUSY_RETRY && owner.impl_ && fixture.deleted==0);
 fixture.cleanup=NV_OK;require(owner.stop()==NV_OK);const auto observed=owner.snapshot();
#if OBSERVATIONS
 require(observed.preparation.firstFailureStage==S540_PREP_HOST_FACTS && observed.preparation.firstFailureStatus==85);
 require(fixture.deleted==1);assertions+=2;
#endif
 outputCase(caseNumber++,status,observed);
 // Refused collection before producing local facts cannot make zero-valued
 // predicates appear observed or successful.
 for(bool device:{false,true}) {
  fixture=Fixture{};fixture.invalidHost=!device;fixture.invalidDevice=device;allocationNumber=0;
  Owner invalid;const auto rejected=invalid.prepareCommon(&provider,&service,images,nullptr);
  if(invalid.impl_)require(invalid.stop()==NV_OK);
  const auto snap=invalid.snapshot();
#if OBSERVATIONS
  require(!(snap.preparation.observedMask&(device?S540_PREP_OBS_DEVICE_FACTS:S540_PREP_OBS_HOST_FACTS)));
  require(snap.preparation.firstFailureStatus==NV_ERR_INVALID_STATE);assertions+=2;
#endif
  outputCase(caseNumber++,rejected,snap);
 }
 std::cerr<<"assertions="<<assertions<<" cases="<<caseNumber<<"\n";
}
