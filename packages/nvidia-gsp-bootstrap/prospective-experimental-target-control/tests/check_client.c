/* SPDX-License-Identifier: MIT
 * The actual user client is included unchanged. IOKit/CF/sysctl/privilege
 * endpoints below are CPU fixtures; no service, kernel or GPU is contacted. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <sys/types.h>
#include <unistd.h>
#include <IOKit/IOKitLib.h>
#include <CoreFoundation/CoreFoundation.h>
#include "../S540ExperimentalTargetProtocol.h"
#define S540_EXPERIMENTAL_EXPECTED_SOURCE {0x11}
#define S540_EXPERIMENTAL_EXPECTED_POLICY {0x22}
#define S540_EXPERIMENTAL_EXPECTED_NATIVE {0x33}
#define S540_EXPERIMENTAL_REQUIRED_STACK 16384ULL
typedef struct FakeCF { unsigned kind, bytes; const char *key; UInt8 data[4]; } FakeCF;
static unsigned scenario, checks, failures, requests, stops, observations, closes, opens;
static unsigned iterNext, iterReleased, entriesReleased, enumCalls, matchingCalls, requestOrder, stopOrder, sequence;
static NvU64 stackBytes = 16384;
static const char *matchingClass;
static void expect(int value, const char *why) {
    ++checks; if (!value) { ++failures; fprintf(stderr, "actual client: %s\n", why); }
}
static uid_t fixtureGeteuid(void) { return scenario == 24 ? 501 : 0; }
int sysctlbyname(const char *name, void *old, size_t *bytes, const void *input, size_t inputBytes) {
    expect(!input && !inputBytes && old && bytes, "sysctl is read-only");
    if (!strcmp(name, "kern.stack_size")) {
        if (scenario == 7) return -1;
        NvU64 value = scenario == 39 ? 0 : stackBytes;
        if (scenario == 6) { *bytes = 2; return 0; }
        if (scenario == 4) { uint32_t narrow = (uint32_t)value; memcpy(old, &narrow, 4); *bytes = 4; }
        else { memcpy(old, &value, 8); *bytes = 8; }
        return 0;
    }
    const char *value;
    if (!strcmp(name, "kern.osversion")) value = scenario == 8 ? "25G242" : "25G241";
    else if (!strcmp(name, "kern.osrelease")) value = scenario == 9 ? "25.5.0" : "25.6.0";
    else return -1;
    if (scenario == 42 && !strcmp(name, "kern.osversion")) { memset(old, 'a', *bytes); return 0; }
    size_t needed = strlen(value) + 1;
    expect(*bytes >= needed, "sysctl string capacity"); memcpy(old, value, needed); *bytes = needed; return 0;
}
CFStringRef CFStringCreateWithCString(CFAllocatorRef allocator, const char *text, CFStringEncoding encoding) {
    (void)allocator; (void)encoding;
    if (scenario == 48) return NULL;
    FakeCF *value = calloc(1, sizeof(*value)); if (!value) abort();
    value->kind = 1; value->key = text; return value;
}
CFTypeID CFGetTypeID(CFTypeRef value) { return ((const FakeCF *)value)->kind; }
CFTypeID CFDataGetTypeID(void) { return 2; }
CFIndex CFDataGetLength(CFDataRef value) { return ((const FakeCF *)value)->bytes; }
const UInt8 *CFDataGetBytePtr(CFDataRef value) { return ((const FakeCF *)value)->data; }
void CFRelease(CFTypeRef value) { free((void *)value); }
CFMutableDictionaryRef IOServiceMatching(const char *name) { matchingClass = name; return (void *)name; }
kern_return_t IOServiceGetMatchingServices(mach_port_t port, CFDictionaryRef match, io_iterator_t *iterator) {
    (void)port; (void)match; ++enumCalls;
    expect(matchingClass && !strcmp(matchingClass, "IOPCIDevice"), "readonly target uses PCI registry matching");
    if (scenario == 38) return kIOReturnError;
    *iterator = 90; return KERN_SUCCESS;
}
io_service_t IOServiceGetMatchingService(mach_port_t port, CFDictionaryRef match) {
    (void)port; (void)match; ++matchingCalls;
    expect(matchingClass && !strcmp(matchingClass, "S540ExperimentalTargetControl"), "exact experimental control class");
    return scenario == 25 ? 0 : 80;
}
boolean_t IOIteratorIsValid(io_iterator_t iterator) {
    expect(iterator == 90, "actual iterator identity");
    return scenario != 33 && !(scenario == 34 && iterNext >= 1);
}
io_object_t IOIteratorNext(io_iterator_t iterator) {
    expect(iterator == 90, "actual bounded iterator next");
    unsigned count = scenario == 32 ? 2 : (scenario == 35 ? 1025 : 1);
    if (iterNext >= count) { ++iterNext; return 0; }
    return 1000 + iterNext++;
}
CFTypeRef IORegistryEntryCreateCFProperty(io_registry_entry_t entry, CFStringRef name, CFAllocatorRef allocator, uint32_t options) {
    (void)allocator; (void)options;
    expect(entry >= 1000 && entry < 2025, "actual enumerated registry entry");
    const char *key = ((const FakeCF *)name)->key;
    uint32_t number = 0;
    if (!strcmp(key, "vendor-id")) number = (scenario == 31 || (scenario == 35 && entry != 1000)) ? 0x8086 : 0x10de;
    else if (!strcmp(key, "device-id")) number = 0x1f91;
    else if (!strcmp(key, "subsystem-vendor-id")) number = 0x17aa;
    else if (!strcmp(key, "subsystem-id")) number = 0x3806;
    else if (!strcmp(key, "revision-id")) number = 0xa1;
    else if (!strcmp(key, "class-code")) number = 0x030000;
    else expect(0, "only actual target identity properties read");
    FakeCF *value = calloc(1, sizeof(*value)); if (!value) abort();
    value->kind = scenario == 37 ? 1 : 2; value->bytes = scenario == 36 ? 2 : 4;
    for (unsigned index = 0; index < 4; ++index) value->data[index] = (number >> (index * 8)) & 0xff;
    return value;
}
kern_return_t IOObjectRelease(io_object_t object) {
    if (object == 90) ++iterReleased;
    else if (object >= 1000 && object < 2025) ++entriesReleased;
    else expect(object == 80, "only matched control service released");
    return KERN_SUCCESS;
}
kern_return_t IORegistryEntryGetRegistryEntryID(io_registry_entry_t service, uint64_t *identifier) {
    expect(service == 80, "actual control registry identity");
    *identifier = 99; return scenario == 27 ? kIOReturnError : KERN_SUCCESS;
}
mach_port_t mach_task_self(void) { return 77; }
kern_return_t IOServiceOpen(io_service_t service, task_port_t task, uint32_t type, io_connect_t *connection) {
    ++opens;
    expect(service == 80 && task == 77 && type == S540_EXPERIMENTAL_CONNECTION_TYPE, "exact typed user-client open");
    if (scenario == 26) return kIOReturnError;
    *connection = 81; return KERN_SUCCESS;
}
kern_return_t IOServiceClose(io_connect_t connection) {
    expect(connection == 81, "same actual connection closed"); ++closes; return KERN_SUCCESS;
}
static void preparationSnapshot(S540ExperimentalSnapshot *out) {
    if (scenario < 49 || scenario > 66 || scenario == 53 ||
        ((scenario <= 52 || (scenario >= 63 && scenario <= 65)) && !requests)) return;
    S540PreparationObservation *p = &out->preparation;
    p->format = 1; p->bytes = sizeof(*p);
    p->stage = S540_PREP_CONTEXT_CREATE; p->lastCompleted = S540_PREP_DMA_REMAP;
    p->firstFailureStage = S540_PREP_CONTEXT_CREATE; p->firstFailureStatus = NV_ERR_NOT_SUPPORTED;
    p->lastStatus = NV_ERR_NOT_SUPPORTED;
    p->observedMask = S540_PREP_OBS_STAGE | S540_PREP_OBS_STATUS | S540_PREP_OBS_FIRST_FAILURE |
        S540_PREP_OBS_HOST_FACTS | S540_PREP_OBS_DEVICE_FACTS | S540_PREP_OBS_POWER;
    p->hostKnown = 0x7f; p->deviceObserved = S540_PREP_DEVICE_ALL; p->devicePredicates = S540_PREP_DEVICE_ALL;
    p->power.format = 1; p->power.bytes = sizeof(p->power);
    p->power.stage = p->power.lastCompleted = S540_PREP_POWER_COMPLETE;
    p->power.observedMask = S540_PREP_PM_OBS_READY | S540_PREP_PM_OBS_DOMAIN |
        S540_PREP_PM_OBS_ACTIVE | S540_PREP_PM_OBS_PROTOCOL;
    p->power.flags = S540_PREP_PM_OBS_READY | S540_PREP_PM_OBS_DOMAIN | S540_PREP_PM_OBS_ACTIVE |
        S540_PREP_PM_FLAG_ON_REQUESTED | S540_PREP_PM_FLAG_ON_SET | S540_PREP_PM_FLAG_ON_COMPLETED;
    if (scenario <= 52) {
        out->preparationAttempted = out->preparationReturned = 1;
        out->preparationStatus = NV_ERR_NOT_SUPPORTED;
        out->initializationAttempted = out->initializationReturned = 0;
        out->adapterInitialized = out->globalInitialized = out->originalEntryObserved = 0;
        out->ownerAllocated = out->providerFound = 1;
        out->retainedStop.cleanupComplete = stops != 0;
        if (stops) {
            out->stopStatus = out->retainedStop.status = NV_OK;
            out->retainedStop.retained = 0;
        }
        // The recorded failure is retained after the fake Owner's successful
        // cleanup; cleanup cannot rewrite the historical preparation result.
    }
    if (scenario == 50) {
        p->stage = p->firstFailureStage = S540_PREP_POWER_START; p->lastCompleted = S540_PREP_DISPATCH_PREPARE;
        p->firstFailureStatus = p->lastStatus = out->preparationStatus = NV_ERR_TIMEOUT;
        p->observedMask = S540_PREP_OBS_STAGE | S540_PREP_OBS_STATUS | S540_PREP_OBS_FIRST_FAILURE | S540_PREP_OBS_POWER;
        p->hostKnown = p->deviceObserved = p->devicePredicates = 0;
        p->power.stage = p->power.firstFailureStage = S540_PREP_POWER_WAIT_DOMAIN;
        p->power.lastCompleted = S540_PREP_POWER_WAIT_READY; p->power.firstFailureStatus = NV_ERR_TIMEOUT;
        p->power.rawIOReturn = p->power.firstFailureRawIOReturn = 0xe00002d8U;
        p->power.rawIOReturnValid = p->power.firstFailureRawIOReturnValid = 1;
        p->power.observedMask |= S540_PREP_PM_OBS_WAIT_RESULT | S540_PREP_PM_OBS_RAW_IOR;
        p->power.flags = S540_PREP_PM_OBS_READY | S540_PREP_PM_OBS_ACTIVE | S540_PREP_PM_FLAG_ON_REQUESTED;
        p->power.waitResult = 7; p->power.waitResultValid = 1;
    }
    if (scenario == 51) {
        p->stage = p->firstFailureStage = S540_PREP_HOST_FACTS; p->lastCompleted = S540_PREP_PLATFORM_INITIALIZE;
        p->hostKnown = 0x1f; p->hostMissing = 0x20;
        p->observedMask &= ~S540_PREP_OBS_DEVICE_FACTS; p->deviceObserved = p->devicePredicates = 0;
    }
    if (scenario == 52) {
        p->stage = p->firstFailureStage = S540_PREP_DEVICE_FACTS; p->lastCompleted = S540_PREP_HOST_FACTS;
        p->devicePredicates &= ~S540_PREP_DEVICE_BARS;
    }
    if (scenario == 54) p->format = 2;
    if (scenario == 55) --p->bytes;
    if (scenario == 56) p->stage = p->firstFailureStage = 0xffffffffU;
    if (scenario == 57) {
        p->power.rawIOReturn = p->power.firstFailureRawIOReturn = 0;
        p->power.rawIOReturnValid = p->power.firstFailureRawIOReturnValid = 0;
    }
    if (scenario == 58) {
        p->stage = p->lastCompleted = S540_PREP_COMPLETE;
        p->lastStatus = NV_OK; p->firstFailureStage = p->firstFailureStatus = 0;
        p->observedMask &= ~S540_PREP_OBS_FIRST_FAILURE;
    }
    if (scenario == 59) {
        p->observedMask &= ~(S540_PREP_OBS_HOST_FACTS | S540_PREP_OBS_DEVICE_FACTS);
        p->hostKnown = 0x7f; p->hostMissing = 0; p->deviceObserved = p->devicePredicates = S540_PREP_DEVICE_ALL;
    }
    if (scenario == 60) p->power.format = 2;
    if (scenario == 61) --p->power.bytes;
    if (scenario == 62) p->deviceObserved = S540_PREP_DEVICE_PCI;
    if (scenario == 64 || scenario == 65) {
        p->stage = p->lastCompleted = S540_PREP_COMPLETE;
        p->lastStatus = NV_OK; p->firstFailureStage = p->firstFailureStatus = 0;
        p->observedMask &= ~S540_PREP_OBS_FIRST_FAILURE;
    }
    if (scenario == 66) {
        p->stage = p->lastCompleted = p->firstFailureStage = p->firstFailureStatus = p->lastStatus = 0;
        p->observedMask = S540_PREP_OBS_POWER;
        p->power.observedMask = 0x80000000U;
        p->power.stage = p->power.lastCompleted = S540_PREP_POWER_COMPLETE;
        p->power.rawIOReturn = 0; p->power.rawIOReturnValid = 1;
    }
}
static void runtimeSnapshot(S540ExperimentalSnapshot *out) {
    if(scenario<67)return;
    S540ExperimentalRuntimeObservation *r=&out->runtime;
    r->format=1;r->bytes=sizeof(*r);r->snapshotStatus=NV_OK;
    r->stage=12;r->lastStage=r->firstFailureStage=9;r->firstStatus=NV_ERR_NOT_SUPPORTED;
    r->attemptedMask=r->returnedMask=15;r->irqStatus=NV_ERR_NOT_SUPPORTED;r->originalStatus=NV_ERR_NOT_READY;
    r->lifetimeRetained=r->cancellationBegun=r->ownerEpochBegun=1;
    r->globalInitialized=r->globalOriginalReturned=r->originalEntered=1;
    r->generation=17;r->observedHostStackBytes=r->requiredWorkerStackBytes=r->requiredIrqStackBytes=16384;
    out->runtimeObservationStatus=NV_OK;
    out->globalInitialized=out->originalEntryObserved=1;
    out->adapterInitialized=out->firmwareLoaded=0;
    out->initializationAttempted=out->initializationReturned=1;
    out->initializationStatus=NV_ERR_NOT_SUPPORTED;
    S540ExperimentalIrqSourceObservation *q=&out->irqSource;
    q->format=1;q->bytes=sizeof(*q);q->sourceProbeAttempted=q->sourceProbeReturned=1;
    q->sourceProbeStatus=NV_ERR_NOT_SUPPORTED;q->sourceCount=q->sourcesObserved=2;
    q->inventoryValid=q->msiCapable=1;q->msiVectors=1;
    if(scenario==68 || scenario==69){
        r->stage=r->lastStage=11;r->firstFailureStage=r->firstStatus=0;
        r->attemptedMask=r->returnedMask=S540_RUNTIME_CALL_ALL;r->irqStatus=r->originalStatus=NV_OK;
        r->adapterAttempted=r->adapterInitialized=r->originalReturned=1;r->interruptInstalled=r->interruptArmed=1;
        out->adapterInitialized=out->interruptInstalled=out->interruptArmed=1;out->initializationStatus=NV_OK;
        q->sourceProbeStatus=NV_OK;q->messagedSources=q->selectedSourceValid=q->selectedTypeValid=1;
        q->selectedSource=scenario==68?1:0;q->selectedInterruptType=0x10000;
        if(scenario==69)q->sourceCount=q->sourcesObserved=1;
    }
    if(scenario==70){r->snapshotStatus=NV_ERR_NOT_READY;r->originalEntered=1;}
    if(scenario==71){r->snapshotStatus=NV_ERR_IN_USE;r->originalEntered=1;}
    if(scenario==72)r->format=2;
    if(scenario==73)--r->bytes;
    if(scenario==74)r->attemptedMask|=0x80000000U;
    if(scenario==75)r->returnedMask|=S540_RUNTIME_CALL_ORIGINAL;
    if(scenario==76)r->stage=0xffffffffU;
    if(scenario==77){r->stage=r->lastStage=9;r->firstFailureStage=r->firstStatus=0;
        r->returnedMask=7;r->irqStatus=NV_ERR_NOT_READY;}
    if(scenario==78){r->firstStatus=r->irqStatus=NV_ERR_NOT_READY;}
    if(scenario==79)q->format=2;
    if(scenario==80)--q->bytes;
    if(scenario==81){q->sourceProbeReturned=0;q->sourceProbeStatus=NV_OK;q->selectedSourceValid=q->selectedTypeValid=1;}
    if(scenario==82 || scenario==86){q->sourceProbeStatus=NV_OK;q->selectedSourceValid=q->selectedTypeValid=1;
        q->selectedSource=1;q->selectedInterruptType=scenario==86?0:0x10000;q->messagedSources=scenario==86?1:2;}
}
static void snapshot(S540ExperimentalSnapshot *out) {
    const NvU8 source[32] = S540_EXPERIMENTAL_EXPECTED_SOURCE;
    const NvU8 policy[32] = S540_EXPERIMENTAL_EXPECTED_POLICY;
    const NvU8 native[32] = S540_EXPERIMENTAL_EXPECTED_NATIVE;
    memset(out, 0, sizeof(*out)); out->format = S540_EXPERIMENTAL_SNAPSHOT_VERSION; out->bytes = sizeof(*out);
    out->moduleEntryAccepted = out->controlServiceStarted = 1; out->generation = 99;
    out->nativeRequiredKernelStackBytes = out->nativeRequiredIrqStackBytes = 16384;
    memcpy(out->sourceSha256, source, 32); memcpy(out->policySha256, policy, 32);
    memcpy(out->nativeCodeContractSha256, native, 32);
    out->requestConsumed = requests != 0; out->retainedUntilReboot = requests != 0;
    out->observedKernelStackBytes = requests ? stackBytes : 0;
    out->stopAttempted = out->stopReturned = stops != 0;
    out->stopStatus = stops ? NV_ERR_IN_USE : NV_OK;
    out->initializationAttempted = out->initializationReturned = requests != 0;
    out->adapterInitialized = out->globalInitialized = out->originalEntryObserved = requests != 0;
    out->retainedStop.format = 1; out->retainedStop.bytes = sizeof(out->retainedStop);
    out->retainedStop.attempts = stops; out->retainedStop.status = out->stopStatus;
    out->retainedStop.retained = requests != 0;
    preparationSnapshot(out);
    runtimeSnapshot(out);
    if (scenario == 12) out->format = 1;
    if (scenario == 83 || (scenario == 84 && observations==2)) out->format=2;
    if (scenario == 13) out->moduleEntryAccepted = 0;
    if (scenario == 14) out->controlServiceStarted = 0;
    if (scenario == 15) out->generation = 0;
    if (scenario == 16) out->sourceSha256[0] ^= 1;
    if (scenario == 17) out->policySha256[0] ^= 1;
    if (scenario == 18) out->nativeCodeContractSha256[0] ^= 1;
    if (scenario == 19) out->nativeRequiredKernelStackBytes = 32768;
    if (scenario == 20) out->nativeRequiredIrqStackBytes = 0;
    if (scenario == 21) out->wholeDmaStopProven = 1;
    if (scenario == 22) out->pmAcknowledgementAuthorized = 1;
    if (scenario == 23) out->accelerationTest = 1;
    if (scenario == 28) out->nativeRequiredKernelStackBytes = 0;
    if (scenario == 41) out->generation = 100;
}
kern_return_t IOConnectCallStructMethod(io_connect_t connection, uint32_t selector,
    const void *input, size_t inputBytes, void *output, size_t *outputBytes) {
    expect(connection == 81 && output && outputBytes && *outputBytes == sizeof(S540ExperimentalSnapshot),
        "actual RPC uses same connection and exact output capacity"); ++sequence;
    if (selector == S540_EXPERIMENTAL_SELECTOR_SNAPSHOT) {
        ++observations;
        expect(!input && !inputBytes, "snapshot has no request input");
        if ((scenario == 29 || scenario == 46) && observations == 2) return kIOReturnError;
        snapshot(output); if(scenario==85 && observations==2)return kIOReturnError;
        if (scenario == 11) --*outputBytes;
        if (scenario == 63 || (scenario == 65 && observations == 2))
            --((S540ExperimentalSnapshot *)output)->bytes;
        if (scenario == 64 && observations == 2) ((S540ExperimentalSnapshot *)output)->format = 1;
        return KERN_SUCCESS;
    }
    if (selector == S540_EXPERIMENTAL_SELECTOR_REQUEST) {
        ++requests; requestOrder = sequence;
        const S540ExperimentalRequest *request = input;
        expect(input && inputBytes == sizeof(*request) && request->format == 1 && request->bytes == sizeof(*request),
            "exact request wire ABI");
        expect(request->generation == 99 && request->observedKernelStackBytes == stackBytes &&
            request->manualAcknowledgement == S540_EXPERIMENTAL_MANUAL_ACK && !strcmp(request->targetBuild, "25G241"),
            "actual generation, sysctl capacity and explicit manual acknowledgement");
        expect(request->sourceSha256[0] == 0x11 && request->policySha256[0] == 0x22 &&
            request->nativeCodeContractSha256[0] == 0x33, "packaged immutable image identity forwarded");
        snapshot(output); return scenario == 1 || (scenario >= 49 && scenario <= 52) ? kIOReturnError : KERN_SUCCESS;
    }
    expect(selector == S540_EXPERIMENTAL_SELECTOR_STOP && !input && !inputBytes, "only typed no-input STOP accepted");
    ++stops; stopOrder = sequence;
    snapshot(output); return scenario == 2 || scenario == 45 ? kIOReturnBusy : KERN_SUCCESS;
}
#define __APPLE__ 1
#define geteuid fixtureGeteuid
#define main s540ActualClientMain
#ifndef S540_CLIENT_SOURCE
#define S540_CLIENT_SOURCE "../experimental_ctl.c"
#endif
#include S540_CLIENT_SOURCE
#undef main
#undef geteuid
int main(int argc, char **argv) {
    if (argc != 2) return 2;
    scenario = (unsigned)strtoul(argv[1], NULL, 10);
    if (scenario >= 87) return 2;
    if (scenario == 10 || scenario == 47) stackBytes = 8192;
    if (scenario == 40) stackBytes = 32768;
    int target = (scenario >= 30 && scenario <= 38) || scenario == 47 || scenario == 48;
    int stopOnly = scenario >= 44 && scenario <= 46;
    int readOnly = scenario == 3 || (scenario >= 53 && scenario <= 62) || scenario == 66 ||
        (scenario>=67 && scenario<=82) || scenario==86;
    char *run[] = {"experimental_ctl", "--run-once", "--ack-retained-first-initialization"};
    char *readonly[] = {"experimental_ctl", "--snapshot"};
    char *targetArgs[] = {"experimental_ctl", "--target"};
    char *stopArgs[] = {"experimental_ctl", "--stop"};
    char *invalid[] = {"experimental_ctl", "--run-once"};
    int actual = s540ActualClientMain(target ? 2 : (stopOnly || readOnly || scenario == 43 ? 2 : 3),
        target ? targetArgs : (stopOnly ? stopArgs : (readOnly ? readonly : (scenario == 43 ? invalid : run))));
    int expected = 2;
    if (scenario == 0 || scenario == 2 || scenario == 3 || scenario == 4 || scenario == 5 || scenario == 40 || scenario == 44) expected = 0;
    if (scenario == 1 || scenario == 29 || scenario == 45 || scenario == 46) expected = 1;
    if (scenario >= 49 && scenario <= 52) expected = 1;
    if (scenario == 64 || scenario == 65 || scenario==84 || scenario==85) expected = 1;
    if (readOnly) expected = 0;
    if (target) expected = scenario == 30 ? 0 : (scenario == 47 ? 2 : 1);
    expect(actual == expected, "actual client exit reflects the requested route and observed RPC status");
    int ran = scenario == 0 || scenario == 1 || scenario == 2 || scenario == 4 || scenario == 5 || scenario == 29 || scenario == 40 ||
        (scenario >= 49 && scenario <= 52) || scenario == 64 || scenario == 65 || scenario==84 || scenario==85;
    expect(requests == (unsigned)ran, "only explicit valid RUN invokes REQUEST");
    expect(stops == (unsigned)(ran || stopOnly), "RUN errors still STOP; readonly snapshot never STOPs");
    if (ran) expect(observations == 2 && closes == 1 && stopOrder > requestOrder,
        "same connection STOP then independent snapshot even after request error");
    if (stopOnly) expect(observations == 2 && closes == 1 && requests == 0, "STOP-only never issues initialization");
    if (readOnly) expect(observations == 1 && closes == 1 && !requests && !stops, "diagnostic snapshot is read-only");
    if (target) {
        expect(!opens && !requests && !stops, "target preflight never opens control or initializes GPU");
        if (scenario == 47) expect(!enumCalls, "insufficient stack rejected before target enumeration");
        else if (scenario != 38) expect(iterReleased == 1 && iterNext <= 1024,
            "target iterator bounded and released");
        if (scenario == 35) expect(entriesReleased == 1024, "bounded enumeration cannot treat truncation as uniqueness");
    }
    if (scenario == 24 || scenario == 6 || scenario == 7 || scenario == 8 || scenario == 9 || scenario == 39 || scenario == 42 || scenario == 43)
        expect(!opens && !requests && !stops, "bad privilege/build/sysctl/CLI refuses before control open");
    printf("{\"fixture_case\":%u,\"checks\":%u,\"failures\":%u,\"client_exit\":%d,\"requests\":%u,\"stops\":%u,\"observations\":%u,\"expected_preparation_failure\":%u,\"expected_snapshot_bytes\":%u}\n",
        scenario, checks, failures, actual, requests, stops, observations,
        (unsigned)(scenario == 50 ? NV_ERR_TIMEOUT : NV_ERR_NOT_SUPPORTED), (unsigned)sizeof(S540ExperimentalSnapshot));
    return failures ? 1 : 0;
}
