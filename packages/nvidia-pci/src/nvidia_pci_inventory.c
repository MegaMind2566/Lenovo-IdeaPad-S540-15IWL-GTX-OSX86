/*
 * Read-only IORegistry inventory for the S540 NVIDIA port investigation.
 * This program reads published registry properties. It does not open a driver,
 * access PCI configuration space, map BARs, or change device power or firmware.
 *
 * Build: clang -std=c11 -Wall -Wextra -Werror -O2 nvidia_pci_inventory.c \
 *        -framework IOKit -framework CoreFoundation -o nvidia-pci
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define TOOL_VERSION "1.0.0"
#define TARGET_VENDOR UINT32_C(0x10de)
#define TARGET_DEVICE UINT32_C(0x1f91)

/* The registry publishes PCI integers as four little-endian bytes. */
static int pci_decode_le32(const unsigned char *bytes, size_t length,
                          uint32_t *value)
{
    if (bytes == NULL || value == NULL || length != 4)
        return 0;
    *value = (uint32_t)bytes[0] | ((uint32_t)bytes[1] << 8) |
             ((uint32_t)bytes[2] << 16) | ((uint32_t)bytes[3] << 24);
    return 1;
}

/* Read one UTF-8 code point; malformed bytes become U+FFFD independently. */
static uint32_t json_codepoint(const unsigned char **cursor)
{
    const unsigned char *p = *cursor;
    uint32_t value;
    size_t length;
    if (p[0] < 0x80) {
        *cursor = p + 1;
        return p[0];
    }
    if (p[0] >= 0xc2 && p[0] <= 0xdf) {
        length = 2;
        value = p[0] & 0x1f;
    } else if (p[0] >= 0xe0 && p[0] <= 0xef) {
        length = 3;
        value = p[0] & 0x0f;
    } else if (p[0] >= 0xf0 && p[0] <= 0xf4) {
        length = 4;
        value = p[0] & 0x07;
    } else {
        *cursor = p + 1;
        return 0xfffd;
    }
    for (size_t i = 1; i < length; ++i) {
        /* A terminating NUL fails before looking at any later byte. */
        if (p[i] < 0x80 || p[i] > 0xbf) {
            *cursor = p + 1;
            return 0xfffd;
        }
        value = (value << 6) | (p[i] & 0x3f);
    }
    if ((length == 3 && value < 0x800) ||
        (length == 4 && value < 0x10000) || value > 0x10ffff ||
        (value >= 0xd800 && value <= 0xdfff)) {
        *cursor = p + 1;
        return 0xfffd;
    }
    *cursor = p + length;
    return value;
}

/* ASCII-only JSON output preserves valid UTF-8 as Unicode escapes. */
static void json_string(FILE *out, const char *text)
{
    const unsigned char *p = (const unsigned char *)text;
    fputc('"', out);
    while (*p != '\0') {
        uint32_t cp = json_codepoint(&p);
        if (cp == '"' || cp == '\\') {
            fputc('\\', out);
            fputc((int)cp, out);
        } else if (cp >= 0x20 && cp <= 0x7e) {
            fputc((int)cp, out);
        } else if (cp <= 0xffff) {
            fprintf(out, "\\u%04" PRIx32, cp);
        } else {
            cp -= 0x10000;
            fprintf(out, "\\u%04" PRIx32 "\\u%04" PRIx32,
                    UINT32_C(0xd800) + (cp >> 10),
                    UINT32_C(0xdc00) + (cp & 0x3ff));
        }
    }
    fputc('"', out);
}

static int has_boot_token(const char *arguments, const char *token)
{
    size_t wanted = strlen(token);
    const char *p = arguments;
    while (*p != '\0') {
        p += strspn(p, " \t\r\n\v\f");
        size_t length = strcspn(p, " \t\r\n\v\f");
        if (length == wanted && memcmp(p, token, wanted) == 0)
            return 1;
        p += length;
    }
    return 0;
}

#ifndef NVIDIA_PCI_CORE_TEST
#include <CoreFoundation/CoreFoundation.h>
#include <IOKit/IOKitLib.h>
#include <limits.h>

#define MAX_MATCHES 8
#define MAX_PCI_ENTRIES 4096
#define MAX_DEVICE_TREE_ENTRIES 8192
#define MAX_PARENT_DEPTH 16
#define MAX_RAW_BYTES 256
#define MAX_BOOT_ARGUMENT_BYTES 4096

enum warning_code {
    WARN_MATCHING_ALLOCATION,
    WARN_ENUMERATION_FAILED,
    WARN_ENUMERATION_INVALIDATED,
    WARN_ENUMERATION_LIMIT,
    WARN_VENDOR_ID_UNREADABLE,
    WARN_NVIDIA_DEVICE_ID_UNREADABLE,
    WARN_MATCH_LIMIT,
    WARN_SELECTED_NAME_UNREADABLE,
    WARN_SELECTED_PATH_UNREADABLE,
    WARN_SELECTED_CLASS_UNREADABLE,
    WARN_SELECTED_PROPERTY_MALFORMED,
    WARN_RAW_PROPERTY_MALFORMED,
    WARN_RAW_PROPERTY_TRUNCATED,
    WARN_PARENT_READ_FAILED,
    WARN_PARENT_DEPTH_LIMIT,
    WARN_PARENT_ID_UNREADABLE,
    WARN_DEVICE_TREE_ENUMERATION_FAILED,
    WARN_DEVICE_TREE_ID_MALFORMED,
    WARN_CONTEXT_UNREADABLE,
    WARN_FLAG_UNREADABLE,
    WARNING_COUNT
};

static const char *const warning_names[WARNING_COUNT] = {
    "matching_allocation_failed", "enumeration_failed",
    "enumeration_invalidated", "enumeration_limit_reached",
    "pci_vendor_id_unreadable", "nvidia_device_id_unreadable",
    "target_match_limit_reached", "selected_node_name_unreadable",
    "selected_registry_path_unreadable", "selected_node_class_unreadable",
    "selected_identity_property_malformed", "raw_property_malformed",
    "raw_property_truncated", "parent_lookup_failed",
    "parent_lookup_depth_limit_reached", "parent_identity_unreadable",
    "device_tree_enumeration_failed", "device_tree_identity_malformed",
    "boot_argument_context_unreadable", "selected_flag_value_unreadable"
};

struct number_property {
    uint32_t value;
    int present;
};

struct raw_property {
    unsigned char bytes[MAX_RAW_BYTES];
    size_t copied;
    uint64_t length;
    int present;
};

struct flag_property {
    int present;
    int kind; /* 0: unknown, 1: boolean, 2: unsigned integer. */
    uint32_t value;
};

struct pci_identity {
    const char *plane;
    io_string_t path;
    io_name_t name;
    io_name_t node_class;
    struct number_property vendor;
    struct number_property device;
    struct number_property subsystem_vendor;
    struct number_property subsystem_device;
    struct number_property revision;
    struct number_property class_code;
};

struct pci_match {
    struct pci_identity identity;
    struct raw_property reg;
    struct raw_property assigned;
    struct pci_identity parent;
    struct flag_property disable_gpu;
    struct flag_property pci_device_hidden;
    int has_parent;
    int service_visible;
};

struct report {
    struct pci_match matches[MAX_MATCHES];
    size_t count;
    unsigned int warnings[WARNING_COUNT];
    int complete;
    int wegnoegpu_known;
    int wegnoegpu_present;
};

static void warn_report(struct report *report, enum warning_code code,
                        int incomplete)
{
    if (report->warnings[code] != UINT_MAX)
        ++report->warnings[code];
    if (incomplete)
        report->complete = 0;
}

/* Return 1 for a valid integer, 0 if absent, and -1 if malformed. */
static int read_number(io_registry_entry_t entry, CFStringRef key,
                       uint32_t maximum, struct number_property *property)
{
    CFTypeRef object = IORegistryEntryCreateCFProperty(
        entry, key, kCFAllocatorDefault, 0);
    uint32_t value = 0;
    int valid = 0;
    memset(property, 0, sizeof(*property));
    if (object == NULL)
        return 0;
    if (CFGetTypeID(object) == CFDataGetTypeID()) {
        CFIndex size = CFDataGetLength((CFDataRef)object);
        valid = size == 4 && pci_decode_le32(
            CFDataGetBytePtr((CFDataRef)object), (size_t)size, &value);
    } else if (CFGetTypeID(object) == CFNumberGetTypeID() &&
               !CFNumberIsFloatType((CFNumberRef)object)) {
        int64_t signed_value = 0;
        valid = CFNumberGetValue((CFNumberRef)object, kCFNumberSInt64Type,
                                 &signed_value) &&
                signed_value >= 0 && signed_value <= UINT32_MAX;
        if (valid)
            value = (uint32_t)signed_value;
    }
    CFRelease(object);
    if (!valid || value > maximum)
        return -1;
    property->value = value;
    property->present = 1;
    return 1;
}

static void read_optional_number(io_registry_entry_t entry, CFStringRef key,
                                 uint32_t maximum,
                                 struct number_property *property,
                                 struct report *report)
{
    if (read_number(entry, key, maximum, property) < 0)
        warn_report(report, WARN_SELECTED_PROPERTY_MALFORMED, 0);
}

static void read_identity(io_registry_entry_t entry, struct pci_identity *identity,
                          struct report *report, int parent, const char *plane)
{
    memset(identity, 0, sizeof(*identity));
    identity->plane = plane;
    if (IORegistryEntryGetPath(entry, plane, identity->path) !=
            KERN_SUCCESS ||
        memchr(identity->path, '\0', sizeof(identity->path)) == NULL) {
        identity->path[0] = '\0';
        warn_report(report, WARN_SELECTED_PATH_UNREADABLE, 1);
    }
    if (IORegistryEntryGetName(entry, identity->name) != KERN_SUCCESS ||
        memchr(identity->name, '\0', sizeof(identity->name)) == NULL) {
        identity->name[0] = '\0';
        warn_report(report, WARN_SELECTED_NAME_UNREADABLE, 0);
    }
    if (IOObjectGetClass(entry, identity->node_class) != KERN_SUCCESS ||
        memchr(identity->node_class, '\0', sizeof(identity->node_class)) == NULL) {
        identity->node_class[0] = '\0';
        warn_report(report, WARN_SELECTED_CLASS_UNREADABLE, 0);
    }
    if (read_number(entry, CFSTR("vendor-id"), UINT16_MAX,
                    &identity->vendor) != 1 ||
        read_number(entry, CFSTR("device-id"), UINT16_MAX,
                    &identity->device) != 1)
        warn_report(report, parent ? WARN_PARENT_ID_UNREADABLE :
                                    WARN_SELECTED_PROPERTY_MALFORMED, 1);
    read_optional_number(entry, CFSTR("class-code"), UINT32_C(0xffffff),
                         &identity->class_code, report);
    if (!parent) {
        read_optional_number(entry, CFSTR("subsystem-vendor-id"), UINT16_MAX,
                             &identity->subsystem_vendor, report);
        read_optional_number(entry, CFSTR("subsystem-id"), UINT16_MAX,
                             &identity->subsystem_device, report);
        read_optional_number(entry, CFSTR("revision-id"), UINT8_MAX,
                             &identity->revision, report);
    }
}

static void read_raw(io_registry_entry_t entry, CFStringRef key,
                     struct raw_property *property, struct report *report)
{
    CFTypeRef object = IORegistryEntryCreateCFProperty(
        entry, key, kCFAllocatorDefault, 0);
    memset(property, 0, sizeof(*property));
    if (object == NULL)
        return;
    if (CFGetTypeID(object) != CFDataGetTypeID()) {
        warn_report(report, WARN_RAW_PROPERTY_MALFORMED, 0);
        CFRelease(object);
        return;
    }
    CFIndex length = CFDataGetLength((CFDataRef)object);
    if (length < 0) {
        warn_report(report, WARN_RAW_PROPERTY_MALFORMED, 0);
        CFRelease(object);
        return;
    }
    property->present = 1;
    property->length = (uint64_t)length;
    property->copied = (uint64_t)length > MAX_RAW_BYTES ?
                       MAX_RAW_BYTES : (size_t)length;
    if (property->copied > 0)
        memcpy(property->bytes, CFDataGetBytePtr((CFDataRef)object),
               property->copied);
    if (property->length > property->copied)
        warn_report(report, WARN_RAW_PROPERTY_TRUNCATED, 0);
    CFRelease(object);
}

static void read_flag(io_registry_entry_t entry, CFStringRef key,
                      struct flag_property *flag, struct report *report)
{
    CFTypeRef object = IORegistryEntryCreateCFProperty(
        entry, key, kCFAllocatorDefault, 0);
    memset(flag, 0, sizeof(*flag));
    if (object == NULL)
        return;
    flag->present = 1;
    if (CFGetTypeID(object) == CFBooleanGetTypeID()) {
        flag->kind = 1;
        flag->value = CFBooleanGetValue((CFBooleanRef)object) ? 1 : 0;
    } else if (CFGetTypeID(object) == CFDataGetTypeID() &&
               CFDataGetLength((CFDataRef)object) == 4 &&
               pci_decode_le32(CFDataGetBytePtr((CFDataRef)object), 4,
                               &flag->value)) {
        flag->kind = 2;
    } else if (CFGetTypeID(object) == CFNumberGetTypeID() &&
               !CFNumberIsFloatType((CFNumberRef)object)) {
        int64_t value = 0;
        if (CFNumberGetValue((CFNumberRef)object, kCFNumberSInt64Type, &value) &&
            value >= 0 && value <= UINT32_MAX) {
            flag->kind = 2;
            flag->value = (uint32_t)value;
        }
    }
    /* Empty data still proves property presence, not a numeric value. */
    if (flag->kind == 0 && !(CFGetTypeID(object) == CFDataGetTypeID() &&
                             CFDataGetLength((CFDataRef)object) == 0))
        warn_report(report, WARN_FLAG_UNREADABLE, 0);
    CFRelease(object);
}

/* Retain only the nearest PCI-to-PCI bridge, never a full bridge tree. */
static void read_parent(io_registry_entry_t entry, struct pci_match *match,
                        struct report *report, const char *plane)
{
    io_registry_entry_t current = entry;
    int retained = 0;
    for (size_t depth = 0; depth < MAX_PARENT_DEPTH; ++depth) {
        io_registry_entry_t parent = IO_OBJECT_NULL;
        kern_return_t result = IORegistryEntryGetParentEntry(
            current, plane, &parent);
        if (retained)
            IOObjectRelease(current);
        retained = 0;
        if (result != KERN_SUCCESS) {
            /* A detached selected device can race this snapshot. */
            if (depth == 0)
                warn_report(report, WARN_PARENT_READ_FAILED, 0);
            return;
        }
        struct number_property class_code;
        if (read_number(parent, CFSTR("class-code"), UINT32_C(0xffffff),
                         &class_code) == 1 &&
            (class_code.value & UINT32_C(0xffff00)) == UINT32_C(0x060400) &&
            (strcmp(plane, kIODeviceTreePlane) == 0 ||
             IOObjectConformsTo(parent, "IOPCIDevice"))) {
            match->has_parent = 1;
            read_identity(parent, &match->parent, report, 1, plane);
            IOObjectRelease(parent);
            return;
        }
        current = parent;
        retained = 1;
    }
    if (retained)
        IOObjectRelease(current);
    warn_report(report, WARN_PARENT_DEPTH_LIMIT, 0);
}

static int compare_matches(const void *left, const void *right)
{
    const struct pci_match *a = left;
    const struct pci_match *b = right;
    int plane_order = strcmp(a->identity.plane, b->identity.plane);
    if (plane_order != 0)
        return plane_order;
    int order = strcmp(a->identity.path, b->identity.path);
    if (order != 0)
        return order;
    return strcmp(a->identity.name, b->identity.name);
}

static void read_context(struct report *report)
{
    io_registry_entry_t chosen = IORegistryEntryFromPath(
        kIOMainPortDefault, "IODeviceTree:/chosen");
    if (chosen == IO_OBJECT_NULL) {
        warn_report(report, WARN_CONTEXT_UNREADABLE, 0);
        return;
    }
    CFTypeRef object = IORegistryEntryCreateCFProperty(
        chosen, CFSTR("boot-args"), kCFAllocatorDefault, 0);
    IOObjectRelease(chosen);
    if (object == NULL) {
        warn_report(report, WARN_CONTEXT_UNREADABLE, 0);
        return;
    }
    char arguments[MAX_BOOT_ARGUMENT_BYTES];
    memset(arguments, 0, sizeof(arguments));
    int valid = 0;
    if (CFGetTypeID(object) == CFStringGetTypeID()) {
        valid = CFStringGetCString((CFStringRef)object, arguments,
                                    sizeof(arguments), kCFStringEncodingUTF8);
    } else if (CFGetTypeID(object) == CFDataGetTypeID()) {
        CFIndex length = CFDataGetLength((CFDataRef)object);
        if (length >= 0 && (uint64_t)length < sizeof(arguments)) {
            if (length > 0)
                memcpy(arguments, CFDataGetBytePtr((CFDataRef)object),
                       (size_t)length);
            const char *first_nul = memchr(arguments, '\0', (size_t)length);
            valid = first_nul == NULL || first_nul == arguments + length - 1;
        }
    }
    CFRelease(object);
    if (!valid) {
        warn_report(report, WARN_CONTEXT_UNREADABLE, 0);
        return;
    }
    report->wegnoegpu_known = 1;
    report->wegnoegpu_present = has_boot_token(arguments, "-wegnoegpu");
    /* Do not retain or emit other boot arguments. */
    memset(arguments, 0, sizeof(arguments));
}

static void append_match(io_registry_entry_t entry, struct report *report,
                         const char *plane, int service_visible)
{
    if (report->count == MAX_MATCHES) {
        warn_report(report, WARN_MATCH_LIMIT, 1);
        return;
    }
    struct pci_match *match = &report->matches[report->count++];
    match->service_visible = service_visible;
    read_identity(entry, &match->identity, report, 0, plane);
    /* Re-read values must still identify this target. */
    if (!match->identity.vendor.present || !match->identity.device.present ||
        match->identity.vendor.value != TARGET_VENDOR ||
        match->identity.device.value != TARGET_DEVICE)
        warn_report(report, WARN_SELECTED_PROPERTY_MALFORMED, 1);
    read_raw(entry, CFSTR("reg"), &match->reg, report);
    read_raw(entry, CFSTR("assigned-addresses"), &match->assigned, report);
    read_flag(entry, CFSTR("disable-gpu"), &match->disable_gpu, report);
    read_flag(entry, CFSTR("pci-device-hidden"), &match->pci_device_hidden,
               report);
    read_parent(entry, match, report, plane);
}

static void collect_services(struct report *report)
{
    CFMutableDictionaryRef matching = IOServiceMatching("IOPCIDevice");
    io_iterator_t iterator = IO_OBJECT_NULL;
    size_t entries = 0;
    if (matching == NULL) {
        warn_report(report, WARN_MATCHING_ALLOCATION, 1);
        return;
    }
    /* IOServiceGetMatchingServices consumes matching, including on failure. */
    if (IOServiceGetMatchingServices(kIOMainPortDefault, matching, &iterator) !=
        KERN_SUCCESS) {
        warn_report(report, WARN_ENUMERATION_FAILED, 1);
        return;
    }
    io_registry_entry_t entry;
    while ((entry = IOIteratorNext(iterator)) != IO_OBJECT_NULL) {
        struct number_property vendor;
        struct number_property device;
        if (++entries > MAX_PCI_ENTRIES) {
            IOObjectRelease(entry);
            warn_report(report, WARN_ENUMERATION_LIMIT, 1);
            break;
        }
        if (read_number(entry, CFSTR("vendor-id"), UINT16_MAX, &vendor) != 1) {
            warn_report(report, WARN_VENDOR_ID_UNREADABLE, 1);
        } else if (vendor.value == TARGET_VENDOR) {
            if (read_number(entry, CFSTR("device-id"), UINT16_MAX, &device) != 1) {
                warn_report(report, WARN_NVIDIA_DEVICE_ID_UNREADABLE, 1);
            } else if (device.value == TARGET_DEVICE) {
                if (report->count == MAX_MATCHES) {
                    warn_report(report, WARN_MATCH_LIMIT, 1);
                } else {
                    append_match(entry, report, kIOServicePlane, 1);
                }
            }
        }
        IOObjectRelease(entry);
    }
    if (!IOIteratorIsValid(iterator))
        warn_report(report, WARN_ENUMERATION_INVALIDATED, 1);
    IOObjectRelease(iterator);
}

static void collect_device_tree(struct report *report)
{
    io_iterator_t iterator = IO_OBJECT_NULL;
    if (IORegistryCreateIterator(kIOMainPortDefault, kIODeviceTreePlane,
                                 kIORegistryIterateRecursively, &iterator) !=
        KERN_SUCCESS) {
        warn_report(report, WARN_DEVICE_TREE_ENUMERATION_FAILED, 1);
        return;
    }
    size_t entries = 0;
    io_registry_entry_t entry;
    while ((entry = IOIteratorNext(iterator)) != IO_OBJECT_NULL) {
        struct number_property vendor;
        struct number_property device;
        if (++entries > MAX_DEVICE_TREE_ENTRIES) {
            IOObjectRelease(entry);
            warn_report(report, WARN_ENUMERATION_LIMIT, 1);
            break;
        }
        int vendor_result = read_number(entry, CFSTR("vendor-id"), UINT16_MAX,
                                        &vendor);
        if (vendor_result < 0) {
            struct number_property class_code;
            int display_candidate =
                read_number(entry, CFSTR("class-code"), UINT32_C(0xffffff),
                            &class_code) == 1 &&
                (class_code.value & UINT32_C(0xff0000)) == UINT32_C(0x030000);
            int target_device =
                read_number(entry, CFSTR("device-id"), UINT16_MAX, &device) == 1 &&
                device.value == TARGET_DEVICE;
            /* Other DeviceTree namespaces can use vendor-id differently.
             * Only a PCI/display candidate makes GPU selection incomplete. */
            warn_report(report, WARN_DEVICE_TREE_ID_MALFORMED,
                        display_candidate || target_device ||
                        IOObjectConformsTo(entry, "IOPCIDevice"));
        } else if (vendor_result == 1 && vendor.value == TARGET_VENDOR) {
            if (read_number(entry, CFSTR("device-id"), UINT16_MAX, &device) != 1)
                warn_report(report, WARN_NVIDIA_DEVICE_ID_UNREADABLE, 1);
            else if (device.value == TARGET_DEVICE)
                append_match(entry, report, kIODeviceTreePlane, 0);
        }
        IOObjectRelease(entry);
    }
    if (!IOIteratorIsValid(iterator))
        warn_report(report, WARN_ENUMERATION_INVALIDATED, 1);
    IOObjectRelease(iterator);
}

static void collect_report(struct report *report)
{
    read_context(report);
    collect_services(report);
    /* Disabled GPUs may remain published only in the DeviceTree plane. */
    if (report->count == 0)
        collect_device_tree(report);
    qsort(report->matches, report->count, sizeof(report->matches[0]),
          compare_matches);
}

static void write_number(FILE *out, const struct number_property *property,
                         unsigned int width)
{
    if (!property->present)
        fputs("null", out);
    else
        fprintf(out, "\"0x%0*" PRIx32 "\"", (int)width, property->value);
}

static void write_identity(FILE *out, const struct pci_identity *identity,
                           int parent)
{
    fputs("{\"registry_plane\":", out);
    json_string(out, identity->plane);
    fputs(",\"registry_path\":", out);
    json_string(out, identity->path);
    fputs(",\"node_name\":", out);
    json_string(out, identity->name);
    fputs(",\"node_class\":", out);
    json_string(out, identity->node_class);
    fputs(",\"vendor_id\":", out);
    write_number(out, &identity->vendor, 4);
    fputs(",\"device_id\":", out);
    write_number(out, &identity->device, 4);
    fputs(",\"class_code\":", out);
    write_number(out, &identity->class_code, 6);
    if (!parent) {
        fputs(",\"subsystem_vendor_id\":", out);
        write_number(out, &identity->subsystem_vendor, 4);
        fputs(",\"subsystem_device_id\":", out);
        write_number(out, &identity->subsystem_device, 4);
        fputs(",\"revision_id\":", out);
        write_number(out, &identity->revision, 2);
    }
    fputc('}', out);
}

static void write_raw(FILE *out, const struct raw_property *property)
{
    if (!property->present) {
        fputs("null", out);
        return;
    }
    fprintf(out, "{\"byte_length\":%" PRIu64 ",\"hex\":\"", property->length);
    for (size_t i = 0; i < property->copied; ++i)
        fprintf(out, "%02x", (unsigned int)property->bytes[i]);
    fprintf(out, "\",\"truncated\":%s}",
            property->length > property->copied ? "true" : "false");
}

static void write_flag(FILE *out, const struct flag_property *flag)
{
    fprintf(out, "{\"present\":%s,\"value\":", flag->present ? "true" : "false");
    if (flag->kind == 1)
        fputs(flag->value ? "true" : "false", out);
    else if (flag->kind == 2)
        fprintf(out, "%" PRIu32, flag->value);
    else
        fputs("null", out);
    fputc('}', out);
}

static void write_report(FILE *out, const struct report *report)
{
    fprintf(out, "{\"format\":1,\"tool\":\"nvidia-pci\",\"version\":\"%s\","
                 "\"target\":{\"vendor_id\":\"0x10de\","
                 "\"device_id\":\"0x1f91\"},\"status\":\"%s\","
                 "\"complete\":%s,\"context\":{\"wegnoegpu_present\":", TOOL_VERSION,
            !report->complete ? "error" : report->count == 0 ? "not_visible" :
                report->matches[0].service_visible ? "found" : "device_tree_only",
            report->complete ? "true" : "false");
    fputs(report->wegnoegpu_known ? report->wegnoegpu_present ? "true" : "false" :
          "null", out);
    fputs("},\"matches\":[", out);
    for (size_t i = 0; i < report->count; ++i) {
        const struct pci_match *match = &report->matches[i];
        if (i != 0)
            fputc(',', out);
        fprintf(out, "{\"service_visible\":%s,\"identity\":",
                match->service_visible ? "true" : "false");
        write_identity(out, &match->identity, 0);
        fputs(",\"raw_properties\":{\"reg\":", out);
        write_raw(out, &match->reg);
        fputs(",\"assigned-addresses\":", out);
        write_raw(out, &match->assigned);
        fputs("},\"flags\":{\"disable-gpu\":", out);
        write_flag(out, &match->disable_gpu);
        fputs(",\"pci-device-hidden\":", out);
        write_flag(out, &match->pci_device_hidden);
        fputs("},\"parent_bridge\":", out);
        if (match->has_parent)
            write_identity(out, &match->parent, 1);
        else
            fputs("null", out);
        fputc('}', out);
    }
    fputs("],\"warnings\":[", out);
    int emitted = 0;
    for (size_t i = 0; i < WARNING_COUNT; ++i) {
        if (report->warnings[i] == 0)
            continue;
        if (emitted++)
            fputc(',', out);
        fprintf(out, "{\"code\":\"%s\",\"count\":%u}",
                warning_names[i], report->warnings[i]);
    }
    fputs("]}\n", out);
}

int main(int argc, char **argv)
{
    if (argc == 2 && strcmp(argv[1], "--help") == 0) {
        puts("Usage: nvidia-pci [--help | --version]\n"
             "Read published IORegistry properties for NVIDIA 10de:1f91.\n"
             "No administrator privileges or device changes are required.\n"
             "DeviceTree fallback is used when no IOService target is visible.\n"
             "A not_visible report does not establish absence or power state.");
        return 0;
    }
    if (argc == 2 && strcmp(argv[1], "--version") == 0) {
        puts("nvidia-pci " TOOL_VERSION);
        return 0;
    }
    if (argc != 1) {
        fputs("Usage: nvidia-pci [--help | --version]\n", stderr);
        return 64;
    }
    struct report report;
    memset(&report, 0, sizeof(report));
    report.complete = 1;
    collect_report(&report);
    write_report(stdout, &report);
    if (fflush(stdout) == EOF || ferror(stdout))
        return 74;
    return report.complete ? 0 : 1;
}
#endif
