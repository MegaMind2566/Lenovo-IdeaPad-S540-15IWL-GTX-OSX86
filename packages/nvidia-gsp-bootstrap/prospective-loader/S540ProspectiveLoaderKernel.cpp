// SPDX-License-Identifier: MIT
// Isolated source-only IOKit prototype. It is not in project_sources().
#include "S540ProspectiveLoaderKernel.hpp"
#include "roots/S540NvidiaGspOriginalRoots.h"
#include <IOKit/IOLib.h>
#include <kern/task.h>
namespace {
IOLock *guard = nullptr;
S540ProspectiveState state{};
NvU32 services = 0, clients = 0;
bool privileged(task_t task) {
    return task && IOUserClient::clientHasPrivilege(task,kIOClientPrivilegeAdministrator) == kIOReturnSuccess;
}
bool callable() {
    return state.snapshot.moduleEntryAccepted && state.snapshot.controlServiceStarted &&
        !state.snapshot.stopping && state.snapshot.phase != S540_PROSPECTIVE_STOPPED;
}
}
OSDefineMetaClassAndStructors(S540ProspectiveLoaderControl, IOService);
OSDefineMetaClassAndStructors(S540ProspectiveLoaderClient, IOUserClient);

extern "C" kern_return_t s540ProspectiveModuleStartBackend(kmod_info_t *info) {
    // Module entry is evidence of this callback only, not an invented query of
    // OSKext::isStarted or successful return of the caller's load command.
    if (!info || !info->address || !info->size || guard || state.snapshot.format ||
        s540ProspectiveRetainedRootCount() != 25 || !s540ProspectiveRetainedRootsPresent())
        return KERN_FAILURE;
    IOLock *created = IOLockAlloc();
    if (!created) return KERN_RESOURCE_SHORTAGE;
    if (s540ProspectiveModuleEnter(&state) != NV_OK) { IOLockFree(created); return KERN_FAILURE; }
    guard = created;
    // No service instance, provider lookup, firmware, PM, IRQ, DMA or RM here.
    return KERN_SUCCESS;
}
extern "C" kern_return_t s540ProspectiveModuleStopBackend(void) {
    if (!guard) return KERN_SUCCESS;
    IOLockLock(guard);
    NV_STATUS status = s540ProspectiveBeginStop(&state);
    // Standard IOKit teardown must remove personalities/instances before
    // module stop. Check actual class counts as well as admitted instances.
    if (status == NV_OK && (S540ProspectiveLoaderControl::metaClass->getInstanceCount() ||
                           S540ProspectiveLoaderClient::metaClass->getInstanceCount()))
        status = NV_ERR_IN_USE;
    if (status == NV_OK) status = s540ProspectiveFinishStop(&state,services,clients);
    IOLockUnlock(guard);
    if (status != NV_OK) return KERN_FAILURE;
    IOLock *released = guard; guard = nullptr; IOLockFree(released);
    return KERN_SUCCESS;
}
bool S540ProspectiveLoaderControl::init(OSDictionary *properties) {
    if (!IOService::init(properties) || !guard) return false;
    IOLockLock(guard);
    const bool allowed = state.snapshot.phase == S540_PROSPECTIVE_MODULE_ENTERED && !services &&
        state.snapshot.moduleEntryAccepted && !state.snapshot.stopping;
    if (allowed) { ++services; counted = true; }
    IOLockUnlock(guard);
    return allowed;
}
void S540ProspectiveLoaderControl::free() {
    if (counted && guard) {
        IOLockLock(guard); --services; counted = false; IOLockUnlock(guard);
    }
    IOService::free();
}
bool S540ProspectiveLoaderControl::start(IOService *provider) {
    // This personality matches IOResources, never a PCI device. Equality
    // derives the actual framework provider; a user property cannot supply it.
    if (!guard || !counted || provider != IOService::getResourceService()) return false;
    if (!IOService::start(provider)) return false;
    IOLockLock(guard);
    NV_STATUS status = s540ProspectiveServiceStart(&state,getRegistryEntryID(),NV_TRUE);
    IOLockUnlock(guard);
    if (status != NV_OK) { IOService::stop(provider); return false; }
    registerService();
    return true;
}
void S540ProspectiveLoaderControl::stop(IOService *provider) {
    if (guard) { IOLockLock(guard); s540ProspectiveServiceGone(&state); IOLockUnlock(guard); }
    IOService::stop(provider);
}
IOReturn S540ProspectiveLoaderControl::newUserClient(task_t task, void *security, UInt32 type,
    OSDictionary *properties, IOUserClient **handler) {
    if (handler) *handler = nullptr;
    if (!handler || type != S540_PROSPECTIVE_CONNECTION_TYPE) return kIOReturnBadArgument;
    if (!privileged(task)) return kIOReturnNotPrivileged;
    if (!guard) return kIOReturnNotReady;
    IOLockLock(guard); bool allowed = callable() && !clients; IOLockUnlock(guard);
    if (!allowed) return kIOReturnNotReady;
    auto *client = new S540ProspectiveLoaderClient;
    if (!client) return kIOReturnNoMemory;
    if (!client->initWithTask(task,security,type,properties)) { client->release(); return kIOReturnError; }
    if (!client->attach(this)) { client->release(); return kIOReturnError; }
    if (!client->start(this)) { client->detach(this); client->release(); return kIOReturnError; }
    *handler = client;
    return kIOReturnSuccess;
}
bool S540ProspectiveLoaderClient::initWithTask(task_t task, void *security, UInt32 type,
    OSDictionary *properties) {
    if (type != S540_PROSPECTIVE_CONNECTION_TYPE || !privileged(task) || !guard ||
        !IOUserClient::initWithTask(task,security,type,properties)) return false;
    IOLockLock(guard);
    const bool allowed = callable() && !clients;
    if (allowed) { ++clients; counted = true; }
    IOLockUnlock(guard);
    return allowed;
}
bool S540ProspectiveLoaderClient::start(IOService *provider) {
    auto *candidate = OSDynamicCast(S540ProspectiveLoaderControl,provider);
    if (!candidate || !counted || !IOUserClient::start(provider)) return false;
    control = candidate; control->retain();
    return true;
}
void S540ProspectiveLoaderClient::free() {
    if (control) { control->release(); control = nullptr; }
    if (counted && guard) { IOLockLock(guard); --clients; counted = false; IOLockUnlock(guard); }
    IOUserClient::free();
}
IOReturn S540ProspectiveLoaderClient::clientClose() {
    terminate();
    return kIOReturnSuccess;
}
IOReturn S540ProspectiveLoaderClient::externalMethod(uint32_t selector,
    IOExternalMethodArguments *arguments, IOExternalMethodDispatch *dispatch,
    OSObject *target, void *reference) {
    (void)dispatch; (void)target; (void)reference;
    // Authenticate the current caller each time, so transferring a root's
    // connection send right does not transfer administrator authorization.
    if (!privileged(current_task())) return kIOReturnNotPrivileged;
    if (!control || !counted || !guard || control->isInactive()) return kIOReturnNotReady;
    if (!arguments || arguments->scalarInputCount || arguments->scalarOutputCount ||
        arguments->asyncWakePort || arguments->asyncReferenceCount ||
        arguments->structureInputDescriptor || arguments->structureOutputDescriptor ||
        arguments->structureVariableOutputData) return kIOReturnBadArgument;
    if (!arguments->structureOutput || arguments->structureOutputSize != sizeof(S540ProspectiveSnapshot))
        return kIOReturnBadArgument;
    if (selector == S540_PROSPECTIVE_SELECTOR_SNAPSHOT) {
        if (arguments->structureInputSize) return kIOReturnBadArgument;
        IOLockLock(guard); *static_cast<S540ProspectiveSnapshot *>(arguments->structureOutput) = state.snapshot;
        IOLockUnlock(guard); return kIOReturnSuccess;
    }
    if (selector != S540_PROSPECTIVE_SELECTOR_REQUEST) return kIOReturnUnsupported;
    if (!arguments->structureInput || arguments->structureInputSize != sizeof(S540ProspectiveRequest))
        return kIOReturnBadArgument;
    S540ProspectiveRequest request = *static_cast<const S540ProspectiveRequest *>(arguments->structureInput);
    IOLockLock(guard);
    NV_STATUS status = s540ProspectiveRequestOnce(&state,NV_TRUE,&request);
    *static_cast<S540ProspectiveSnapshot *>(arguments->structureOutput) = state.snapshot;
    IOLockUnlock(guard);
    // Return the actual refusal; never turn policy-closed activation into OK.
    if (status == NV_ERR_INSUFFICIENT_PERMISSIONS) return kIOReturnNotPrivileged;
    if (status == NV_ERR_STATE_IN_USE) return kIOReturnExclusiveAccess;
    if (status == NV_ERR_INVALID_ARGUMENT) return kIOReturnBadArgument;
    if (status == NV_ERR_INVALID_STATE) return kIOReturnNotReady;
    return kIOReturnNotReady;
}
