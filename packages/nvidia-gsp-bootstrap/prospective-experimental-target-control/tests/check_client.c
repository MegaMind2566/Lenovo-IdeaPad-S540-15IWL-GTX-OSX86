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
static void snapshot(S540ExperimentalSnapshot *out) {
    const NvU8 source[32] = S540_EXPERIMENTAL_EXPECTED_SOURCE;
    const NvU8 policy[32] = S540_EXPERIMENTAL_EXPECTED_POLICY;
    const NvU8 native[32] = S540_EXPERIMENTAL_EXPECTED_NATIVE;
    memset(out, 0, sizeof(*out)); out->format = 1; out->bytes = sizeof(*out);
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
    if (scenario == 12) out->format = 2;
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
        snapshot(output); if (scenario == 11) --*outputBytes;
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
        snapshot(output); return scenario == 1 ? kIOReturnError : KERN_SUCCESS;
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
    if (scenario >= 49) return 2;
    if (scenario == 10 || scenario == 47) stackBytes = 8192;
    if (scenario == 40) stackBytes = 32768;
    int target = (scenario >= 30 && scenario <= 38) || scenario == 47 || scenario == 48;
    int stopOnly = scenario >= 44 && scenario <= 46;
    char *run[] = {"experimental_ctl", "--run-once", "--ack-retained-first-initialization"};
    char *readonly[] = {"experimental_ctl", "--snapshot"};
    char *targetArgs[] = {"experimental_ctl", "--target"};
    char *stopArgs[] = {"experimental_ctl", "--stop"};
    char *invalid[] = {"experimental_ctl", "--run-once"};
    int actual = s540ActualClientMain(target ? 2 : (stopOnly || scenario == 3 || scenario == 43 ? 2 : 3),
        target ? targetArgs : (stopOnly ? stopArgs : (scenario == 3 ? readonly : (scenario == 43 ? invalid : run))));
    int expected = 2;
    if (scenario == 0 || scenario == 2 || scenario == 3 || scenario == 4 || scenario == 5 || scenario == 40 || scenario == 44) expected = 0;
    if (scenario == 1 || scenario == 29 || scenario == 45 || scenario == 46) expected = 1;
    if (target) expected = scenario == 30 ? 0 : (scenario == 47 ? 2 : 1);
    expect(actual == expected, "actual client exit reflects the requested route and observed RPC status");
    int ran = scenario == 0 || scenario == 1 || scenario == 2 || scenario == 4 || scenario == 5 || scenario == 29 || scenario == 40;
    expect(requests == (unsigned)ran, "only explicit valid RUN invokes REQUEST");
    expect(stops == (unsigned)(ran || stopOnly), "RUN errors still STOP; readonly snapshot never STOPs");
    if (ran) expect(observations == 2 && closes == 1 && stopOrder > requestOrder,
        "same connection STOP then independent snapshot even after request error");
    if (stopOnly) expect(observations == 2 && closes == 1 && requests == 0, "STOP-only never issues initialization");
    if (target) {
        expect(!opens && !requests && !stops, "target preflight never opens control or initializes GPU");
        if (scenario == 47) expect(!enumCalls, "insufficient stack rejected before target enumeration");
        else if (scenario != 38) expect(iterReleased == 1 && iterNext <= 1024,
            "target iterator bounded and released");
        if (scenario == 35) expect(entriesReleased == 1024, "bounded enumeration cannot treat truncation as uniqueness");
    }
    if (scenario == 24 || scenario == 6 || scenario == 7 || scenario == 8 || scenario == 9 || scenario == 39 || scenario == 42 || scenario == 43)
        expect(!opens && !requests && !stops, "bad privilege/build/sysctl/CLI refuses before control open");
    printf("{\"fixture_case\":%u,\"checks\":%u,\"failures\":%u,\"client_exit\":%d,\"requests\":%u,\"stops\":%u,\"observations\":%u}\n",
        scenario, checks, failures, actual, requests, stops, observations);
    return failures ? 1 : 0;
}
