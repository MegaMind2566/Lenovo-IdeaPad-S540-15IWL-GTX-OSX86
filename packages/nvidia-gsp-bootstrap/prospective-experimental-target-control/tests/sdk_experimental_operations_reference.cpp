// SPDX-License-Identifier: MIT
#include "../S540ExperimentalTargetKernel.hpp"
#include <IOKit/IOLib.h>
#include <IOKit/pci/IOPCIDevice.h>
#include <kern/task.h>
// The real module-stop refusal checks both live metaclass instance counts.
// Derive this const public SDK operation instead of approving a bare symbol.
extern "C" unsigned int s540ExperimentalSdkInstanceCount(const OSMetaClass *meta) {
    return meta->getInstanceCount();
}
// This reference names actual public virtual operations independently of the
// frontend implementation. It supplies compiler/SDK bindings, not success.
extern "C" bool s540ExperimentalSdkOperations(IOService *service,IOUserClient *client,
    OSDictionary *dictionary,task_t task,void *security) {
    if (!service || !client) return false;
    bool initialized=service->IOService::init(dictionary);
    bool started=service->IOService::start(IOService::getResourceService());
    service->IOService::stop(IOService::getResourceService());
    bool user=client->IOUserClient::initWithTask(task,security,S540_EXPERIMENTAL_CONNECTION_TYPE,dictionary);
    IOLock *lock=IOLockAlloc();
    if (lock) {
        IOLockLock(lock);IOLockWakeup(lock,lock,false);
        if (!initialized) IOLockSleep(lock,lock,THREAD_UNINT);
        IOLockUnlock(lock);IOLockFree(lock);
    }
    void *memory=IOMalloc(8);if (memory) IOFree(memory,8);
    OSDictionary *matching=IOService::serviceMatching("IOPCIDevice");
    if (matching) {
        OSIterator *iterator=IOService::getMatchingServices(matching);matching->release();
        if (iterator) {
            bool valid=iterator->isValid();
            auto *device=OSDynamicCast(IOPCIDevice,iterator->getNextObject());
            if (valid && device && !device->isInactive()) (void)device->configRead32(0);
            iterator->release();
        }
    }
    (void)IOUserClient::clientHasPrivilege(current_task(),kIOClientPrivilegeAdministrator);
    return initialized && started && user && service->getRegistryEntryID();
}
