// SPDX-License-Identifier: MIT
#include "S540ExperimentalTargetKernel.hpp"
#include "../prospective-loader/roots/S540NvidiaGspOriginalRoots.h"
#include "S540ExperimentalRuntime.h"
#include "S540NvidiaRetainedStop.h"
#include <IOKit/IOLib.h>
#include <IOKit/pci/IOPCIDevice.h>
#include <libkern/c++/OSIterator.h>
#include <kern/task.h>
struct S540ExperimentalPlacement { void *address; };
void *operator new(decltype(sizeof(0)),S540ExperimentalPlacement place) noexcept { return place.address; }
namespace {
IOLock *guard = nullptr;
S540ExperimentalState state{};
S540ExperimentalTargetControl *activeControl = nullptr;
NvU32 services = 0, clients = 0, cancellationPublishers = 0;
constexpr NvU32 maximumClients=16;
bool busy = false, cancellationReady = false;
bool privileged(task_t task) {
    return task && IOUserClient::clientHasPrivilege(task,kIOClientPrivilegeAdministrator) == kIOReturnSuccess;
}
bool callable() {
    // Retained state remains inspectable and accepts another real STOP.
    // RequestBegin alone enforces the one-shot/stop entry refusal.
    return state.snapshot.moduleEntryAccepted && state.snapshot.controlServiceStarted;
}
IOReturn translate(NV_STATUS status) {
    if (status == NV_OK) return kIOReturnSuccess;
    if (status == NV_ERR_INVALID_ARGUMENT) return kIOReturnBadArgument;
    if (status == NV_ERR_INSUFFICIENT_PERMISSIONS) return kIOReturnNotPrivileged;
    if (status == NV_ERR_STATE_IN_USE || status == NV_ERR_IN_USE) return kIOReturnExclusiveAccess;
    if (status == NV_ERR_BUSY_RETRY) return kIOReturnBusy;
    return kIOReturnError;
}
IOPCIDevice *copyTarget() {
    OSDictionary *matching = IOService::serviceMatching("IOPCIDevice");
    if (!matching) return nullptr;
    OSIterator *iterator = IOService::getMatchingServices(matching);
    matching->release();
    if (!iterator) return nullptr;
    IOPCIDevice *found = nullptr;
    bool valid = true, exhausted = false;
    for (NvU32 count = 0; count < 1024; ++count) {
        if (!iterator->isValid()) { valid = false; break; }
        OSObject *object = iterator->getNextObject();
        if (!object) { exhausted = true; break; }
        IOPCIDevice *device = OSDynamicCast(IOPCIDevice,object);
        if (!device || device->isInactive()) continue;
        if (device->configRead32(0x00) == 0x1f9110deU &&
            device->configRead32(0x08) == 0x030000a1U &&
            device->configRead32(0x2c) == 0x380617aaU) {
            if (found) { valid = false; break; }
            device->retain(); found = device;
        }
    }
    valid = valid && exhausted && iterator->isValid() && (!found || !found->isInactive());
    iterator->release();
    if (!valid && found) { found->release(); found = nullptr; }
    return found;
}
bool stopPending() {
    IOLockLock(guard); bool pending=state.snapshot.stopRequested!=0; IOLockUnlock(guard);
    return pending;
}
void closeCancellationPublication() {
    IOLockLock(guard);
    cancellationReady=false;
    while (cancellationPublishers) IOLockSleep(guard,&cancellationPublishers,THREAD_UNINT);
    IOLockUnlock(guard);
}
}
OSDefineMetaClassAndStructors(S540ExperimentalTargetControl,IOService);
OSDefineMetaClassAndStructors(S540ExperimentalTargetClient,IOUserClient);

extern "C" kern_return_t s540ExperimentalModuleStartBackend(kmod_info_t *info) {
    if (!info || !info->address || !info->size || guard || state.snapshot.format ||
        s540ProspectiveRetainedRootCount()!=25 || !s540ProspectiveRetainedRootsPresent()) return KERN_FAILURE;
    S540ExperimentalNativeProfile profile{};
    const auto *identity=s540ExperimentalGetBuildIdentity();
    if (!identity || identity->format!=1 || identity->bytes!=sizeof(*identity) ||
        s540RuntimeReadCompiledProfile(&profile)!=NV_OK) return KERN_FAILURE;
    IOLock *created=IOLockAlloc();
    if (!created) return KERN_RESOURCE_SHORTAGE;
    if (s540ExperimentalModuleEnter(&state)!=NV_OK) { IOLockFree(created); return KERN_FAILURE; }
    state.snapshot.nativeRequiredKernelStackBytes=profile.workerStackBytes;
    state.snapshot.nativeRequiredIrqStackBytes=profile.irqStackBytes;
    for (NvU32 i=0;i<32;++i) {
        state.snapshot.sourceSha256[i]=identity->sourceSha256[i];
        state.snapshot.policySha256[i]=identity->policySha256[i];
        state.snapshot.nativeCodeContractSha256[i]=profile.codeContractSha256[i];
    }
    guard=created;
    // Module load has no PCI lookup, PM registration, original entry or worker.
    return KERN_SUCCESS;
}
extern "C" kern_return_t s540ExperimentalModuleStopBackend(void) {
    if (!guard) return KERN_SUCCESS;
    IOLockLock(guard);
    S540ExperimentalTargetControl *control=activeControl;
    if (control) control->retain();
    IOLockUnlock(guard);
    // Retention never skips the actual stop request/attempt.
    if (control) { (void)control->requestStop(); control->release(); }
    IOLockLock(guard);
    const bool refuse=busy || cancellationPublishers || state.snapshot.requestConsumed || services || clients ||
        S540ExperimentalTargetControl::metaClass->getInstanceCount() ||
        S540ExperimentalTargetClient::metaClass->getInstanceCount();
    IOLockUnlock(guard);
    if (refuse) return KERN_FAILURE;
    IOLock *released=guard; guard=nullptr; IOLockFree(released);
    return KERN_SUCCESS;
}
bool S540ExperimentalTargetControl::init(OSDictionary *properties) {
    if (!IOService::init(properties) || !guard) return false;
    IOLockLock(guard);
    const bool allowed=state.snapshot.phase==S540_EXPERIMENTAL_MODULE_ENTERED &&
        state.snapshot.moduleEntryAccepted && !state.snapshot.stopRequested && !services;
    if (allowed) { ++services; counted=true; }
    IOLockUnlock(guard); return allowed;
}
void S540ExperimentalTargetControl::free() {
    // A run consumes a permanent real retain before publishing an Owner.
    // Its facade/provider/module may not be destroyed until reboot.
    if (counted && guard) { IOLockLock(guard); --services; counted=false; IOLockUnlock(guard); }
    IOService::free();
}
bool S540ExperimentalTargetControl::start(IOService *provider) {
    if (!guard || !counted || provider!=IOService::getResourceService() || !IOService::start(provider)) return false;
    IOLockLock(guard);
    NV_STATUS status=s540ExperimentalServiceStart(&state,getRegistryEntryID());
    if (status==NV_OK) { activeControl=this; retain(); }
    IOLockUnlock(guard);
    if (status!=NV_OK) { IOService::stop(provider); return false; }
    registerService(); return true;
}
void S540ExperimentalTargetControl::stop(IOService *provider) {
    (void)requestStop();
    bool drop=false;
    if (guard) {
        IOLockLock(guard); s540ExperimentalServiceGone(&state);
        if (activeControl==this) { activeControl=nullptr; drop=true; }
        IOLockUnlock(guard);
    }
    IOService::stop(provider);
    if (drop) release();
}
IOReturn S540ExperimentalTargetControl::newUserClient(task_t task,void *security,UInt32 type,
    OSDictionary *properties,IOUserClient **handler) {
    if (handler) *handler=nullptr;
    if (!handler || type!=S540_EXPERIMENTAL_CONNECTION_TYPE) return kIOReturnBadArgument;
    if (!privileged(task)) return kIOReturnNotPrivileged;
    if (!guard) return kIOReturnNotReady;
    IOLockLock(guard); bool allowed=callable() && clients<maximumClients; IOLockUnlock(guard);
    if (!allowed) return kIOReturnNotReady;
    auto *client=new S540ExperimentalTargetClient;
    if (!client) return kIOReturnNoMemory;
    if (!client->initWithTask(task,security,type,properties)) { client->release(); return kIOReturnError; }
    if (!client->attach(this)) { client->release(); return kIOReturnError; }
    if (!client->start(this)) { client->detach(this); client->release(); return kIOReturnError; }
    *handler=client; return kIOReturnSuccess;
}
void S540ExperimentalTargetControl::publishOwnerObservation() {
    if (!owner) return;
    const auto observed=owner->snapshot();
    const auto runtime=owner->runtimeSnapshot();
    const auto stopped=owner->retainedStopSnapshot();
    IOLockLock(guard);
    state.snapshot.globalInitialized=observed.globalInitialized;
    state.snapshot.adapterInitialized=observed.adapterInitialized;
    state.snapshot.firmwareLoaded=observed.firmwareLoaded;
    state.snapshot.interruptInstalled=observed.interruptInstalled;
    state.snapshot.interruptArmed=observed.interruptArmed;
    state.snapshot.powerRevoked=observed.powerRevoked;
    state.snapshot.cancellationRevoked=observed.cancellationRevoked;
    state.snapshot.powerAcknowledged=observed.powerAcknowledged;
    state.snapshot.runtimeObservationStatus=runtime.snapshotStatus;
    state.snapshot.originalEntryObserved=runtime.originalEntered;
    state.snapshot.stopObservationStatus=stopped.snapshotStatus;
    auto &wire=state.snapshot.retainedStop;
    wire.format=1;wire.bytes=sizeof(wire);
#define S540_COPY_STOP_FIELD(name) wire.name=stopped.name
    S540_COPY_STOP_FIELD(attempts);
    S540_COPY_STOP_FIELD(status);S540_COPY_STOP_FIELD(firstError);S540_COPY_STOP_FIELD(snapshotStatus);
    S540_COPY_STOP_FIELD(identityStatus);S540_COPY_STOP_FIELD(locksStatus);S540_COPY_STOP_FIELD(protocolStatus);
    S540_COPY_STOP_FIELD(closingStatus);S540_COPY_STOP_FIELD(servicesStatus);S540_COPY_STOP_FIELD(sealStatus);
    S540_COPY_STOP_FIELD(disableStatus);S540_COPY_STOP_FIELD(interruptStatus);S540_COPY_STOP_FIELD(shutdownStatus);
    S540_COPY_STOP_FIELD(generation);S540_COPY_STOP_FIELD(requested);S540_COPY_STOP_FIELD(retained);
    S540_COPY_STOP_FIELD(originalReturned);S540_COPY_STOP_FIELD(originalExitReady);S540_COPY_STOP_FIELD(locksReleased);
    S540_COPY_STOP_FIELD(protocolAttempted);S540_COPY_STOP_FIELD(servicesAttempted);S540_COPY_STOP_FIELD(interruptAttempted);
    S540_COPY_STOP_FIELD(disableAttempted);S540_COPY_STOP_FIELD(shutdownAttempted);S540_COPY_STOP_FIELD(servicesDrained);
    S540_COPY_STOP_FIELD(interruptSoftwareDrained);S540_COPY_STOP_FIELD(interruptFullyDrained);
    S540_COPY_STOP_FIELD(cleanupComplete);S540_COPY_STOP_FIELD(physicalReleaseAuthorized);S540_COPY_STOP_FIELD(pmAcknowledgementSent);
#undef S540_COPY_STOP_FIELD
    wire.protocolFormat=stopped.protocol.format;wire.protocolBytes=stopped.protocol.bytes;
    wire.protocolGeneration=stopped.protocol.generation;wire.protocolOperationStatus=stopped.protocol.operationStatus;
    wire.protocolOriginalReturnStatus=stopped.protocol.originalReturnStatus;wire.protocolUnlockStatus=stopped.protocol.unlockStatus;
    wire.protocolClaimed=stopped.protocol.claimed;wire.protocolOriginalEntered=stopped.protocol.originalEntered;
    wire.protocolOriginalReturned=stopped.protocol.originalReturned;wire.protocolCompleted=stopped.protocol.protocolCompleted;
    IOLockUnlock(guard);
}
NV_STATUS S540ExperimentalTargetControl::runOnce(const S540ExperimentalRequest &request,NvBool *requestOwner) {
    if (!requestOwner) return NV_ERR_INVALID_ARGUMENT;
    S540ExperimentalNativeProfile profile{};
    NV_STATUS status=s540RuntimeReadCompiledProfile(&profile);
    const auto *identity=s540ExperimentalGetBuildIdentity();
    if (status!=NV_OK) return status;
    IOLockLock(guard);
    if (busy) { IOLockUnlock(guard); return NV_ERR_BUSY_RETRY; }
    status=s540ExperimentalRequestBegin(&state,NV_TRUE,&request,identity,profile.codeContractSha256,
        profile.workerStackBytes,profile.irqStackBytes);
    if (status!=NV_OK) { IOLockUnlock(guard); return status; }
    *requestOwner=NV_TRUE;
    busy=true;
    // This real retain remains even when preparation fails. It is deliberately
    // independent of diagnostic snapshots and private Impl cleanup decisions.
    retain(); permanentPin=true;
    IOLockUnlock(guard);
    void *storage=IOMalloc(sizeof(S540NvidiaGspBootstrap::Owner));
    if (!storage) status=NV_ERR_NO_MEMORY;
    else {
        auto *created=new(S540ExperimentalPlacement{storage}) S540NvidiaGspBootstrap::Owner;
        IOLockLock(guard); owner=created; state.snapshot.ownerAllocated=1; IOLockUnlock(guard);
        S540NvidiaGspBootstrap::Images images{};
        status=s540RuntimeEmbeddedFirmware(&images.gsp,&images.gspBytes,&images.ucodes,&images.ucodesBytes);
        if (status==NV_OK && stopPending()) status=NV_ERR_INVALID_STATE;
        if (status==NV_OK) {
            retainedProvider=copyTarget();
            if (!retainedProvider) status=NV_ERR_OBJECT_NOT_FOUND;
            else { IOLockLock(guard); state.snapshot.providerFound=1; IOLockUnlock(guard); }
        }
        if (status==NV_OK && stopPending()) status=NV_ERR_INVALID_STATE;
        if (status==NV_OK) {
            IOLockLock(guard); state.snapshot.preparationAttempted=1; IOLockUnlock(guard);
            status=owner->prepare(retainedProvider,this,images);
            IOLockLock(guard);
            state.snapshot.preparationReturned=1; state.snapshot.preparationStatus=status;
            cancellationReady=status==NV_OK;
            IOLockUnlock(guard);
        }
        if (status==NV_OK && stopPending()) status=NV_ERR_INVALID_STATE;
        if (status==NV_OK) {
            S540ExperimentalRuntimeRequest admitted{};
            admitted.format=1; admitted.bytes=sizeof(admitted);
            admitted.observedHostStackBytes=request.observedKernelStackBytes;
            admitted.manualAcknowledgement=request.manualAcknowledgement;
            for (NvU32 i=0;i<32;++i) admitted.codeContractSha256[i]=request.nativeCodeContractSha256[i];
            for (NvU32 i=0;i<16;++i) admitted.targetBuild[i]=request.targetBuild[i];
            IOLockLock(guard); state.snapshot.initializationAttempted=1; IOLockUnlock(guard);
            status=owner->experimentalInitialize(admitted);
            IOLockLock(guard);
            state.snapshot.initializationReturned=1; state.snapshot.initializationStatus=status;
            IOLockUnlock(guard);
        }
        closeCancellationPublication();
        publishOwnerObservation();
    }
    // Close the final pending-stop race under the same guard which publishes
    // busy=false. A concurrent STOP either joins this attempt or becomes the
    // next exclusive lifecycle writer; it cannot disappear between the two.
    IOLockLock(guard);
    if (owner && state.snapshot.stopRequested && !state.snapshot.stopReturned) {
        state.snapshot.stopAttempted=1; IOLockUnlock(guard);
        NV_STATUS stopped=owner->stop();
        publishOwnerObservation();
        IOLockLock(guard); state.snapshot.stopReturned=1; state.snapshot.stopStatus=stopped;
    }
    s540ExperimentalRequestFinish(&state,status); busy=false; IOLockUnlock(guard);
    return status;
}
NV_STATUS S540ExperimentalTargetControl::requestStop() {
    if (!guard) return NV_ERR_INVALID_STATE;
    IOLockLock(guard);
    (void)s540ExperimentalRequestStop(&state);
    if (busy) {
        const bool cancel=owner && cancellationReady;
        if (cancel) ++cancellationPublishers;
        IOLockUnlock(guard);
        if (cancel) {
            NV_STATUS cancelled=owner->cancelExperimental();
            IOLockLock(guard); state.snapshot.cancellationStatus=cancelled;
            --cancellationPublishers; IOLockWakeup(guard,&cancellationPublishers,false); IOLockUnlock(guard);
        }
        return NV_ERR_BUSY_RETRY;
    }
    if (!owner) { IOLockUnlock(guard); return NV_OK; }
    busy=true; cancellationReady=false; state.snapshot.stopAttempted=1;
    IOLockUnlock(guard);
    const NV_STATUS status=owner->stop();
    publishOwnerObservation();
    IOLockLock(guard);
    state.snapshot.stopReturned=1; state.snapshot.stopStatus=status; busy=false;
    IOLockUnlock(guard);
    return status;
}
bool S540ExperimentalTargetClient::initWithTask(task_t task,void *security,UInt32 type,OSDictionary *properties) {
    if (type!=S540_EXPERIMENTAL_CONNECTION_TYPE || !privileged(task) || !guard ||
        !IOUserClient::initWithTask(task,security,type,properties)) return false;
    IOLockLock(guard); bool allowed=callable() && clients<maximumClients;
    if (allowed) { ++clients; counted=true; }
    IOLockUnlock(guard); return allowed;
}
bool S540ExperimentalTargetClient::start(IOService *provider) {
    auto *candidate=OSDynamicCast(S540ExperimentalTargetControl,provider);
    if (!candidate || !counted || !IOUserClient::start(provider)) return false;
    control=candidate; control->retain(); return true;
}
void S540ExperimentalTargetClient::free() {
    if (control) { control->release(); control=nullptr; }
    if (counted && guard) { IOLockLock(guard); --clients; counted=false; IOLockUnlock(guard); }
    IOUserClient::free();
}
IOReturn S540ExperimentalTargetClient::clientClose() {
    bool owns=false;
    if (guard) { IOLockLock(guard); owns=requestOwned!=NV_FALSE; IOLockUnlock(guard); }
    if (control && owns) (void)control->requestStop();
    terminate(); return kIOReturnSuccess;
}
IOReturn S540ExperimentalTargetClient::externalMethod(uint32_t selector,IOExternalMethodArguments *arguments,
    IOExternalMethodDispatch *dispatch,OSObject *target,void *reference) {
    (void)dispatch; (void)target; (void)reference;
    if (!privileged(current_task())) return kIOReturnNotPrivileged;
    if (!control || !counted || !guard || control->isInactive()) return kIOReturnNotReady;
    if (!arguments || arguments->scalarInputCount || arguments->scalarOutputCount ||
        arguments->asyncWakePort || arguments->asyncReferenceCount || arguments->structureInputDescriptor ||
        arguments->structureOutputDescriptor || arguments->structureVariableOutputData ||
        !arguments->structureOutput || arguments->structureOutputSize!=sizeof(S540ExperimentalSnapshot))
        return kIOReturnBadArgument;
    NV_STATUS status=NV_OK;
    if (selector==S540_EXPERIMENTAL_SELECTOR_REQUEST) {
        if (!arguments->structureInput || arguments->structureInputSize!=sizeof(S540ExperimentalRequest))
            return kIOReturnBadArgument;
        const auto request=*static_cast<const S540ExperimentalRequest *>(arguments->structureInput);
        status=control->runOnce(request,&requestOwned);
    } else if (selector==S540_EXPERIMENTAL_SELECTOR_STOP) {
        if (arguments->structureInputSize) return kIOReturnBadArgument;
        status=control->requestStop();
    } else if (selector!=S540_EXPERIMENTAL_SELECTOR_SNAPSHOT || arguments->structureInputSize)
        return kIOReturnBadArgument;
    // Reading the cached integer wire state never dereferences a facade whose
    // Impl may be changing during preparation or stop.
    IOLockLock(guard); *static_cast<S540ExperimentalSnapshot *>(arguments->structureOutput)=state.snapshot;
    IOLockUnlock(guard); return translate(status);
}
