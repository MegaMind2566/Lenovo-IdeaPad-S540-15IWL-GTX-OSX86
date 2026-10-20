/* SPDX-License-Identifier: MIT. Read-only idle loader snapshot controller. */
#include "S540ProspectiveLoaderProtocol.h"
#include <stdio.h>
#include <string.h>

static int valid(const S540ProspectiveSnapshot *s)
{
    return s->format == 1 && s->bytes == sizeof(*s) &&
        s->phase == S540_PROSPECTIVE_CONTROL_STARTED && s->lastStatus == NV_ERR_NOT_READY &&
        s->generation != 0 && s->moduleEntryAccepted == 1 && s->controlServiceStarted == 1 &&
        s->rootRequestConsumed == 0 && s->requestsAccepted == 0 && s->entryPolicyClosed == 1 &&
        s->targetLoaderAdmissionProven == 0 && s->originalCalls == 0 &&
        s->providerPreparations == 0 && s->pmRegistrations == 0 && s->stopping == 0;
}

#if defined(S540_IDLE_CTL_DECODE_CONTROL)
#include "S540ProspectiveLoaderState.h"
int main(void)
{
    S540ProspectiveState state = {0};
    S540ProspectiveSnapshot good, changed;
    unsigned int checks = 0;
    if (s540ProspectiveModuleEnter(&state) != NV_OK || valid(&state.snapshot)) return 1;
    checks++;
    if (s540ProspectiveServiceStart(&state, 17, NV_TRUE) != NV_OK || !valid(&state.snapshot)) return 2;
    checks++;
    good = state.snapshot;
    for (unsigned int i = 0; i < sizeof(good) / sizeof(NvU32); i++) {
        if (i == 4 || i == 5) continue;
        changed = good;
        ((unsigned char *)&changed)[i * sizeof(NvU32)] ^= 1;
        if (valid(&changed)) return 3;
        checks++;
    }
    changed = good; changed.generation = 0;
    if (valid(&changed)) return 4;
    checks++;
    S540ProspectiveRequest request = {1, sizeof(request), good.generation};
    if (s540ProspectiveRequestOnce(&state, NV_TRUE, &request) != NV_ERR_NOT_READY ||
        valid(&state.snapshot) || state.snapshot.originalCalls != 0) return 5;
    checks++;
    printf("{\"status\":\"passed\",\"checks\":%u,\"actual_loader_state\":true}\n", checks);
    return 0;
}
#else
#if !defined(__APPLE__)
#error Operational controller requires native macOS
#endif
#include <IOKit/IOKitLib.h>
#include <CoreFoundation/CoreFoundation.h>
#include <unistd.h>

static int number(io_registry_entry_t entry, const char *key, NvU32 *out)
{
    CFStringRef name = CFStringCreateWithCString(kCFAllocatorDefault, key, kCFStringEncodingUTF8);
    if (!name) return 0;
    CFTypeRef value = IORegistryEntryCreateCFProperty(entry, name, kCFAllocatorDefault, 0);
    CFRelease(name);
    int ok = value && CFGetTypeID(value) == CFDataGetTypeID() &&
        CFDataGetLength((CFDataRef)value) == 4;
    if (ok) {
        const UInt8 *p = CFDataGetBytePtr((CFDataRef)value);
        *out = (NvU32)p[0] | (NvU32)p[1] << 8 | (NvU32)p[2] << 16 | (NvU32)p[3] << 24;
    }
    if (value) CFRelease(value);
    return ok;
}

static int target(void)
{
    io_iterator_t iterator = IO_OBJECT_NULL;
    if (IOServiceGetMatchingServices(kIOMainPortDefault, IOServiceMatching("IOPCIDevice"),
                                    &iterator) != KERN_SUCCESS) return 1;
    unsigned int matches = 0;
    io_registry_entry_t entry;
    while ((entry = IOIteratorNext(iterator))) {
        NvU32 vendor, device, subvendor, subdevice, revision, classcode;
        if (number(entry, "vendor-id", &vendor) && vendor == 0x10de &&
            number(entry, "device-id", &device) && device == 0x1f91 &&
            number(entry, "subsystem-vendor-id", &subvendor) && subvendor == 0x17aa &&
            number(entry, "subsystem-id", &subdevice) && subdevice == 0x3806 &&
            number(entry, "revision-id", &revision) && revision == 0xa1 &&
            number(entry, "class-code", &classcode) && classcode == 0x030000) matches++;
        IOObjectRelease(entry);
    }
    IOObjectRelease(iterator);
    printf("{\"scope\":\"readonly-registry-identity\",\"matches\":%u,"
           "\"vendor\":4318,\"device\":8081,\"subvendor\":6058,\"subdevice\":14342,"
           "\"revision\":161,\"class\":196608,\"hardware_access\":false}\n", matches);
    return matches == 1 ? 0 : 1;
}

static int snapshot(void)
{
    io_service_t service = IOServiceGetMatchingService(kIOMainPortDefault,
        IOServiceMatching("S540ProspectiveLoaderControl"));
    if (!service) return 1;
    uint64_t registry_id = 0;
    io_connect_t connection = IO_OBJECT_NULL;
    kern_return_t identity = IORegistryEntryGetRegistryEntryID(service, &registry_id);
    kern_return_t opened = IOServiceOpen(service, mach_task_self(),
                                        S540_PROSPECTIVE_CONNECTION_TYPE, &connection);
    IOObjectRelease(service);
    if (identity != KERN_SUCCESS || registry_id == 0 || opened != KERN_SUCCESS) {
        if (opened == KERN_SUCCESS) IOServiceClose(connection);
        return 1;
    }
    S540ProspectiveSnapshot s = {0};
    size_t size = sizeof(s);
    kern_return_t result = IOConnectCallStructMethod(connection, S540_PROSPECTIVE_SELECTOR_SNAPSHOT,
                                                    NULL, 0, &s, &size);
    IOServiceClose(connection);
    if (result != KERN_SUCCESS || size != sizeof(s)) return 1;
    printf("{\"format\":%u,\"bytes\":%u,\"phase\":%u,\"last_status\":%u,"
           "\"generation\":%llu,\"module_entry_accepted\":%u,\"control_service_started\":%u,"
           "\"one_shot_consumed\":%u,\"requests_accepted\":%u,\"entry_policy_closed\":%u,"
           "\"target_loader_admission_proven\":%u,\"original_calls\":%u,"
           "\"provider_preparations\":%u,\"pm_registrations\":%u,\"stopping\":%u,"
           "\"actual_registry_entry_id\":%llu,\"generation_matches_registry\":%s,"
           "\"idle_state_valid\":%s}\n", s.format, s.bytes, s.phase, s.lastStatus,
           (unsigned long long)s.generation, s.moduleEntryAccepted, s.controlServiceStarted,
           s.rootRequestConsumed, s.requestsAccepted, s.entryPolicyClosed, s.targetLoaderAdmissionProven,
           s.originalCalls, s.providerPreparations, s.pmRegistrations, s.stopping,
           (unsigned long long)registry_id, s.generation == registry_id ? "true" : "false",
           valid(&s) ? "true" : "false");
    return valid(&s) && s.generation == registry_id ? 0 : 1;
}

int main(int argc, char **argv)
{
    if (geteuid() != 0 || argc != 2) return 64;
    if (!strcmp(argv[1], "--target")) return target();
    if (!strcmp(argv[1], "--snapshot")) return snapshot();
    return 64;
}
#endif
