// SPDX-License-Identifier: MIT
// Independent pinned SDK operations. Never linked into the driver.
#include <IOKit/IOLib.h>
#include <IOKit/IOService.h>
#include <IOKit/pci/IOPCIDevice.h>
#include <IOKit/pwr_mgt/IOPowerConnection.h>
#include <kern/clock.h>
#include <kern/thread.h>
extern "C" void s540GspPowerSdkReference(IOService *child, IOPCIDevice *provider,
    IOPMPowerState *states, IOLock *guard, void *event) {
    (void)child->IOService::init(nullptr);
    (void)child->attach(provider);
    (void)child->IOService::start(provider);
    child->setName("S540NvidiaGspPowerLease");
    child->PMinit();
    (void)child->registerPowerDriver(child, states, 2);
    (void)child->changePowerStateTo(0);
    (void)provider->addPowerChild(child);
    (void)child->changePowerStateToPriv(1);
    child->IOService::powerChangeDone(0);
    (void)child->acknowledgeSetPowerState();
    child->PMstop();
    child->IOService::stop(provider);
    child->detach(provider);
    IORegistryEntry *connection = child->copyParentEntry(gIOPowerPlane);
    IORegistryEntry *parent = connection ? connection->copyParentEntry(gIOPowerPlane) : nullptr;
    (void)OSDynamicCast(IOPowerConnection, connection);
    if (parent) parent->release();
    if (connection) connection->release();
    uint64_t deadline = 0;
    clock_interval_to_deadline(5000, kMillisecondScale, &deadline);
    (void)IOLockSleepDeadline(guard, event, deadline, THREAD_UNINT);
    IOLockWakeup(guard, event, false);
    child->IOService::free();
}
