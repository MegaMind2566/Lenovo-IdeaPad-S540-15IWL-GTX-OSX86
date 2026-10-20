// SPDX-License-Identifier: MIT
// Independent compile-only declaration/import reference. Never link or execute.
// Deliberately does not include S540NvidiaPublicCallout.hpp.
#include <IOKit/IOWorkLoop.h>
#include <IOKit/IOTimerEventSource.h>
#include <libkern/c++/OSData.h>

namespace {
void timerAction(OSObject *, IOTimerEventSource *) {}
IOReturn gateAction(OSObject *, void *, void *, void *, void *) { return kIOReturnSuccess; }
}
extern "C" void s540PublicCallbackSdkImportReference(const void *bytes, unsigned length,
    AbsoluteTime deadline) {
    OSData *owner=OSData::withBytes(bytes,length);
    if (!owner) return;
    IOWorkLoop *loop=IOWorkLoop::workLoop();
    if (!loop) { owner->release(); return; }
    IOTimerEventSource *source=IOTimerEventSource::timerEventSource(
        kIOTimerEventSourceOptionsPriorityWorkLoop,owner,timerAction);
    (void)owner->getBytesNoCopy();
    if (source && loop->addEventSource(source)==kIOReturnSuccess) {
        (void)source->wakeAtTime(deadline);
        (void)loop->runAction(gateAction,owner,source);
        source->cancelTimeout();
        (void)loop->removeEventSource(source);
    }
    if (source) source->release();
    loop->release();
    owner->release();
}
