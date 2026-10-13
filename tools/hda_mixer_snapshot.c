/*
 * Read-only VoodooHDA 3.6.8 mixer snapshot.
 * Wire ABI: CloverHackyColor/VoodooHDA, commit
 * 8c7e8e2ce6de0a917be663a3192857955288c937, tranc/Shared.h.
 *
 * No external action method is called. In particular this program never sends
 * SetMixer, GetMixers, SetMath, pin-dump actions, or codec verbs. Memory type
 * 0x3000 refreshes a copy of cached mixer values inside the driver; 0x2000 is
 * only the already existing initialization/message buffer.
 *
 * Build on macOS: clang -std=c11 -Wall -Wextra -Werror -mmacosx-version-min=13.0
 *   -arch x86_64 hda_mixer_snapshot.c -framework IOKit -framework CoreFoundation
 *   -o hda_mixer_snapshot
 */

#include <CoreFoundation/CoreFoundation.h>
#include <IOKit/IOKitLib.h>
#include <mach/mach.h>
#include <mach/mach_vm.h>
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#define VHDA_CLASS "VoodooHDADevice"
#define SOURCE_PIN "8c7e8e2ce6de0a917be663a3192857955288c937"
#define MIXER_COUNT 25U
#define NAME_LENGTH 32U
#define MEMORY_MIXERS 0x3000U
#define MEMORY_MESSAGES 0x2000U
#define MAX_BUFFER_SIZE (16U * 1024U * 1024U)
#define MAX_CONTROLLERS 16U

/* C _Bool has the one-byte layout of the pinned driver's C++ bool. */
typedef struct {
    uint8_t mix_id;
    uint8_t value;
    char name[NAME_LENGTH];
    bool enabled;
    uint8_t padding[5];
} MixerInfo;

typedef struct {
    char name[NAME_LENGTH];
    MixerInfo mixers[MIXER_COUNT];
    uint8_t tab_count;
    bool vectorize;
    bool use_stereo;
    uint8_t noise_level;
    uint8_t stereo_base;
    uint8_t padding[3];
} ChannelInfo;

_Static_assert(sizeof(bool) == 1, "Unsupported bool ABI");
_Static_assert(sizeof(MixerInfo) == 40, "Unexpected mixer ABI");
_Static_assert(offsetof(MixerInfo, enabled) == 34, "Unexpected mixer offsets");
_Static_assert(sizeof(ChannelInfo) == 1040, "Unexpected channel ABI");
_Static_assert(offsetof(ChannelInfo, tab_count) == 1032, "Unexpected channel offsets");

static void json_string(FILE *out, const char *text, size_t limit)
{
    fputc('"', out);
    for (size_t i = 0; i < limit && text[i] != '\0'; ++i) {
        unsigned char c = (unsigned char) text[i];
        if (c == '"' || c == '\\') {
            fputc('\\', out);
            fputc(c, out);
        } else if (c < 0x20 || c >= 0x7f) {
            fprintf(out, "\\u%04x", (unsigned int) c);
        } else {
            fputc(c, out);
        }
    }
    fputc('"', out);
}

static void report_named_error(FILE *out, const char *field, const char *operation,
                               kern_return_t error)
{
    json_string(out, field, strlen(field));
    fputs(":{\"operation\":", out);
    json_string(out, operation, strlen(operation));
    fprintf(out, ",\"code\":\"0x%08x\"}", (unsigned int) error);
}

static void report_error(FILE *out, const char *operation, kern_return_t error)
{
    report_named_error(out, "error", operation, error);
}

static int read_pci_id(io_registry_entry_t provider, CFStringRef key, uint32_t *value)
{
    CFTypeRef property = IORegistryEntryCreateCFProperty(provider, key,
                                                       kCFAllocatorDefault, 0);
    int result = 0;
    if (property && CFGetTypeID(property) == CFDataGetTypeID() &&
        CFDataGetLength((CFDataRef) property) == 4) {
        const UInt8 *b = CFDataGetBytePtr((CFDataRef) property);
        *value = (uint32_t) b[0] | (uint32_t) b[1] << 8 |
                 (uint32_t) b[2] << 16 | (uint32_t) b[3] << 24;
        result = 1;
    }
    if (property) CFRelease(property);
    return result;
}

static void print_provider(FILE *out, io_service_t service)
{
    io_registry_entry_t provider = IO_OBJECT_NULL;
    uint32_t vendor, device;
    fputs("\"pci\":", out);
    if (IORegistryEntryGetParentEntry(service, kIOServicePlane, &provider) == KERN_SUCCESS &&
        IOObjectConformsTo(provider, "IOPCIDevice") &&
        read_pci_id(provider, CFSTR("vendor-id"), &vendor) &&
        read_pci_id(provider, CFSTR("device-id"), &device)) {
        fprintf(out, "{\"vendor\":\"0x%04" PRIx32 "\",\"device\":\"0x%04" PRIx32 "\"}",
                vendor, device);
    } else {
        fputs("null", out);
    }
    if (provider != IO_OBJECT_NULL) IOObjectRelease(provider);
}

/* These memory selectors return snapshots. Never write to a mapped address. */
static kern_return_t map_snapshot(io_connect_t connection, uint32_t selector,
                                 mach_vm_address_t *address, mach_vm_size_t *size)
{
    *address = 0;
    *size = 0;
    return IOConnectMapMemory64(connection, selector, mach_task_self(), address, size,
                                kIOMapAnywhere | kIOMapDefaultCache | kIOMapReadOnly);
}

static int valid_channels(const unsigned char *bytes, size_t size, unsigned int *count)
{
    if (size < MIXER_COUNT * sizeof(ChannelInfo)) return 0;
    *count = bytes[offsetof(ChannelInfo, tab_count)];
    if (*count == 0 || *count > MIXER_COUNT) return 0;
    for (unsigned int i = 0; i < *count; ++i) {
        const unsigned char *channel = bytes + i * sizeof(ChannelInfo);
        if (channel[offsetof(ChannelInfo, tab_count)] != *count ||
            !memchr(channel, '\0', NAME_LENGTH)) return 0;
        for (unsigned int j = 0; j < MIXER_COUNT; ++j) {
            const unsigned char *m = channel + offsetof(ChannelInfo, mixers) +
                                     j * sizeof(MixerInfo);
            unsigned int enabled = m[offsetof(MixerInfo, enabled)];
            if (enabled > 1) return 0;
            if (enabled && (m[offsetof(MixerInfo, value)] > 100 ||
                m[offsetof(MixerInfo, mix_id)] != (j == 24 ? 0 : j + 1) ||
                !memchr(m + offsetof(MixerInfo, name), '\0', NAME_LENGTH))) return 0;
        }
    }
    return 1;
}

static void print_channels(FILE *out, const unsigned char *bytes, unsigned int count)
{
    fputs("\"tabs\":[", out);
    for (unsigned int i = 0; i < count; ++i) {
        ChannelInfo channel;
        memcpy(&channel, bytes + i * sizeof channel, sizeof channel);
        if (i) fputc(',', out);
        fprintf(out, "{\"index\":%u,\"name\":", i);
        json_string(out, channel.name, sizeof channel.name);
        fputs(",\"mixers\":[", out);
        unsigned int printed = 0;
        for (unsigned int j = 0; j < MIXER_COUNT; ++j) {
            const MixerInfo *m = &channel.mixers[j];
            if (!m->enabled) continue;
            if (printed++) fputc(',', out);
            fprintf(out, "{\"id\":%u,\"name\":", (unsigned int) m->mix_id);
            json_string(out, m->name, sizeof m->name);
            fprintf(out, ",\"cached_left_percent\":%u}", (unsigned int) m->value);
        }
        fputs("]}", out);
    }
    fputc(']', out);
}

static int save_messages(int directory, unsigned int index, const void *bytes, size_t size)
{
    char filename[64];
    snprintf(filename, sizeof filename, "controller-%u-init-buffer.txt", index);
    int fd = openat(directory, filename, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0600);
    if (fd == -1) return -1;
    const unsigned char *p = bytes;
    size_t written = 0;
    while (written < size) {
        ssize_t amount = write(fd, p + written, size - written);
        if (amount < 0 && errno == EINTR) continue;
        if (amount <= 0) { close(fd); return -1; }
        written += (size_t) amount;
    }
    if (close(fd) != 0) return -1;
    return 0;
}

static int snapshot_controller(FILE *out, io_service_t service, unsigned int index, int directory)
{
    io_connect_t connection = IO_OBJECT_NULL;
    mach_vm_address_t address = 0;
    mach_vm_size_t size = 0;
    unsigned char *copy = NULL;
    unsigned int count = 0;
    int failed = 0;
    fprintf(out, "{\"index\":%u,", index);
    print_provider(out, service);
    fputc(',', out);
    kern_return_t result = IOServiceOpen(service, mach_task_self(), 0, &connection);
    if (result != KERN_SUCCESS) {
        report_error(out, "IOServiceOpen", result);
        failed = 1;
        goto done;
    }
    result = map_snapshot(connection, MEMORY_MIXERS, &address, &size);
    if (result != KERN_SUCCESS) {
        report_error(out, "map-0x3000", result);
        failed = 1;
        goto done;
    }
    if (address == 0 || size < MIXER_COUNT * sizeof(ChannelInfo) || size > MAX_BUFFER_SIZE) {
        fputs("\"error\":{\"operation\":\"validate-mixer-buffer-size\"}", out);
        failed = 1;
        goto done;
    }
    copy = malloc(MIXER_COUNT * sizeof(ChannelInfo));
    if (!copy) {
        fputs("\"error\":{\"operation\":\"allocate-mixer-snapshot\"}", out);
        failed = 1;
        goto done;
    }
    memcpy(copy, (const void *) (uintptr_t) address, MIXER_COUNT * sizeof(ChannelInfo));
    if (!valid_channels(copy, MIXER_COUNT * sizeof(ChannelInfo), &count)) {
        fputs("\"error\":{\"operation\":\"validate-pinned-3.6.8-ABI\"}", out);
        failed = 1;
        goto done;
    }
    print_channels(out, copy, count);
    if (directory != -1) {
        fputc(',', out);
        result = map_snapshot(connection, MEMORY_MESSAGES, &address, &size);
        if (result != KERN_SUCCESS) {
            report_named_error(out, "init_buffer_error", "map-0x2000", result);
        } else if (!address || !size || size > MAX_BUFFER_SIZE) {
            fputs("\"init_buffer_error\":{\"operation\":\"validate-init-buffer-size\"}", out);
        } else {
            const char *messages = (const char *) (uintptr_t) address;
            const char *end = memchr(messages, '\0', (size_t) size);
            size_t length = end ? (size_t) (end - messages) : (size_t) size;
            if (save_messages(directory, index, messages, length) == 0) {
                fprintf(out, "\"init_buffer\":{\"file\":\"controller-%u-init-buffer.txt\","
                             "\"bytes\":%zu,\"nul_terminated\":%s,\"refresh_requested\":false}",
                        index, length, end ? "true" : "false");
            } else {
                fputs("\"init_buffer_error\":{\"operation\":\"save-init-buffer\"}", out);
                failed = 1;
            }
        }
    }
done:
    free(copy);
    /* Upstream explicitly forbids IOConnectUnmapMemory for this user client.
     * Close the connection once, then let process exit dispose the mappings. */
    if (connection != IO_OBJECT_NULL) {
        result = IOServiceClose(connection);
        if (result != KERN_SUCCESS) {
            fprintf(stderr, "controller %u: IOServiceClose failed (0x%08x)\n", index,
                    (unsigned int) result);
            failed = 1;
        }
    }
    fputc('}', out);
    return failed;
}

int main(int argc, char **argv)
{
    int directory = -1;
    FILE *out = stdout;
    if (argc == 2 && strcmp(argv[1], "--help") == 0) {
        puts("Usage: hda_mixer_snapshot [--output-dir EXISTING_DIRECTORY]\n"
             "Reads VoodooHDA 3.6.8 cached mixer state. Does not change audio controls.\n"
             "With --output-dir, saves mixers.json and existing init buffers; never overwrites files.");
        return 0;
    }
    if (argc == 3 && strcmp(argv[1], "--output-dir") == 0) {
        directory = open(argv[2], O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
        if (directory == -1) { perror("output directory"); return 2; }
        int fd = openat(directory, "mixers.json", O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0600);
        if (fd == -1) { perror("mixers.json"); close(directory); return 2; }
        out = fdopen(fd, "w");
        if (!out) { perror("fdopen"); close(fd); close(directory); return 2; }
    } else if (argc != 1) {
        fputs("Usage: hda_mixer_snapshot [--output-dir EXISTING_DIRECTORY]\n", stderr);
        return 2;
    }
    fputs("{\"format\":1,\"source_pin\":\"" SOURCE_PIN "\","
          "\"scope\":\"cached-left-mixer-percent; not dB or a live amplifier readback\","
          "\"controllers\":[", out);
    io_iterator_t iterator = IO_OBJECT_NULL;
    io_service_t service = IO_OBJECT_NULL;
    kern_return_t result = IOServiceGetMatchingServices(kIOMainPortDefault,
                                                       IOServiceMatching(VHDA_CLASS), &iterator);
    unsigned int count = 0;
    int failed = 0;
    if (result == KERN_SUCCESS) {
        while ((service = IOIteratorNext(iterator)) != IO_OBJECT_NULL) {
            if (count >= MAX_CONTROLLERS) {
                fputs("Too many VoodooHDA controllers; snapshot stopped.\n", stderr);
                IOObjectRelease(service);
                failed = 1;
                break;
            }
            if (count) fputc(',', out);
            failed |= snapshot_controller(out, service, ++count, directory);
            IOObjectRelease(service);
        }
        IOObjectRelease(iterator);
    } else {
        fprintf(stderr, "IOServiceGetMatchingServices failed (0x%08x)\n", (unsigned int) result);
        failed = 1;
    }
    fprintf(out, "],\"controller_count\":%u}\n", count);
    if (!count) { fputs("No VoodooHDADevice found.\n", stderr); failed = 1; }
    if (ferror(out)) failed = 1;
    if (out != stdout && fclose(out) != 0) failed = 1;
    if (directory != -1) close(directory);
    return failed ? 1 : 0;
}
