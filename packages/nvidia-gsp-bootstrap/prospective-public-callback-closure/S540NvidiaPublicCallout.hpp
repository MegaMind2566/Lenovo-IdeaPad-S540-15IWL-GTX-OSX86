// SPDX-License-Identifier: MIT
#pragma once

// Public IOKit lifetime boundary. No application callback runs in Apple's
// private interrupt signaler. The application runs under its own workloop gate.
#include <IOKit/IOWorkLoop.h>
#include <IOKit/IOTimerEventSource.h>
#include <libkern/c++/OSData.h>

struct S540PublicCallout {
    using Action = void (*)(void *);
    struct Binding { Action action; void *context; };
    OSData *owner;
    IOWorkLoop *loop;
    IOTimerEventSource *source;

    static void invoke(OSObject *object, IOTimerEventSource *) {
        const auto *binding = static_cast<const Binding *>(
            static_cast<OSData *>(object)->getBytesNoCopy());
        binding->action(binding->context);
    }
    bool initialize(Action action, void *context) {
        const Binding binding = {action, context};
        owner = OSData::withBytes(&binding, sizeof(binding));
        if (!owner) return false;
        loop = IOWorkLoop::workLoop();
        if (!loop) { owner->release(); owner = nullptr; return false; }
        source = IOTimerEventSource::timerEventSource(
            kIOTimerEventSourceOptionsPriorityWorkLoop, owner, invoke);
        if (!source) {
            loop->release(); loop = nullptr;
            owner->release(); owner = nullptr;
            return false;
        }
        if (loop->addEventSource(source) != kIOReturnSuccess) {
            source->release(); source = nullptr;
            loop->release(); loop = nullptr;
            owner->release(); owner = nullptr;
            return false;
        }
        return true;
    }
    // Caller serializes scheduling with its existing short state Guard.
    // PriorityWorkLoop wakeAtTime never acquires the workloop gate: it enters
    // the preallocated Apple interrupt signaler. No allocation or sleep here.
    bool schedule(AbsoluteTime deadline) {
        return source->wakeAtTime(deadline) == kIOReturnSuccess;
    }
    static IOReturn cancel(OSObject *, void *event, void *, void *, void *) {
        static_cast<IOTimerEventSource *>(event)->cancelTimeout();
        return kIOReturnSuccess;
    }
    // Caller first closes admission and releases its Guard. Gate acquisition
    // waits for the complete application callback return. cancelTimeout then
    // invalidates pending generations and drains Apple's interrupt signaler.
    bool drain() {
        return loop->runAction(cancel, owner, source) == kIOReturnSuccess;
    }
    // All external references must already be quiescent and drain succeeded.
    // A failed removal retains every object and its application callback text.
    bool retire() {
        if (loop->removeEventSource(source) != kIOReturnSuccess) return false;
        source->release(); source = nullptr;
        owner->release(); owner = nullptr;
        loop->release(); loop = nullptr;
        return true;
    }
};
