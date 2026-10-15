/*
 * Read only the S540NvidiaPCIProbe snapshot and its direct provider identity.
 * No IOServiceOpen, PCI configuration access, BAR mapping, MMIO, DMA, writes,
 * firmware operations, or administrator privileges are used by this program.
 *
 * Build: clang -arch x86_64 -std=c11 -Wall -Wextra -Werror -O2 \
 *   check_nvidia_transport.c -framework IOKit -framework CoreFoundation \
 *   -o check-nvidia-transport
 */
#include <CoreFoundation/CoreFoundation.h>
#include <IOKit/IOKitLib.h>
#include <inttypes.h>
#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define TOOL_VERSION "0.3.0"
#define PROBE_CLASS "S540NvidiaPCIProbe"
#define SNAPSHOT_KEY "S540NvidiaPCIProbeSnapshot"
#define ACCESS_POLICY "two-read-only-bar0-hal-identification"
#define LEGACY_MMIO_ACCESS_POLICY "single-read-only-bar0-identification"
#define NVIDIA_SOURCE_COMMIT "1a82fbfda8f321b056eb3568850f9316c5e465c5"
#define LEGACY_ACCESS_POLICY "config-read-and-resource-metadata-only"
#define BAR_COUNT 6
#define MAX_SERVICES 8
#define MAX_BOOT_ARGUMENT_BYTES 4096

struct bar_descriptor {
    uint8_t reg;
    int present;
    uint64_t address;
    uint64_t length;
};

enum mmio_status { MMIO_REFUSED, MMIO_FAILED, MMIO_IDENTIFIED, MMIO_NOT_ATTEMPTED };

struct mmio_result {
    enum mmio_status status;
    size_t reason;
    uint32_t read_count;
    uint32_t raw_value;
    uint32_t architecture;
    uint32_t implementation;
    uint32_t chip_id;
};

static const char *const mmio_reasons[] = {
    "resource-metadata-unavailable", "bar0-descriptor-missing",
    "pci-identity-changed", "pci-config-unavailable",
    "memory-decoding-disabled", "bar0-configuration-invalid",
    "bar0-descriptor-invalid", "pm-capability-unavailable",
    "pm-capability-malformed", "pm-capability-unsupported", "pci-not-d0",
    "mapping-unavailable", "mapping-invalid",
    "provider-arbitration-unavailable", "provider-already-open",
    "zero-value", "all-ones-value", "architecture-mismatch",
    "implementation-mismatch", "tu117-identified"
};
#define MMIO_REFUSAL_COUNT 15
#define MMIO_REASON_COUNT (sizeof(mmio_reasons) / sizeof(mmio_reasons[0]))

struct snapshot {
    uint32_t format;
    char probe_version[32];
    uint16_t vendor;
    uint16_t device;
    uint16_t subsystem_vendor;
    uint16_t subsystem;
    uint8_t revision;
    uint32_t class_code;
    uint16_t command;
    uint16_t status;
    struct bar_descriptor bars[BAR_COUNT];
    int bars_available;
    struct mmio_result mmio;
    struct mmio_result boot42;
    int hal_matched;
    uint32_t total_read_count;
};

enum warning_code {
    WARN_MATCHING_ALLOCATION,
    WARN_ENUMERATION_FAILED,
    WARN_ENUMERATION_INVALIDATED,
    WARN_SERVICE_LIMIT,
    WARN_MULTIPLE_SERVICES,
    WARN_SERVICE_CLASS,
    WARN_PROVIDER_LOOKUP,
    WARN_PROVIDER_CLASS,
    WARN_PROVIDER_IDENTITY,
    WARN_SNAPSHOT_INVALID,
    WARN_CONTEXT_UNREADABLE,
    WARNING_COUNT
};

static const char *const warning_names[WARNING_COUNT] = {
    "matching_allocation_failed", "enumeration_failed",
    "enumeration_invalidated", "service_limit_reached",
    "multiple_probe_services", "unexpected_probe_class",
    "direct_provider_unavailable", "unexpected_direct_provider_class",
    "direct_provider_identity_mismatch", "snapshot_missing_or_invalid",
    "boot_argument_context_unreadable"
};

struct report {
    struct snapshot snapshot;
    size_t services;
    int attached;
    int outdated;
    int complete;
    int wegnoegpu_known;
    int wegnoegpu_present;
    unsigned int warnings[WARNING_COUNT];
};

static void warn_report(struct report *report, enum warning_code code,
                        int incomplete)
{
    if (report->warnings[code] != UINT_MAX)
        ++report->warnings[code];
    if (incomplete)
        report->complete = 0;
}

static int has_boot_token(const char *arguments, const char *token)
{
    size_t wanted = strlen(token);
    const char *p = arguments;
    while (*p != '\0') {
        p += strspn(p, " \t\r\n\v\f");
        size_t length = strcspn(p, " \t\r\n\v\f");
        /* XNU leading-dash flags remain present with an =value suffix. */
        if (length >= wanted && memcmp(p, token, wanted) == 0 &&
            (length == wanted || p[wanted] == '='))
            return 1;
        p += length;
    }
    return 0;
}

/* Snapshot values must be integral CFNumbers, never booleans or raw bytes. */
static int decode_number(CFTypeRef object, uint64_t maximum, uint64_t *result)
{
    int64_t signed_value = 0;
    if (object == NULL || CFGetTypeID(object) != CFNumberGetTypeID() ||
        CFNumberIsFloatType((CFNumberRef)object) ||
        !CFNumberGetValue((CFNumberRef)object, kCFNumberSInt64Type,
                          &signed_value) || signed_value < 0 ||
        (uint64_t)signed_value > maximum)
        return 0;
    *result = (uint64_t)signed_value;
    return 1;
}

static int dictionary_number(CFDictionaryRef dictionary, CFStringRef key,
                              uint64_t maximum, uint64_t *result)
{
    return decode_number(CFDictionaryGetValue(dictionary, key), maximum, result);
}

static int exact_string(CFTypeRef object, CFStringRef expected)
{
    return object != NULL && CFGetTypeID(object) == CFStringGetTypeID() &&
           CFEqual(object, expected);
}

static int decode_version(CFTypeRef object, char *version, size_t capacity)
{
    if (object == NULL || CFGetTypeID(object) != CFStringGetTypeID() ||
        CFStringGetLength((CFStringRef)object) == 0 ||
        CFStringGetLength((CFStringRef)object) >= (CFIndex)capacity ||
        !CFStringGetCString((CFStringRef)object, version, (CFIndex)capacity,
                             kCFStringEncodingASCII) ||
        strlen(version) != (size_t)CFStringGetLength((CFStringRef)object))
        return 0;
    for (const unsigned char *p = (const unsigned char *)version; *p; ++p)
        if (!(*p >= '0' && *p <= '9') && *p != '.')
            return 0;
    return 1;
}

/* Fixed keys, integral types, and result-specific fields form the wire contract. */
static int decode_mmio(CFTypeRef object, struct mmio_result *output)
{
    struct mmio_result candidate;
    memset(&candidate, 0, sizeof(candidate));
    if (object == NULL || CFGetTypeID(object) != CFDictionaryGetTypeID())
        return 0;
    CFDictionaryRef dictionary = (CFDictionaryRef)object;
    uint64_t value = 0;
    if (!dictionary_number(dictionary, CFSTR("ReadCount"), 1, &value))
        return 0;
    candidate.read_count = (uint32_t)value;
    if (CFDictionaryGetCount(dictionary) != (candidate.read_count ? 9 : 6) ||
        !dictionary_number(dictionary, CFSTR("BarIndex"), 0, &value) ||
        !dictionary_number(dictionary, CFSTR("Offset"), 0, &value) ||
        !dictionary_number(dictionary, CFSTR("Width"), 32, &value) || value != 32)
        return 0;
    char reason[64];
    CFTypeRef reason_object = CFDictionaryGetValue(dictionary, CFSTR("Reason"));
    if (reason_object == NULL || CFGetTypeID(reason_object) != CFStringGetTypeID() ||
        !CFStringGetCString((CFStringRef)reason_object, reason, sizeof(reason),
                            kCFStringEncodingASCII) ||
        strlen(reason) != (size_t)CFStringGetLength((CFStringRef)reason_object))
        return 0;
    int reason_found = 0;
    for (size_t index = 0; index < MMIO_REASON_COUNT; ++index) {
        if (strcmp(reason, mmio_reasons[index]) == 0) {
            candidate.reason = index;
            reason_found = 1;
            break;
        }
    }
    if (!reason_found)
        return 0;
    if (candidate.reason < MMIO_REFUSAL_COUNT) {
        if (candidate.read_count != 0 ||
            !exact_string(CFDictionaryGetValue(dictionary, CFSTR("Status")),
                           CFSTR("refused")))
            return 0;
        candidate.status = MMIO_REFUSED;
    } else {
        if (candidate.read_count != 1 ||
            !dictionary_number(dictionary, CFSTR("RawValue"), UINT32_MAX, &value))
            return 0;
        candidate.raw_value = (uint32_t)value;
        if (!dictionary_number(dictionary, CFSTR("Architecture"), 0x3f, &value))
            return 0;
        candidate.architecture = (uint32_t)value;
        if (!dictionary_number(dictionary, CFSTR("Implementation"), 0xf, &value))
            return 0;
        candidate.implementation = (uint32_t)value;
        uint32_t raw = candidate.raw_value;
        if (candidate.architecture != ((((raw >> 8) & 1U) << 5) |
                                       ((raw >> 24) & 0x1fU)) ||
            candidate.implementation != ((raw >> 20) & 0xfU))
            return 0;
        size_t expected_reason;
        if (raw == 0)
            expected_reason = MMIO_REFUSAL_COUNT;
        else if (raw == UINT32_MAX)
            expected_reason = MMIO_REFUSAL_COUNT + 1;
        else if (candidate.architecture != 0x16)
            expected_reason = MMIO_REFUSAL_COUNT + 2;
        else if (candidate.implementation != 7)
            expected_reason = MMIO_REFUSAL_COUNT + 3;
        else
            expected_reason = MMIO_REFUSAL_COUNT + 4;
        if (candidate.reason != expected_reason)
            return 0;
        int identified = expected_reason == MMIO_REFUSAL_COUNT + 4;
        if (!exact_string(CFDictionaryGetValue(dictionary, CFSTR("Status")),
                           identified ? CFSTR("identified") : CFSTR("failed")))
            return 0;
        candidate.status = identified ? MMIO_IDENTIFIED : MMIO_FAILED;
    }
    *output = candidate;
    return 1;
}

/* BOOT42 has its own architecture encoding and must not reuse BOOT0 masks. */
static int decode_boot42(CFTypeRef object, const struct mmio_result *boot0,
                         struct mmio_result *output)
{
    struct mmio_result candidate;
    memset(&candidate, 0, sizeof(candidate));
    if (object == NULL || CFGetTypeID(object) != CFDictionaryGetTypeID())
        return 0;
    CFDictionaryRef dictionary = (CFDictionaryRef)object;
    uint64_t value = 0;
    if (!dictionary_number(dictionary, CFSTR("ReadCount"), 1, &value))
        return 0;
    candidate.read_count = (uint32_t)value;
    if (CFDictionaryGetCount(dictionary) != (candidate.read_count ? 10 : 6) ||
        !dictionary_number(dictionary, CFSTR("BarIndex"), 0, &value) ||
        !dictionary_number(dictionary, CFSTR("Offset"), 0xa00, &value) || value != 0xa00 ||
        !dictionary_number(dictionary, CFSTR("Width"), 32, &value) || value != 32)
        return 0;
    CFTypeRef reason_object = CFDictionaryGetValue(dictionary, CFSTR("Reason"));
    CFTypeRef status_object = CFDictionaryGetValue(dictionary, CFSTR("Status"));
    if (boot0->status != MMIO_IDENTIFIED) {
        if (candidate.read_count != 0 ||
            !exact_string(status_object, CFSTR("not_attempted")) ||
            !exact_string(reason_object, CFSTR("boot0-not-identified")))
            return 0;
        candidate.status = MMIO_NOT_ATTEMPTED;
        candidate.reason = MMIO_REASON_COUNT;
        *output = candidate;
        return 1;
    }
    char reason[64];
    if (reason_object == NULL || CFGetTypeID(reason_object) != CFStringGetTypeID() ||
        !CFStringGetCString((CFStringRef)reason_object, reason, sizeof(reason),
                            kCFStringEncodingASCII) ||
        strlen(reason) != (size_t)CFStringGetLength((CFStringRef)reason_object))
        return 0;
    int found = 0;
    for (size_t index = 0; index < MMIO_REASON_COUNT; ++index) {
        if (strcmp(reason, mmio_reasons[index]) == 0) {
            candidate.reason = index;
            found = 1;
            break;
        }
    }
    if (!found)
        return 0;
    if (candidate.reason < MMIO_REFUSAL_COUNT) {
        if (candidate.reason == 0 || candidate.reason == 1 ||
            candidate.reason == 13 || candidate.reason == 14 ||
            candidate.read_count != 0 || !exact_string(status_object, CFSTR("refused")))
            return 0;
        candidate.status = MMIO_REFUSED;
    } else {
        if (candidate.read_count != 1 ||
            !dictionary_number(dictionary, CFSTR("RawValue"), UINT32_MAX, &value))
            return 0;
        candidate.raw_value = (uint32_t)value;
        if (!dictionary_number(dictionary, CFSTR("Architecture"), 0x3f, &value))
            return 0;
        candidate.architecture = (uint32_t)value;
        if (!dictionary_number(dictionary, CFSTR("Implementation"), 0xf, &value))
            return 0;
        candidate.implementation = (uint32_t)value;
        if (!dictionary_number(dictionary, CFSTR("ChipID"), 0x3ff, &value))
            return 0;
        candidate.chip_id = (uint32_t)value;
        uint32_t raw = candidate.raw_value;
        if (candidate.architecture != ((raw >> 24) & 0x3fU) ||
            candidate.implementation != ((raw >> 20) & 0xfU) ||
            candidate.chip_id != ((raw >> 20) & 0x3ffU))
            return 0;
        size_t expected_reason;
        if (raw == 0)
            expected_reason = MMIO_REFUSAL_COUNT;
        else if (raw == UINT32_MAX)
            expected_reason = MMIO_REFUSAL_COUNT + 1;
        else if (candidate.architecture != 0x16)
            expected_reason = MMIO_REFUSAL_COUNT + 2;
        else if (candidate.implementation != 7)
            expected_reason = MMIO_REFUSAL_COUNT + 3;
        else
            expected_reason = MMIO_REFUSAL_COUNT + 4;
        if (candidate.reason != expected_reason)
            return 0;
        int identified = expected_reason == MMIO_REFUSAL_COUNT + 4;
        if (!exact_string(status_object, identified ? CFSTR("identified") : CFSTR("failed")))
            return 0;
        candidate.status = identified ? MMIO_IDENTIFIED : MMIO_FAILED;
    }
    *output = candidate;
    return 1;
}

/* Selection is a local identity table match, not a running NVIDIA HAL. */
static int decode_hal(CFTypeRef object, struct snapshot *snapshot)
{
    if (object == NULL || CFGetTypeID(object) != CFDictionaryGetTypeID())
        return 0;
    CFDictionaryRef dictionary = (CFDictionaryRef)object;
    uint64_t count = 0;
    if (!dictionary_number(dictionary, CFSTR("TotalReadCount"), 2, &count) ||
        count != snapshot->mmio.read_count + snapshot->boot42.read_count ||
        !exact_string(CFDictionaryGetValue(dictionary, CFSTR("SourceCommit")),
                       CFSTR(NVIDIA_SOURCE_COMMIT)))
        return 0;
    int matched = snapshot->mmio.status == MMIO_IDENTIFIED &&
                  snapshot->boot42.status == MMIO_IDENTIFIED &&
                  snapshot->mmio.architecture == snapshot->boot42.architecture &&
                  snapshot->mmio.implementation == snapshot->boot42.implementation &&
                  snapshot->boot42.chip_id == 0x167;
    if (CFDictionaryGetCount(dictionary) != (matched ? 5 : 3) ||
        !exact_string(CFDictionaryGetValue(dictionary, CFSTR("Status")),
                       matched ? CFSTR("matched") : CFSTR("not_selected")))
        return 0;
    if (matched) {
        uint64_t variant = 0;
        if (!exact_string(CFDictionaryGetValue(dictionary, CFSTR("Chip")), CFSTR("TU117")) ||
            !dictionary_number(dictionary, CFSTR("VariantIndex"), 41, &variant) || variant != 41)
            return 0;
    }
    snapshot->hal_matched = matched;
    snapshot->total_read_count = (uint32_t)count;
    return 1;
}

/* Legacy format is decoded only to identify an old loaded kext, never emitted. */
static int decode_snapshot(CFTypeRef object, struct snapshot *output)
{
    struct snapshot candidate;
    memset(&candidate, 0, sizeof(candidate));
    if (object == NULL || CFGetTypeID(object) != CFDictionaryGetTypeID())
        return 0;
    CFDictionaryRef dictionary = (CFDictionaryRef)object;
    uint64_t value = 0;
    if (!dictionary_number(dictionary, CFSTR("Format"), 3, &value) ||
        (value != 1 && value != 2 && value != 3))
        return 0;
    candidate.format = (uint32_t)value;
    int legacy = candidate.format == 1;
    int current = candidate.format == 3;
    if (!exact_string(CFDictionaryGetValue(dictionary, CFSTR("Stage")),
                       CFSTR("attached")) ||
        !exact_string(CFDictionaryGetValue(dictionary, CFSTR("AccessPolicy")),
                       legacy ? CFSTR(LEGACY_ACCESS_POLICY) : current ? CFSTR(ACCESS_POLICY) :
                                CFSTR(LEGACY_MMIO_ACCESS_POLICY)) ||
        !decode_version(CFDictionaryGetValue(dictionary, CFSTR("ProbeVersion")),
                         candidate.probe_version,
                         sizeof(candidate.probe_version)) ||
        strcmp(candidate.probe_version, legacy ? "0.1.0" : current ? TOOL_VERSION : "0.2.0") != 0)
        return 0;
    if (!legacy && !decode_mmio(CFDictionaryGetValue(dictionary, CFSTR("MMIOResult")),
                                &candidate.mmio))
        return 0;
    if (current &&
        (!decode_boot42(CFDictionaryGetValue(dictionary, CFSTR("BOOT42Result")),
                          &candidate.mmio, &candidate.boot42) ||
         !decode_hal(CFDictionaryGetValue(dictionary, CFSTR("HALSelection")), &candidate)))
        return 0;
    int missing_bars_allowed = !legacy && candidate.mmio.status == MMIO_REFUSED &&
                              candidate.mmio.reason == 0;
    CFIndex expected_keys = legacy ? 13 : current ? 16 : 14;
    if (missing_bars_allowed)
        --expected_keys;
    if (CFDictionaryGetCount(dictionary) != expected_keys)
        return 0;
#define READ_FIELD(KEY, MAXIMUM, FIELD) do { \
    if (!dictionary_number(dictionary, CFSTR(KEY), (MAXIMUM), &value)) \
        return 0; \
    candidate.FIELD = value; \
} while (0)
    READ_FIELD("VendorID", UINT16_MAX, vendor);
    READ_FIELD("DeviceID", UINT16_MAX, device);
    READ_FIELD("SubsystemVendorID", UINT16_MAX, subsystem_vendor);
    READ_FIELD("SubsystemID", UINT16_MAX, subsystem);
    READ_FIELD("RevisionID", UINT8_MAX, revision);
    READ_FIELD("ClassCode", UINT32_C(0xffffff), class_code);
    READ_FIELD("Command", UINT16_MAX, command);
    READ_FIELD("Status", UINT16_MAX, status);
#undef READ_FIELD
    if (candidate.vendor != 0x10de || candidate.device != 0x1f91 ||
        candidate.subsystem_vendor != 0x17aa || candidate.subsystem != 0x3806 ||
        candidate.revision != 0xa1 || candidate.class_code != 0x030000)
        return 0;
    CFTypeRef bars_object = CFDictionaryGetValue(dictionary, CFSTR("BARDescriptors"));
    if (missing_bars_allowed) {
        if (bars_object != NULL)
            return 0;
        *output = candidate;
        return 1;
    }
    if (bars_object == NULL || CFGetTypeID(bars_object) != CFArrayGetTypeID() ||
        CFArrayGetCount((CFArrayRef)bars_object) != BAR_COUNT)
        return 0;
    candidate.bars_available = 1;
    for (CFIndex index = 0; index < BAR_COUNT; ++index) {
        CFTypeRef bar_object = CFArrayGetValueAtIndex((CFArrayRef)bars_object, index);
        if (bar_object == NULL || CFGetTypeID(bar_object) != CFDictionaryGetTypeID())
            return 0;
        CFDictionaryRef bar = (CFDictionaryRef)bar_object;
        struct bar_descriptor *descriptor = &candidate.bars[index];
        if (!dictionary_number(bar, CFSTR("Register"), UINT8_MAX, &value) ||
            value != (uint64_t)(0x10 + 4 * index))
            return 0;
        descriptor->reg = (uint8_t)value;
        CFTypeRef present = CFDictionaryGetValue(bar, CFSTR("Present"));
        if (present == NULL || CFGetTypeID(present) != CFBooleanGetTypeID())
            return 0;
        descriptor->present = CFBooleanGetValue((CFBooleanRef)present);
        if (CFDictionaryGetCount(bar) != (descriptor->present ? 4 : 2))
            return 0;
        if (descriptor->present &&
            (!dictionary_number(bar, CFSTR("Address"), INT64_MAX,
                                  &descriptor->address) ||
             !dictionary_number(bar, CFSTR("Length"), INT64_MAX,
                                  &descriptor->length) ||
             descriptor->length == 0 ||
             descriptor->address > UINT64_MAX - (descriptor->length - 1)))
            return 0;
    }
    if (!legacy && candidate.mmio.reason == 1 && candidate.bars[0].present)
        return 0;
    if (!legacy && candidate.mmio.read_count == 1 &&
        (!candidate.bars[0].present || candidate.bars[0].address == 0 ||
         candidate.bars[0].length != UINT64_C(0x01000000) ||
         (candidate.bars[0].address & UINT64_C(0x00ffffff)) != 0))
        return 0;
    *output = candidate;
    return 1;
}

/* PCI identity properties can also use the standard four little-endian bytes. */
static int decode_provider_id(CFTypeRef object, uint16_t *result)
{
    uint64_t value = 0;
    if (object == NULL)
        return 0;
    if (CFGetTypeID(object) == CFDataGetTypeID()) {
        if (CFDataGetLength((CFDataRef)object) != 4)
            return 0;
        const UInt8 *bytes = CFDataGetBytePtr((CFDataRef)object);
        value = (uint64_t)bytes[0] | ((uint64_t)bytes[1] << 8) |
                ((uint64_t)bytes[2] << 16) | ((uint64_t)bytes[3] << 24);
        if (value > UINT16_MAX)
            return 0;
    } else if (!decode_number(object, UINT16_MAX, &value)) {
        return 0;
    }
    *result = (uint16_t)value;
    return 1;
}

static int provider_id_equals(io_registry_entry_t provider, CFStringRef key,
                               uint16_t expected)
{
    CFTypeRef object = IORegistryEntryCreateCFProperty(provider, key,
                                                       kCFAllocatorDefault, 0);
    uint16_t actual = 0;
    int valid = decode_provider_id(object, &actual);
    if (object != NULL)
        CFRelease(object);
    return valid && actual == expected;
}

static int exact_class(io_object_t object, const char *expected)
{
    io_name_t name;
    memset(name, 0, sizeof(name));
    return IOObjectGetClass(object, name) == KERN_SUCCESS &&
           memchr(name, '\0', sizeof(name)) != NULL &&
           strcmp(name, expected) == 0;
}

static void read_probe(io_registry_entry_t service, struct report *report)
{
    if (!exact_class(service, PROBE_CLASS)) {
        warn_report(report, WARN_SERVICE_CLASS, 1);
        return;
    }
    io_registry_entry_t provider = IO_OBJECT_NULL;
    if (IORegistryEntryGetParentEntry(service, kIOServicePlane, &provider) !=
        KERN_SUCCESS || provider == IO_OBJECT_NULL) {
        warn_report(report, WARN_PROVIDER_LOOKUP, 1);
        return;
    }
    int valid = 1;
    if (!exact_class(provider, "IOPCIDevice")) {
        warn_report(report, WARN_PROVIDER_CLASS, 1);
        valid = 0;
    } else if (!provider_id_equals(provider, CFSTR("vendor-id"), 0x10de) ||
               !provider_id_equals(provider, CFSTR("device-id"), 0x1f91) ||
               !provider_id_equals(provider, CFSTR("subsystem-vendor-id"),
                                     0x17aa) ||
               !provider_id_equals(provider, CFSTR("subsystem-id"), 0x3806)) {
        warn_report(report, WARN_PROVIDER_IDENTITY, 1);
        valid = 0;
    }
    IOObjectRelease(provider);
    if (!valid)
        return;
    CFTypeRef object = IORegistryEntryCreateCFProperty(service,
        CFSTR(SNAPSHOT_KEY), kCFAllocatorDefault, 0);
    valid = decode_snapshot(object, &report->snapshot);
    if (object != NULL)
        CFRelease(object);
    if (!valid) {
        warn_report(report, WARN_SNAPSHOT_INVALID, 1);
        return;
    }
    report->attached = 1;
    report->outdated = report->snapshot.format < 3;
}

static void read_context(struct report *report)
{
    io_registry_entry_t chosen = IORegistryEntryFromPath(
        kIOMainPortDefault, "IODeviceTree:/chosen");
    if (chosen == IO_OBJECT_NULL) {
        warn_report(report, WARN_CONTEXT_UNREADABLE, 0);
        return;
    }
    CFTypeRef object = IORegistryEntryCreateCFProperty(chosen,
        CFSTR("boot-args"), kCFAllocatorDefault, 0);
    IOObjectRelease(chosen);
    char arguments[MAX_BOOT_ARGUMENT_BYTES];
    memset(arguments, 0, sizeof(arguments));
    int valid = 0;
    if (object != NULL && CFGetTypeID(object) == CFStringGetTypeID()) {
        valid = CFStringGetCString((CFStringRef)object, arguments,
                                    sizeof(arguments), kCFStringEncodingUTF8);
    } else if (object != NULL && CFGetTypeID(object) == CFDataGetTypeID()) {
        CFIndex length = CFDataGetLength((CFDataRef)object);
        if (length >= 0 && (uint64_t)length < sizeof(arguments)) {
            if (length > 0)
                memcpy(arguments, CFDataGetBytePtr((CFDataRef)object),
                         (size_t)length);
            const char *first_nul = memchr(arguments, '\0', (size_t)length);
            valid = first_nul == NULL || first_nul == arguments + length - 1;
        }
    }
    if (object != NULL)
        CFRelease(object);
    if (valid) {
        report->wegnoegpu_known = 1;
        report->wegnoegpu_present = has_boot_token(arguments, "-wegnoegpu");
    } else {
        warn_report(report, WARN_CONTEXT_UNREADABLE, 0);
    }
    memset(arguments, 0, sizeof(arguments));
}

static void collect_report(struct report *report)
{
    read_context(report);
    CFMutableDictionaryRef matching = IOServiceMatching(PROBE_CLASS);
    if (matching == NULL) {
        warn_report(report, WARN_MATCHING_ALLOCATION, 1);
        return;
    }
    io_iterator_t iterator = IO_OBJECT_NULL;
    if (IOServiceGetMatchingServices(kIOMainPortDefault, matching, &iterator) !=
        KERN_SUCCESS) {
        warn_report(report, WARN_ENUMERATION_FAILED, 1);
        return;
    }
    /* XNU can return success with no iterator when no service class matches.
       A null handle is an empty result, not an invalidated live iterator. */
    if (iterator == IO_OBJECT_NULL)
        return;
    io_registry_entry_t service;
    while ((service = IOIteratorNext(iterator)) != IO_OBJECT_NULL) {
        ++report->services;
        if (report->services > MAX_SERVICES) {
            IOObjectRelease(service);
            warn_report(report, WARN_SERVICE_LIMIT, 1);
            break;
        }
        if (report->services == 1)
            read_probe(service, report);
        IOObjectRelease(service);
    }
    if (!IOIteratorIsValid(iterator))
        warn_report(report, WARN_ENUMERATION_INVALIDATED, 1);
    IOObjectRelease(iterator);
    if (report->services > 1) {
        warn_report(report, WARN_MULTIPLE_SERVICES, 1);
        report->attached = 0;
    }
}

static void write_boot42(FILE *out, const struct mmio_result *result)
{
    const char *status = result->status == MMIO_IDENTIFIED ? "identified" :
                         result->status == MMIO_FAILED ? "failed" :
                         result->status == MMIO_REFUSED ? "refused" : "not_attempted";
    const char *reason = result->status == MMIO_NOT_ATTEMPTED ? "boot0-not-identified" :
                         mmio_reasons[result->reason];
    fprintf(out, "{\"status\":\"%s\",\"reason\":\"%s\",\"read_count\":%" PRIu32
        ",\"bar_index\":0,\"offset\":2560,\"width_bits\":32", status, reason, result->read_count);
    if (result->read_count)
        fprintf(out, ",\"raw_value\":\"0x%08" PRIx32 "\",\"architecture\":\"0x%02" PRIx32
            "\",\"implementation\":\"0x%02" PRIx32 "\",\"chip_id\":\"0x%03" PRIx32 "\"",
            result->raw_value, result->architecture, result->implementation, result->chip_id);
    fputc('}', out);
}

static void write_snapshot(FILE *out, const struct snapshot *snapshot)
{
    /* All strings here are constants or the ASCII digits/dots version. */
    fprintf(out, "{\"format\":%" PRIu32 ",\"probe_version\":\"%s\","
        "\"stage\":\"attached\",\"access_policy\":\"%s\","
        "\"identity\":{\"vendor_id\":\"0x%04x\",\"device_id\":\"0x%04x\","
        "\"subsystem_vendor_id\":\"0x%04x\",\"subsystem_device_id\":\"0x%04x\","
        "\"revision_id\":\"0x%02x\",\"class_code\":\"0x%06" PRIx32 "\"},"
        "\"command\":\"0x%04x\",\"status\":\"0x%04x\",\"bars\":[",
        snapshot->format, snapshot->probe_version, ACCESS_POLICY,
        (unsigned int)snapshot->vendor, (unsigned int)snapshot->device,
        (unsigned int)snapshot->subsystem_vendor,
        (unsigned int)snapshot->subsystem, (unsigned int)snapshot->revision,
        snapshot->class_code, (unsigned int)snapshot->command,
        (unsigned int)snapshot->status);
    for (size_t index = 0; snapshot->bars_available && index < BAR_COUNT; ++index) {
        const struct bar_descriptor *bar = &snapshot->bars[index];
        if (index)
            fputc(',', out);
        fprintf(out, "{\"register\":\"0x%02x\",\"present\":%s",
            (unsigned int)bar->reg, bar->present ? "true" : "false");
        if (bar->present)
            fprintf(out, ",\"address\":\"0x%016" PRIx64 "\","
                "\"length_bytes\":%" PRIu64, bar->address, bar->length);
        fputc('}', out);
    }
    fputs("],\"mmio\":{\"status\":\"", out);
    const struct mmio_result *mmio = &snapshot->mmio;
    fputs(mmio->status == MMIO_IDENTIFIED ? "identified" :
          mmio->status == MMIO_REFUSED ? "refused" : "failed", out);
    fprintf(out, "\",\"reason\":\"%s\",\"read_count\":%" PRIu32
        ",\"bar_index\":0,\"offset\":0,\"width_bits\":32", mmio_reasons[mmio->reason],
        mmio->read_count);
    if (mmio->read_count)
        fprintf(out, ",\"raw_value\":\"0x%08" PRIx32 "\",\"architecture\":\"0x%02" PRIx32
            "\",\"implementation\":\"0x%02" PRIx32 "\"", mmio->raw_value,
            mmio->architecture, mmio->implementation);
    fputs("},\"boot42\":", out);
    write_boot42(out, &snapshot->boot42);
    fprintf(out, ",\"hal_selection\":{\"status\":\"%s\",\"total_read_count\":%" PRIu32
        ",\"source_commit\":\"" NVIDIA_SOURCE_COMMIT "\"", snapshot->hal_matched ? "matched" : "not_selected",
        snapshot->total_read_count);
    if (snapshot->hal_matched)
        fputs(",\"chip\":\"TU117\",\"variant_index\":41", out);
    fputs("}}", out);
}

static const char *report_status(const struct report *report)
{
    if (!report->complete)
        return "error";
    if (report->outdated)
        return "outdated_probe";
    if (!report->attached)
        return "not_attached";
    if (report->snapshot.hal_matched)
        return "hal_matched";
    return report->snapshot.mmio.status == MMIO_REFUSED ||
           report->snapshot.boot42.status == MMIO_REFUSED ? "refused" : "failed";
}

static int report_exit_code(const struct report *report)
{
    return report->complete && (!report->attached || report->outdated ||
        (report->snapshot.mmio.status != MMIO_FAILED &&
         report->snapshot.boot42.status != MMIO_FAILED)) ? 0 : 1;
}

static void write_report(FILE *out, const struct report *report)
{
    fprintf(out, "{\"format\":3,\"tool\":\"nvidia-transport\",\"version\":\"%s\","
        "\"target\":{\"vendor_id\":\"0x10de\",\"device_id\":\"0x1f91\","
        "\"subsystem_vendor_id\":\"0x17aa\",\"subsystem_device_id\":\"0x3806\"},"
        "\"status\":\"%s\",\"complete\":%s,"
        "\"context\":{\"wegnoegpu_present\":%s},\"probe\":",
        TOOL_VERSION, report_status(report),
        report->complete ? "true" : "false",
        !report->wegnoegpu_known ? "null" :
            report->wegnoegpu_present ? "true" : "false");
    if (report->attached && report->complete && !report->outdated) {
        fputs("{\"service_class\":\"" PROBE_CLASS "\","
              "\"provider_class\":\"IOPCIDevice\","
              "\"provider_identity_verified\":true,\"snapshot\":", out);
        write_snapshot(out, &report->snapshot);
        fputc('}', out);
    } else {
        fputs("null", out);
    }
    fputs(",\"reason\":", out);
    fputs(report->outdated ? "\"The loaded probe is an older version. Replace the kext on the EFI used for this boot with version 0.3.0.\"" : "null", out);
    fputs(",\"warnings\":[", out);
    int emitted = 0;
    for (size_t index = 0; index < WARNING_COUNT; ++index) {
        if (!report->warnings[index])
            continue;
        if (emitted++)
            fputc(',', out);
        fprintf(out, "{\"code\":\"%s\",\"count\":%u}", warning_names[index],
                  report->warnings[index]);
    }
    fputs("]}\n", out);
}

static void fixture_number(CFMutableDictionaryRef dictionary, CFStringRef key,
                            int64_t value)
{
    CFNumberRef number = CFNumberCreate(kCFAllocatorDefault,
                                         kCFNumberSInt64Type, &value);
    if (number == NULL) {
        fputs("Self-test allocation failed.\n", stderr);
        exit(1);
    }
    CFDictionarySetValue(dictionary, key, number);
    CFRelease(number);
}

static CFMutableDictionaryRef fixture_mmio(const char *status, const char *reason,
                                          int read_count, uint32_t raw)
{
    CFMutableDictionaryRef mmio = CFDictionaryCreateMutable(kCFAllocatorDefault,
        0, &kCFTypeDictionaryKeyCallBacks, &kCFTypeDictionaryValueCallBacks);
    CFStringRef status_value = CFStringCreateWithCString(kCFAllocatorDefault,
        status, kCFStringEncodingASCII);
    CFStringRef reason_value = CFStringCreateWithCString(kCFAllocatorDefault,
        reason, kCFStringEncodingASCII);
    if (mmio == NULL || status_value == NULL || reason_value == NULL) {
        fputs("Self-test allocation failed.\n", stderr);
        exit(1);
    }
    CFDictionarySetValue(mmio, CFSTR("Status"), status_value);
    CFDictionarySetValue(mmio, CFSTR("Reason"), reason_value);
    CFRelease(status_value);
    CFRelease(reason_value);
    fixture_number(mmio, CFSTR("ReadCount"), read_count);
    fixture_number(mmio, CFSTR("BarIndex"), 0);
    fixture_number(mmio, CFSTR("Offset"), 0);
    fixture_number(mmio, CFSTR("Width"), 32);
    if (read_count) {
        fixture_number(mmio, CFSTR("RawValue"), raw);
        fixture_number(mmio, CFSTR("Architecture"), (((raw >> 8) & 1U) << 5) |
                                                     ((raw >> 24) & 0x1fU));
        fixture_number(mmio, CFSTR("Implementation"), (raw >> 20) & 0xfU);
    }
    return mmio;
}

static CFMutableDictionaryRef fixture_boot42(const char *status, const char *reason,
                                             int read_count, uint32_t raw)
{
    CFMutableDictionaryRef result = fixture_mmio(status, reason, read_count, raw);
    fixture_number(result, CFSTR("Offset"), 0xa00);
    if (read_count) {
        fixture_number(result, CFSTR("Architecture"), (raw >> 24) & 0x3fU);
        fixture_number(result, CFSTR("ChipID"), (raw >> 20) & 0x3ffU);
    }
    return result;
}

static void fixture_set_phases(CFMutableDictionaryRef fixture,
                                CFMutableDictionaryRef supplied_boot42)
{
    CFDictionaryRef boot0 = (CFDictionaryRef)CFDictionaryGetValue(fixture, CFSTR("MMIOResult"));
    int boot0_identified = exact_string(CFDictionaryGetValue(boot0, CFSTR("Status")), CFSTR("identified"));
    CFMutableDictionaryRef boot42 = supplied_boot42;
    if (boot42 == NULL)
        boot42 = fixture_boot42(boot0_identified ? "identified" : "not_attempted",
            boot0_identified ? "tu117-identified" : "boot0-not-identified",
            boot0_identified ? 1 : 0, 0x167000a1);
    CFDictionarySetValue(fixture, CFSTR("BOOT42Result"), boot42);
    int matched = boot0_identified && exact_string(CFDictionaryGetValue(boot42,
        CFSTR("Status")), CFSTR("identified"));
    uint64_t boot0_count = 0, boot42_count = 0;
    if (!dictionary_number(boot0, CFSTR("ReadCount"), 1, &boot0_count) ||
        !dictionary_number(boot42, CFSTR("ReadCount"), 1, &boot42_count)) {
        fputs("Self-test phase fixture invalid.\n", stderr);
        exit(1);
    }
    CFMutableDictionaryRef hal = CFDictionaryCreateMutable(kCFAllocatorDefault,
        0, &kCFTypeDictionaryKeyCallBacks, &kCFTypeDictionaryValueCallBacks);
    if (hal == NULL) {
        fputs("Self-test allocation failed.\n", stderr);
        exit(1);
    }
    CFDictionarySetValue(hal, CFSTR("Status"), matched ? CFSTR("matched") : CFSTR("not_selected"));
    CFDictionarySetValue(hal, CFSTR("SourceCommit"), CFSTR(NVIDIA_SOURCE_COMMIT));
    fixture_number(hal, CFSTR("TotalReadCount"), (int64_t)(boot0_count + boot42_count));
    if (matched) {
        CFDictionarySetValue(hal, CFSTR("Chip"), CFSTR("TU117"));
        fixture_number(hal, CFSTR("VariantIndex"), 41);
    }
    CFDictionarySetValue(fixture, CFSTR("HALSelection"), hal);
    CFRelease(hal);
    if (supplied_boot42 == NULL)
        CFRelease(boot42);
}

static CFMutableDictionaryRef valid_fixture(void)
{
    CFMutableDictionaryRef dictionary = CFDictionaryCreateMutable(
        kCFAllocatorDefault, 0, &kCFTypeDictionaryKeyCallBacks,
        &kCFTypeDictionaryValueCallBacks);
    CFMutableArrayRef bars = CFArrayCreateMutable(kCFAllocatorDefault, 0,
                                                  &kCFTypeArrayCallBacks);
    if (dictionary == NULL || bars == NULL) {
        fputs("Self-test allocation failed.\n", stderr);
        exit(1);
    }
    fixture_number(dictionary, CFSTR("Format"), 3);
    CFDictionarySetValue(dictionary, CFSTR("ProbeVersion"), CFSTR("0.3.0"));
    CFDictionarySetValue(dictionary, CFSTR("Stage"), CFSTR("attached"));
    CFDictionarySetValue(dictionary, CFSTR("AccessPolicy"), CFSTR(ACCESS_POLICY));
    fixture_number(dictionary, CFSTR("VendorID"), 0x10de);
    fixture_number(dictionary, CFSTR("DeviceID"), 0x1f91);
    fixture_number(dictionary, CFSTR("SubsystemVendorID"), 0x17aa);
    fixture_number(dictionary, CFSTR("SubsystemID"), 0x3806);
    fixture_number(dictionary, CFSTR("RevisionID"), 0xa1);
    fixture_number(dictionary, CFSTR("ClassCode"), 0x030000);
    fixture_number(dictionary, CFSTR("Command"), 6);
    fixture_number(dictionary, CFSTR("Status"), 0x10);
    for (size_t index = 0; index < BAR_COUNT; ++index) {
        CFMutableDictionaryRef bar = CFDictionaryCreateMutable(
            kCFAllocatorDefault, 0, &kCFTypeDictionaryKeyCallBacks,
            &kCFTypeDictionaryValueCallBacks);
        if (bar == NULL) {
            fputs("Self-test allocation failed.\n", stderr);
            exit(1);
        }
        fixture_number(bar, CFSTR("Register"), (int64_t)(0x10 + 4 * index));
        CFDictionarySetValue(bar, CFSTR("Present"), index == 0 ?
                               kCFBooleanTrue : kCFBooleanFalse);
        if (index == 0) {
            fixture_number(bar, CFSTR("Address"), 0xc0000000);
            fixture_number(bar, CFSTR("Length"), 0x1000000);
        }
        CFArrayAppendValue(bars, bar);
        CFRelease(bar);
    }
    CFDictionarySetValue(dictionary, CFSTR("BARDescriptors"), bars);
    CFRelease(bars);
    CFMutableDictionaryRef mmio = fixture_mmio("identified", "tu117-identified",
                                              1, 0x167000a1);
    CFDictionarySetValue(dictionary, CFSTR("MMIOResult"), mmio);
    CFRelease(mmio);
    fixture_set_phases(dictionary, NULL);
    return dictionary;
}

static void require_test(int condition, const char *name, unsigned int *count)
{
    if (!condition) {
        fprintf(stderr, "Self-test failed: %s\n", name);
        exit(1);
    }
    ++*count;
}

static int run_self_tests(void)
{
    unsigned int count = 0;
    struct snapshot snapshot;
    CFMutableDictionaryRef fixture = valid_fixture();
    require_test(decode_snapshot(fixture, &snapshot) &&
        snapshot.bars[0].address == UINT64_C(0xc0000000) &&
        snapshot.bars[0].length == UINT64_C(0x1000000),
        "valid production decoder fixture", &count);
    require_test(!decode_snapshot(NULL, &snapshot), "missing snapshot", &count);
    require_test(!decode_snapshot(kCFBooleanTrue, &snapshot),
                   "wrong snapshot type", &count);
    CFDictionarySetValue(fixture, CFSTR("Extra"), CFSTR("not allowed"));
    require_test(!decode_snapshot(fixture, &snapshot), "extra snapshot key", &count);
    CFDictionaryRemoveValue(fixture, CFSTR("Extra"));
    CFDictionaryRemoveValue(fixture, CFSTR("Format"));
    require_test(!decode_snapshot(fixture, &snapshot), "missing format", &count);
    fixture_number(fixture, CFSTR("Format"), 4);
    require_test(!decode_snapshot(fixture, &snapshot), "unsupported format", &count);
    fixture_number(fixture, CFSTR("Format"), 3);
    CFDictionarySetValue(fixture, CFSTR("VendorID"), kCFBooleanTrue);
    require_test(!decode_snapshot(fixture, &snapshot), "boolean numeric field", &count);
    fixture_number(fixture, CFSTR("VendorID"), -1);
    require_test(!decode_snapshot(fixture, &snapshot), "negative numeric field", &count);
    fixture_number(fixture, CFSTR("VendorID"), 0x10000);
    require_test(!decode_snapshot(fixture, &snapshot), "oversized numeric field", &count);
    fixture_number(fixture, CFSTR("VendorID"), 0x10de);
    double floating_value = 1.0;
    CFNumberRef floating = CFNumberCreate(kCFAllocatorDefault,
                                           kCFNumberDoubleType, &floating_value);
    require_test(floating != NULL, "floating fixture allocation", &count);
    CFDictionarySetValue(fixture, CFSTR("Format"), floating);
    CFRelease(floating);
    require_test(!decode_snapshot(fixture, &snapshot), "floating numeric field", &count);
    fixture_number(fixture, CFSTR("Format"), 3);
    fixture_number(fixture, CFSTR("SubsystemID"), 0x3807);
    require_test(!decode_snapshot(fixture, &snapshot), "wrong subsystem", &count);
    fixture_number(fixture, CFSTR("SubsystemID"), 0x3806);
    fixture_number(fixture, CFSTR("ClassCode"), 0x030200);
    require_test(!decode_snapshot(fixture, &snapshot), "wrong class code", &count);
    fixture_number(fixture, CFSTR("ClassCode"), 0x030000);
    CFDictionarySetValue(fixture, CFSTR("AccessPolicy"), CFSTR("write"));
    require_test(!decode_snapshot(fixture, &snapshot), "wrong policy", &count);
    CFDictionarySetValue(fixture, CFSTR("AccessPolicy"), CFSTR(ACCESS_POLICY));
    CFDictionarySetValue(fixture, CFSTR("Stage"), CFSTR("ready"));
    require_test(!decode_snapshot(fixture, &snapshot), "wrong stage", &count);
    CFDictionarySetValue(fixture, CFSTR("Stage"), CFSTR("attached"));
    CFDictionarySetValue(fixture, CFSTR("ProbeVersion"),
                           CFSTR("12345678901234567890123456789012"));
    require_test(!decode_snapshot(fixture, &snapshot), "oversized version", &count);
    CFDictionarySetValue(fixture, CFSTR("ProbeVersion"), CFSTR("0.1.0\""));
    require_test(!decode_snapshot(fixture, &snapshot), "unsafe version character", &count);
    CFDictionarySetValue(fixture, CFSTR("ProbeVersion"), CFSTR("0.3.0"));
    CFMutableArrayRef bars = (CFMutableArrayRef)CFDictionaryGetValue(
        fixture, CFSTR("BARDescriptors"));
    CFArrayAppendValue(bars, CFArrayGetValueAtIndex(bars, 0));
    require_test(!decode_snapshot(fixture, &snapshot), "oversized BAR array", &count);
    CFArrayRemoveValueAtIndex(bars, BAR_COUNT);
    CFMutableDictionaryRef bar = (CFMutableDictionaryRef)CFArrayGetValueAtIndex(bars, 1);
    fixture_number(bar, CFSTR("Register"), 0x10);
    require_test(!decode_snapshot(fixture, &snapshot), "duplicate BAR register", &count);
    fixture_number(bar, CFSTR("Register"), 0x14);
    CFDictionarySetValue(bar, CFSTR("Present"), CFSTR("false"));
    require_test(!decode_snapshot(fixture, &snapshot), "wrong BAR boolean type", &count);
    CFDictionarySetValue(bar, CFSTR("Present"), kCFBooleanFalse);
    fixture_number(bar, CFSTR("Address"), 0);
    require_test(!decode_snapshot(fixture, &snapshot), "absent BAR metadata", &count);
    CFDictionaryRemoveValue(bar, CFSTR("Address"));
    bar = (CFMutableDictionaryRef)CFArrayGetValueAtIndex(bars, 0);
    fixture_number(bar, CFSTR("Length"), 0);
    require_test(!decode_snapshot(fixture, &snapshot), "zero BAR length", &count);
    fixture_number(bar, CFSTR("Length"), 0x1000000);
    CFDictionarySetValue(bar, CFSTR("Address"), CFSTR("0xc0000000"));
    require_test(!decode_snapshot(fixture, &snapshot), "wrong BAR address type", &count);
    fixture_number(bar, CFSTR("Address"), 0xc0000000);
    CFDictionaryRemoveValue(bar, CFSTR("Length"));
    require_test(!decode_snapshot(fixture, &snapshot), "missing present BAR length", &count);
    fixture_number(bar, CFSTR("Length"), 0x1000000);
    require_test(decode_snapshot(fixture, &snapshot), "restored valid fixture", &count);
    CFRelease(fixture);

    fixture = valid_fixture();
    CFMutableDictionaryRef mmio = (CFMutableDictionaryRef)CFDictionaryGetValue(
        fixture, CFSTR("MMIOResult"));
    struct mmio_result decoded_mmio;
    require_test(!decode_mmio(NULL, &decoded_mmio), "missing MMIO result", &count);
    require_test(!decode_mmio(kCFBooleanTrue, &decoded_mmio),
        "wrong MMIO result type", &count);
    CFDictionarySetValue(mmio, CFSTR("Extra"), CFSTR("private payload"));
    require_test(!decode_snapshot(fixture, &snapshot), "extra MMIO key", &count);
    CFDictionaryRemoveValue(mmio, CFSTR("Extra"));
    fixture_number(mmio, CFSTR("ReadCount"), 2);
    require_test(!decode_snapshot(fixture, &snapshot), "multiple reads rejected", &count);
    fixture_number(mmio, CFSTR("ReadCount"), 1);
    fixture_number(mmio, CFSTR("BarIndex"), 1);
    require_test(!decode_snapshot(fixture, &snapshot), "other BAR rejected", &count);
    fixture_number(mmio, CFSTR("BarIndex"), 0);
    fixture_number(mmio, CFSTR("Offset"), 4);
    require_test(!decode_snapshot(fixture, &snapshot), "other offset rejected", &count);
    fixture_number(mmio, CFSTR("Offset"), 0);
    fixture_number(mmio, CFSTR("Width"), 64);
    require_test(!decode_snapshot(fixture, &snapshot), "other width rejected", &count);
    fixture_number(mmio, CFSTR("Width"), 32);
    CFDictionarySetValue(mmio, CFSTR("RawValue"), kCFBooleanTrue);
    require_test(!decode_snapshot(fixture, &snapshot), "boolean MMIO raw value", &count);
    fixture_number(mmio, CFSTR("RawValue"), -1);
    require_test(!decode_snapshot(fixture, &snapshot), "negative MMIO raw value", &count);
    fixture_number(mmio, CFSTR("RawValue"), INT64_C(0x100000000));
    require_test(!decode_snapshot(fixture, &snapshot), "oversized MMIO raw value", &count);
    fixture_number(mmio, CFSTR("RawValue"), 0x167000a1);
    fixture_number(mmio, CFSTR("Architecture"), 0x17);
    require_test(!decode_snapshot(fixture, &snapshot), "incoherent architecture", &count);
    fixture_number(mmio, CFSTR("Architecture"), 0x16);
    fixture_number(mmio, CFSTR("Implementation"), 8);
    require_test(!decode_snapshot(fixture, &snapshot), "incoherent implementation", &count);
    fixture_number(mmio, CFSTR("Implementation"), 7);
    CFDictionarySetValue(mmio, CFSTR("Reason"), CFSTR("unexpected reason"));
    require_test(!decode_snapshot(fixture, &snapshot), "unknown MMIO reason", &count);
    const UInt8 embedded_reason[] = "tu117-identified\0private";
    CFStringRef embedded_string = CFStringCreateWithBytes(kCFAllocatorDefault,
        embedded_reason, sizeof(embedded_reason) - 1, kCFStringEncodingASCII, 0);
    require_test(embedded_string != NULL, "embedded reason allocation", &count);
    CFDictionarySetValue(mmio, CFSTR("Reason"), embedded_string);
    CFRelease(embedded_string);
    require_test(!decode_snapshot(fixture, &snapshot), "embedded NUL reason rejected", &count);
    CFDictionarySetValue(mmio, CFSTR("Reason"), CFSTR("tu117-identified"));
    CFDictionarySetValue(mmio, CFSTR("Status"), CFSTR("failed"));
    require_test(!decode_snapshot(fixture, &snapshot), "success with failed status", &count);
    CFDictionarySetValue(mmio, CFSTR("Status"), CFSTR("identified"));
    require_test(decode_snapshot(fixture, &snapshot), "restored MMIO fixture", &count);
    bars = (CFMutableArrayRef)CFDictionaryGetValue(fixture, CFSTR("BARDescriptors"));
    bar = (CFMutableDictionaryRef)CFArrayGetValueAtIndex(bars, 0);
    fixture_number(bar, CFSTR("Length"), 4);
    require_test(!decode_snapshot(fixture, &snapshot), "successful read needs exact BAR0 length", &count);
    fixture_number(bar, CFSTR("Length"), 0x1000000);
    fixture_number(bar, CFSTR("Address"), 0xc0000004);
    require_test(!decode_snapshot(fixture, &snapshot), "successful read needs aligned BAR0", &count);
    fixture_number(bar, CFSTR("Address"), 0xc0000000);

    static const struct { uint32_t raw; const char *reason; } failures[] = {
        {0, "zero-value"}, {UINT32_MAX, "all-ones-value"},
        {0x157000a1, "architecture-mismatch"},
        {0x166000a1, "implementation-mismatch"}
    };
    for (size_t index = 0; index < sizeof(failures) / sizeof(failures[0]); ++index) {
        mmio = fixture_mmio("failed", failures[index].reason, 1, failures[index].raw);
        CFDictionarySetValue(fixture, CFSTR("MMIOResult"), mmio);
        fixture_set_phases(fixture, NULL);
        require_test(decode_snapshot(fixture, &snapshot) &&
            snapshot.mmio.status == MMIO_FAILED && snapshot.mmio.read_count == 1,
            "failed read classified without claiming identification", &count);
        CFDictionarySetValue(mmio, CFSTR("Status"), CFSTR("identified"));
        require_test(!decode_snapshot(fixture, &snapshot),
            "failed read cannot claim success", &count);
        CFRelease(mmio);
    }
    /* Extended architecture bit is part of the decoded architecture. */
    mmio = fixture_mmio("failed", "architecture-mismatch", 1, 0x167001a1);
    CFDictionarySetValue(fixture, CFSTR("MMIOResult"), mmio);
    fixture_set_phases(fixture, NULL);
    require_test(decode_snapshot(fixture, &snapshot) && snapshot.mmio.architecture == 0x36,
        "extended architecture bit decoded", &count);
    CFRelease(mmio);
    CFRelease(fixture);

    for (size_t index = 0; index < MMIO_REFUSAL_COUNT; ++index) {
        fixture = valid_fixture();
        mmio = fixture_mmio("refused", mmio_reasons[index], 0, 0);
        CFDictionarySetValue(fixture, CFSTR("MMIOResult"), mmio);
        if (index == 0)
            CFDictionaryRemoveValue(fixture, CFSTR("BARDescriptors"));
        if (index == 1) {
            bars = (CFMutableArrayRef)CFDictionaryGetValue(fixture, CFSTR("BARDescriptors"));
            bar = (CFMutableDictionaryRef)CFArrayGetValueAtIndex(bars, 0);
            CFDictionarySetValue(bar, CFSTR("Present"), kCFBooleanFalse);
            CFDictionaryRemoveValue(bar, CFSTR("Address"));
            CFDictionaryRemoveValue(bar, CFSTR("Length"));
        }
        fixture_set_phases(fixture, NULL);
        require_test(decode_snapshot(fixture, &snapshot) &&
            snapshot.mmio.status == MMIO_REFUSED && snapshot.mmio.read_count == 0,
            "known refusal performs no read", &count);
        fixture_number(mmio, CFSTR("RawValue"), 0);
        require_test(!decode_snapshot(fixture, &snapshot),
            "refusal cannot publish raw register", &count);
        CFDictionaryRemoveValue(mmio, CFSTR("RawValue"));
        fixture_number(mmio, CFSTR("ReadCount"), 1);
        require_test(!decode_snapshot(fixture, &snapshot),
            "refusal cannot claim attempted read", &count);
        CFRelease(mmio);
        CFRelease(fixture);
    }

    fixture = valid_fixture();
    CFDictionaryRemoveValue(fixture, CFSTR("MMIOResult"));
    CFDictionaryRemoveValue(fixture, CFSTR("BOOT42Result"));
    CFDictionaryRemoveValue(fixture, CFSTR("HALSelection"));
    fixture_number(fixture, CFSTR("Format"), 1);
    CFDictionarySetValue(fixture, CFSTR("ProbeVersion"), CFSTR("0.1.0"));
    CFDictionarySetValue(fixture, CFSTR("AccessPolicy"), CFSTR(LEGACY_ACCESS_POLICY));
    require_test(decode_snapshot(fixture, &snapshot) && snapshot.format == 1,
        "strict legacy snapshot recognized", &count);
    CFDictionarySetValue(fixture, CFSTR("Extra"), CFSTR("not allowed"));
    require_test(!decode_snapshot(fixture, &snapshot), "legacy extra rejected", &count);
    CFRelease(fixture);

    fixture = valid_fixture();
    CFDictionaryRemoveValue(fixture, CFSTR("BOOT42Result"));
    CFDictionaryRemoveValue(fixture, CFSTR("HALSelection"));
    fixture_number(fixture, CFSTR("Format"), 2);
    CFDictionarySetValue(fixture, CFSTR("ProbeVersion"), CFSTR("0.2.0"));
    CFDictionarySetValue(fixture, CFSTR("AccessPolicy"), CFSTR(LEGACY_MMIO_ACCESS_POLICY));
    require_test(decode_snapshot(fixture, &snapshot) && snapshot.format == 2,
        "strict version 0.2.0 snapshot recognized", &count);
    CFDictionarySetValue(fixture, CFSTR("Extra"), CFSTR("not allowed"));
    require_test(!decode_snapshot(fixture, &snapshot), "version 0.2.0 extra rejected", &count);
    CFRelease(fixture);

    fixture = valid_fixture();
    CFMutableDictionaryRef boot42 = (CFMutableDictionaryRef)CFDictionaryGetValue(
        fixture, CFSTR("BOOT42Result"));
    CFMutableDictionaryRef hal = (CFMutableDictionaryRef)CFDictionaryGetValue(
        fixture, CFSTR("HALSelection"));
    require_test(decode_snapshot(fixture, &snapshot) && snapshot.hal_matched &&
        snapshot.total_read_count == 2 && snapshot.boot42.chip_id == 0x167,
        "two coherent identities select pinned TU117 table entry", &count);
    require_test(!decode_boot42(NULL, &snapshot.mmio, &snapshot.boot42),
        "missing BOOT42 result", &count);
    require_test(!decode_boot42(kCFBooleanTrue, &snapshot.mmio, &snapshot.boot42),
        "wrong BOOT42 type", &count);
    CFDictionarySetValue(boot42, CFSTR("Extra"), CFSTR("private"));
    require_test(!decode_snapshot(fixture, &snapshot), "extra BOOT42 key", &count);
    CFDictionaryRemoveValue(boot42, CFSTR("Extra"));
    fixture_number(boot42, CFSTR("Offset"), 0);
    require_test(!decode_snapshot(fixture, &snapshot), "BOOT42 cannot use BOOT0 offset", &count);
    fixture_number(boot42, CFSTR("Offset"), 0xa00);
    fixture_number(boot42, CFSTR("BarIndex"), 1);
    require_test(!decode_snapshot(fixture, &snapshot), "BOOT42 cannot use other BAR", &count);
    fixture_number(boot42, CFSTR("BarIndex"), 0);
    fixture_number(boot42, CFSTR("Width"), 64);
    require_test(!decode_snapshot(fixture, &snapshot), "BOOT42 cannot use other width", &count);
    fixture_number(boot42, CFSTR("Width"), 32);
    fixture_number(boot42, CFSTR("ReadCount"), 2);
    require_test(!decode_snapshot(fixture, &snapshot), "BOOT42 cannot retry", &count);
    fixture_number(boot42, CFSTR("ReadCount"), 1);
    CFDictionarySetValue(boot42, CFSTR("RawValue"), kCFBooleanTrue);
    require_test(!decode_snapshot(fixture, &snapshot), "BOOT42 boolean raw value", &count);
    fixture_number(boot42, CFSTR("RawValue"), INT64_C(0x100000000));
    require_test(!decode_snapshot(fixture, &snapshot), "BOOT42 oversized raw value", &count);
    fixture_number(boot42, CFSTR("RawValue"), 0x167001a1);
    fixture_number(boot42, CFSTR("Architecture"), 0x36);
    require_test(!decode_snapshot(fixture, &snapshot), "BOOT42 rejects BOOT0 architecture mask", &count);
    fixture_number(boot42, CFSTR("Architecture"), 0x16);
    require_test(decode_snapshot(fixture, &snapshot) && snapshot.hal_matched,
        "BOOT42 bit 8 is not the BOOT0 architecture extension", &count);
    fixture_number(boot42, CFSTR("RawValue"), 0x167000a1);
    fixture_number(boot42, CFSTR("ChipID"), 0x166);
    require_test(!decode_snapshot(fixture, &snapshot), "incoherent BOOT42 chip ID", &count);
    fixture_number(boot42, CFSTR("ChipID"), 0x167);
    fixture_number(boot42, CFSTR("Implementation"), 6);
    require_test(!decode_snapshot(fixture, &snapshot), "incoherent BOOT42 implementation", &count);
    fixture_number(boot42, CFSTR("Implementation"), 7);
    CFDictionarySetValue(boot42, CFSTR("Status"), CFSTR("not_attempted"));
    require_test(!decode_snapshot(fixture, &snapshot), "BOOT42 must run after identified BOOT0", &count);
    CFDictionarySetValue(boot42, CFSTR("Status"), CFSTR("identified"));
    fixture_number(hal, CFSTR("TotalReadCount"), 1);
    require_test(!decode_snapshot(fixture, &snapshot), "HAL count must equal phase sum", &count);
    fixture_number(hal, CFSTR("TotalReadCount"), 3);
    require_test(!decode_snapshot(fixture, &snapshot), "HAL count cannot exceed two", &count);
    fixture_number(hal, CFSTR("TotalReadCount"), 2);
    CFDictionarySetValue(hal, CFSTR("SourceCommit"), CFSTR("0000000000000000000000000000000000000000"));
    require_test(!decode_snapshot(fixture, &snapshot), "HAL source pin mismatch", &count);
    CFDictionarySetValue(hal, CFSTR("SourceCommit"), CFSTR(NVIDIA_SOURCE_COMMIT));
    fixture_number(hal, CFSTR("VariantIndex"), 40);
    require_test(!decode_snapshot(fixture, &snapshot), "HAL variant index mismatch", &count);
    fixture_number(hal, CFSTR("VariantIndex"), 41);
    CFDictionarySetValue(hal, CFSTR("Chip"), CFSTR("TU116"));
    require_test(!decode_snapshot(fixture, &snapshot), "HAL chip mismatch", &count);
    CFDictionarySetValue(hal, CFSTR("Chip"), CFSTR("TU117"));
    CFDictionarySetValue(hal, CFSTR("Status"), CFSTR("not_selected"));
    require_test(!decode_snapshot(fixture, &snapshot), "coherent identities must select table entry", &count);
    CFDictionarySetValue(hal, CFSTR("Status"), CFSTR("matched"));
    CFDictionarySetValue(hal, CFSTR("Extra"), CFSTR("private"));
    require_test(!decode_snapshot(fixture, &snapshot), "extra HAL key", &count);
    CFDictionaryRemoveValue(hal, CFSTR("Extra"));
    require_test(decode_snapshot(fixture, &snapshot), "restored HAL fixture", &count);
    CFRelease(fixture);

    for (size_t index = 0; index < sizeof(failures) / sizeof(failures[0]); ++index) {
        fixture = valid_fixture();
        boot42 = fixture_boot42("failed", failures[index].reason, 1, failures[index].raw);
        fixture_set_phases(fixture, boot42);
        require_test(decode_snapshot(fixture, &snapshot) && !snapshot.hal_matched &&
            snapshot.total_read_count == 2 && snapshot.boot42.status == MMIO_FAILED,
            "BOOT42 failed read prevents HAL selection", &count);
        hal = (CFMutableDictionaryRef)CFDictionaryGetValue(fixture, CFSTR("HALSelection"));
        CFDictionarySetValue(hal, CFSTR("Status"), CFSTR("matched"));
        CFDictionarySetValue(hal, CFSTR("Chip"), CFSTR("TU117"));
        fixture_number(hal, CFSTR("VariantIndex"), 41);
        require_test(!decode_snapshot(fixture, &snapshot), "failed BOOT42 cannot select HAL", &count);
        CFRelease(boot42);
        CFRelease(fixture);
    }
    fixture = valid_fixture();
    boot42 = fixture_boot42("failed", "architecture-mismatch", 1, 0x367000a1);
    fixture_set_phases(fixture, boot42);
    require_test(decode_snapshot(fixture, &snapshot) && snapshot.boot42.architecture == 0x36 &&
        !snapshot.hal_matched, "BOOT42 architecture includes bit 29", &count);
    CFRelease(boot42);
    CFRelease(fixture);

    for (size_t index = 0; index < MMIO_REFUSAL_COUNT; ++index) {
        fixture = valid_fixture();
        boot42 = fixture_boot42("refused", mmio_reasons[index], 0, 0);
        fixture_set_phases(fixture, boot42);
        int outer_guard = index == 0 || index == 1 || index == 13 || index == 14;
        int decoded = decode_snapshot(fixture, &snapshot);
        require_test(outer_guard ? !decoded : decoded && !snapshot.hal_matched &&
            snapshot.total_read_count == 1 && snapshot.boot42.status == MMIO_REFUSED,
            "phase-two refusal respects retained outer guards", &count);
        CFRelease(boot42);
        CFRelease(fixture);
    }
    fixture = valid_fixture();
    mmio = fixture_mmio("failed", "zero-value", 1, 0);
    CFDictionarySetValue(fixture, CFSTR("MMIOResult"), mmio);
    fixture_set_phases(fixture, NULL);
    require_test(decode_snapshot(fixture, &snapshot) && snapshot.total_read_count == 1 &&
        snapshot.boot42.status == MMIO_NOT_ATTEMPTED && !snapshot.hal_matched,
        "BOOT0 failure stops before BOOT42", &count);
    boot42 = fixture_boot42("identified", "tu117-identified", 1, 0x167000a1);
    fixture_set_phases(fixture, boot42);
    require_test(!decode_snapshot(fixture, &snapshot), "BOOT42 forbidden after failed BOOT0", &count);
    CFRelease(boot42);
    CFRelease(mmio);
    CFRelease(fixture);

    struct report classified;
    memset(&classified, 0, sizeof(classified));
    classified.complete = 1;
    require_test(strcmp(report_status(&classified), "not_attached") == 0 &&
        report_exit_code(&classified) == 0, "not attached result is complete", &count);
    classified.attached = 1;
    classified.snapshot.mmio.status = MMIO_REFUSED;
    classified.snapshot.boot42.status = MMIO_NOT_ATTEMPTED;
    require_test(strcmp(report_status(&classified), "refused") == 0 &&
        report_exit_code(&classified) == 0, "safe refusal is complete", &count);
    classified.snapshot.mmio.status = MMIO_FAILED;
    require_test(strcmp(report_status(&classified), "failed") == 0 &&
        report_exit_code(&classified) != 0, "failed read has nonzero exit", &count);
    classified.snapshot.mmio.status = MMIO_IDENTIFIED;
    classified.snapshot.boot42.status = MMIO_IDENTIFIED;
    classified.snapshot.hal_matched = 1;
    require_test(strcmp(report_status(&classified), "hal_matched") == 0 &&
        report_exit_code(&classified) == 0, "identified result", &count);
    classified.snapshot.hal_matched = 0;
    classified.snapshot.boot42.status = MMIO_REFUSED;
    require_test(strcmp(report_status(&classified), "refused") == 0 &&
        report_exit_code(&classified) == 0, "phase-two refusal is complete", &count);
    classified.snapshot.boot42.status = MMIO_FAILED;
    require_test(strcmp(report_status(&classified), "failed") == 0 &&
        report_exit_code(&classified) != 0, "phase-two failure has nonzero exit", &count);
    classified.outdated = 1;
    require_test(strcmp(report_status(&classified), "outdated_probe") == 0 &&
        report_exit_code(&classified) == 0, "outdated probe recognized", &count);
    FILE *serialized = tmpfile();
    require_test(serialized != NULL, "serialization fixture allocation", &count);
    write_report(serialized, &classified);
    require_test(fflush(serialized) == 0 && fseek(serialized, 0, SEEK_SET) == 0,
        "serialization fixture rewind", &count);
    char serialized_report[4096];
    size_t serialized_size = fread(serialized_report, 1, sizeof(serialized_report) - 1, serialized);
    serialized_report[serialized_size] = '\0';
    require_test(!ferror(serialized) && strstr(serialized_report, "\"probe\":null") != NULL &&
        strstr(serialized_report, "version 0.3.0") != NULL &&
        strstr(serialized_report, "raw_value") == NULL,
        "legacy report emits fixed instruction without snapshot", &count);
    fclose(serialized);
    classified.complete = 0;
    require_test(strcmp(report_status(&classified), "error") == 0 &&
        report_exit_code(&classified) != 0, "invalid snapshot has nonzero exit", &count);

    const UInt8 identity_bytes[] = {0xde, 0x10, 0, 0};
    uint16_t identity = 0;
    CFDataRef identity_data = CFDataCreate(kCFAllocatorDefault, identity_bytes, 4);
    require_test(identity_data != NULL &&
        decode_provider_id(identity_data, &identity) && identity == 0x10de,
        "provider little-endian identity", &count);
    CFRelease(identity_data);
    CFDataRef short_data = CFDataCreate(kCFAllocatorDefault, identity_bytes, 3);
    require_test(short_data != NULL && !decode_provider_id(short_data, &identity),
        "short provider identity", &count);
    CFRelease(short_data);
    require_test(!decode_provider_id(kCFBooleanTrue, &identity),
        "boolean provider identity", &count);
    require_test(has_boot_token("-v\t-wegnoegpu -igfxblr", "-wegnoegpu"),
        "exact boot token", &count);
    require_test(has_boot_token("-v -wegnoegpu=0 -igfxblr", "-wegnoegpu"),
        "valued leading-dash boot flag", &count);
    require_test(has_boot_token("-wegnoegpu=anything", "-wegnoegpu"),
        "arbitrary leading-dash flag value", &count);
    require_test(!has_boot_token("foo-wegnoegpu -x-wegnoegpu -wegnoegpu-other -wegnoegpux", "-wegnoegpu"),
        "nonexact boot flag alias", &count);
    fprintf(stdout, "NVIDIA transport self-tests passed (%u checks).\n", count);
    return 0;
}

int main(int argc, char **argv)
{
    if (argc == 2 && strcmp(argv[1], "--self-test") == 0)
        return run_self_tests();
    if (argc == 2 && strcmp(argv[1], "--version") == 0) {
        puts("nvidia-transport " TOOL_VERSION);
        return 0;
    }
    if (argc == 2 && strcmp(argv[1], "--help") == 0) {
        puts("Usage: nvidia-transport [--help | --version | --self-test]\n"
             "Read the S540 NVIDIA transport probe snapshot and verify its provider.\n"
             "No administrator privileges or device access are required.\n"
             "not_attached is an observation, not a diagnosis of the GPU.");
        return 0;
    }
    if (argc != 1) {
        fputs("Usage: nvidia-transport [--help | --version | --self-test]\n", stderr);
        return 64;
    }
    struct report report;
    memset(&report, 0, sizeof(report));
    report.complete = 1;
    collect_report(&report);
    write_report(stdout, &report);
    if (fflush(stdout) == EOF || ferror(stdout))
        return 74;
    return report_exit_code(&report);
}
