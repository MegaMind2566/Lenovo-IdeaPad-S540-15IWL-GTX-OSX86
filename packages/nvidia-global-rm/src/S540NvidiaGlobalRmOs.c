// SPDX-License-Identifier: MIT
// Forced-include S540GlobalRmNamespace.h when compiling this original ABI
// facade. It must never be linked without that namespace isolation.
#include "nv.h"
#include "os-interface.h"
#include "S540NvidiaGlobalRm.h"
#include "S540NvidiaGlobalRmProfile.h"
#include "../../nvidia-darwin-services/src/S540NvidiaDarwinServices.h"

extern NV_STATUS RmWriteRegistryDword(nv_state_t *, const char *, NvU32);
extern NV_STATUS RmReadRegistryDword(nv_state_t *, const char *, NvU32 *);
extern NvS32 s540GlobalRmLogV(const char *, va_list);
extern NvS32 s540GlobalRmFormatV(char *, NvU32, const char *, va_list);

enum {
    CALL_ALLOC, CALL_FREE, CALL_MUTEX, CALL_SPIN, CALL_RW, CALL_SEMA,
    CALL_WAIT, CALL_THREAD, CALL_TIME, CALL_CONTEXT, CALL_WORK, CALL_DELAY,
    CALL_PLATFORM, CALL_CPU, CALL_PROCESS, CALL_SECURITY, CALL_STRING,
    CALL_REGISTRY, CALL_DEBUG, CALL_LOG, CALL_MEMORY, CALL_PID
};
#define MARK(which) do { s540GlobalRmRecordService(which); \
                         s540GlobalRmRecordServiceName(__func__); } while (0)
#define STATUS_BRIDGE(name, type, args, call, mark) \
    type name args { MARK(mark); return s540Darwin_##name call; }
#define VOID_BRIDGE(name, args, call, mark) \
    void name args { MARK(mark); s540Darwin_##name call; }

NV_STATUS os_alloc_mem(void **out, NvU64 bytes)
{
    void *allocation;
    MARK(CALL_ALLOC);
    if (!out || !bytes) return NV_ERR_INVALID_ARGUMENT;
    if (!s540Darwin_os_semaphore_may_sleep()) {
        s540GlobalRmRecordUnavailable(CALL_ALLOC);
        return NV_ERR_INVALID_STATE;
    }
    allocation = s540GlobalRmHostAllocateOriginal(bytes);
    if (!allocation) return NV_ERR_NO_MEMORY;
    *out = allocation;
    return NV_OK;
}
void os_free_mem(void *pointer) { MARK(CALL_FREE); s540GlobalRmHostFreeOriginal(pointer); }

STATUS_BRIDGE(os_alloc_mutex, NV_STATUS, (void **p), (p), CALL_MUTEX)
VOID_BRIDGE(os_free_mutex, (void *p), (p), CALL_MUTEX)
STATUS_BRIDGE(os_acquire_mutex, NV_STATUS, (void *p), (p), CALL_MUTEX)
STATUS_BRIDGE(os_cond_acquire_mutex, NV_STATUS, (void *p), (p), CALL_MUTEX)
VOID_BRIDGE(os_release_mutex, (void *p), (p), CALL_MUTEX)
STATUS_BRIDGE(os_alloc_spinlock, NV_STATUS, (void **p), (p), CALL_SPIN)
VOID_BRIDGE(os_free_spinlock, (void *p), (p), CALL_SPIN)
STATUS_BRIDGE(os_acquire_spinlock, NvU64, (void *p), (p), CALL_SPIN)
VOID_BRIDGE(os_release_spinlock, (void *p, NvU64 level), (p, level), CALL_SPIN)
STATUS_BRIDGE(os_alloc_rwlock, void *, (void), (), CALL_RW)
VOID_BRIDGE(os_free_rwlock, (void *p), (p), CALL_RW)
STATUS_BRIDGE(os_acquire_rwlock_read, NV_STATUS, (void *p), (p), CALL_RW)
STATUS_BRIDGE(os_acquire_rwlock_write, NV_STATUS, (void *p), (p), CALL_RW)
STATUS_BRIDGE(os_cond_acquire_rwlock_read, NV_STATUS, (void *p), (p), CALL_RW)
STATUS_BRIDGE(os_cond_acquire_rwlock_write, NV_STATUS, (void *p), (p), CALL_RW)
VOID_BRIDGE(os_release_rwlock_read, (void *p), (p), CALL_RW)
VOID_BRIDGE(os_release_rwlock_write, (void *p), (p), CALL_RW)
STATUS_BRIDGE(os_alloc_semaphore, void *, (NvU32 n), (n), CALL_SEMA)
VOID_BRIDGE(os_free_semaphore, (void *p), (p), CALL_SEMA)
STATUS_BRIDGE(os_acquire_semaphore, NV_STATUS, (void *p), (p), CALL_SEMA)
STATUS_BRIDGE(os_cond_acquire_semaphore, NV_STATUS, (void *p), (p), CALL_SEMA)
STATUS_BRIDGE(os_release_semaphore, NV_STATUS, (void *p), (p), CALL_SEMA)
STATUS_BRIDGE(os_alloc_wait_queue, NV_STATUS, (os_wait_queue **p), (p), CALL_WAIT)
VOID_BRIDGE(os_free_wait_queue, (os_wait_queue *p), (p), CALL_WAIT)
VOID_BRIDGE(os_wait_interruptible, (os_wait_queue *p), (p), CALL_WAIT)
VOID_BRIDGE(os_wait_uninterruptible, (os_wait_queue *p), (p), CALL_WAIT)
VOID_BRIDGE(os_wake_up, (os_wait_queue *p), (p), CALL_WAIT)
STATUS_BRIDGE(os_get_current_thread, NV_STATUS, (NvU64 *p), (p), CALL_THREAD)
STATUS_BRIDGE(os_get_system_time, NV_STATUS, (NvU32 *s, NvU32 *u), (s, u), CALL_TIME)
STATUS_BRIDGE(os_get_monotonic_time_ns, NvU64, (void), (), CALL_TIME)
STATUS_BRIDGE(os_get_monotonic_time_ns_hr, NvU64, (void), (), CALL_TIME)
STATUS_BRIDGE(os_get_monotonic_tick_resolution_ns, NvU64, (void), (), CALL_TIME)
STATUS_BRIDGE(os_is_isr, NvBool, (void), (), CALL_CONTEXT)
STATUS_BRIDGE(os_semaphore_may_sleep, NvBool, (void), (), CALL_CONTEXT)
STATUS_BRIDGE(os_delay, NV_STATUS, (NvU32 n), (n), CALL_DELAY)
STATUS_BRIDGE(os_delay_us, NV_STATUS, (NvU32 n), (n), CALL_DELAY)
STATUS_BRIDGE(os_queue_work_item, NV_STATUS, (struct os_work_queue *p, void *d), (p, d), CALL_WORK)
STATUS_BRIDGE(os_flush_work_queue, NV_STATUS, (struct os_work_queue *p, NvBool b), (p, b), CALL_WORK)
STATUS_BRIDGE(os_is_queue_flush_ongoing, NvBool, (struct os_work_queue *p), (p), CALL_WORK)
STATUS_BRIDGE(os_get_current_process, NvU32, (void), (), CALL_PROCESS)
VOID_BRIDGE(os_get_current_process_name, (char *p, NvU32 n), (p, n), CALL_PROCESS)
STATUS_BRIDGE(os_get_euid, NV_STATUS, (NvU32 *p), (p), CALL_SECURITY)
STATUS_BRIDGE(os_is_administrator, NvBool, (void), (), CALL_SECURITY)
STATUS_BRIDGE(os_check_access, NvBool, (RsAccessRight right), (right), CALL_SECURITY)
STATUS_BRIDGE(os_get_current_process_flags, NvU32, (void), (), CALL_PROCESS)
STATUS_BRIDGE(os_get_pid_info, void *, (void), (), CALL_PID)
VOID_BRIDGE(os_put_pid_info, (void *p), (p), CALL_PID)
STATUS_BRIDGE(os_find_ns_pid, NV_STATUS, (void *p, NvU32 *n), (p, n), CALL_PID)
STATUS_BRIDGE(os_is_init_ns, NvBool, (void), (), CALL_PID)
STATUS_BRIDGE(os_get_random_bytes, NV_STATUS, (NvU8 *p, NvU16 n), (p, n), CALL_SECURITY)
STATUS_BRIDGE(os_schedule, NV_STATUS, (void), (), CALL_CONTEXT)
VOID_BRIDGE(os_flush_cpu_write_combine_buffer, (void), (), CALL_MEMORY)

static const S540NvidiaGlobalRmPlatformFacts *facts(void)
{
    // Every caller is dominated by HostInitialize's complete-fact gate.
    return s540GlobalRmPlatformFacts();
}
NvBool nv_is_chassis_notebook(void) { MARK(CALL_PLATFORM); return facts()->notebook; }
NvBool nv_acpi_is_battery_present(void) { MARK(CALL_PLATFORM); return facts()->battery; }
NvBool nv_platform_supports_s0ix(void) { MARK(CALL_PLATFORM); return facts()->s0ix; }
NvBool os_is_efi_enabled(void) { MARK(CALL_PLATFORM); return facts()->efi; }
NvBool os_is_vgx_hyper(void) { MARK(CALL_PLATFORM); return facts()->vgpuHypervisor; }
NvBool os_is_nvswitch_present(void) { MARK(CALL_PLATFORM); return facts()->nvSwitch; }
NvU32 os_get_cpu_count(void) { MARK(CALL_CPU); return facts()->cpuCount; }
NvU64 os_get_cpu_frequency(void) { MARK(CALL_CPU); return facts()->cpuFrequencyHz; }
STATUS_BRIDGE(os_get_cpu_number, NvU32, (void), (), CALL_CPU)
NV_STATUS os_get_version_info(os_version_info *out)
{
    const S540NvidiaGlobalRmPlatformFacts *p = facts();
    MARK(CALL_PLATFORM);
    if (!out || !p) return NV_ERR_NOT_READY;
    out->os_major_version = p->osMajor;
    out->os_minor_version = p->osMinor;
    out->os_build_number = p->osBuild;
    out->os_build_version_str = p->osVersion;
    out->os_build_date_plus_str = p->osDate;
    return NV_OK;
}

// Original Linux builds seed their RM registry from Linux module parameters.
// Darwin has no such parameter table. Publish and verify the selected original
// power/NVLink policy transaction; never continue after a partial profile.
NV_STATUS os_registry_init(void)
{
    MARK(CALL_REGISTRY);
    return s540GlobalRmInitializeRegistryProfile();
}

static NvU32 debugLevel = ~0U;
void os_dbg_init(void)
{
    NvU32 requested = 0;
    MARK(CALL_DEBUG);
    if (RmReadRegistryDword(NULL, "ResmanDebugLevel", &requested) == NV_OK && requested != ~0U)
        debugLevel = requested;
}
void os_dbg_set_level(NvU32 level) { MARK(CALL_DEBUG); debugLevel = level; }
void os_dbg_breakpoint(void)
{
    // Assertions invalidate this loaded profile. This boundary deliberately
    // does not replace an assertion with a successful service implementation.
    MARK(CALL_DEBUG);
    s540GlobalRmRecordUnavailable(CALL_DEBUG);
}
int nv_printf(NvU32 level, const char *format, ...)
{
    va_list arguments;
    NvS32 result;
    MARK(CALL_LOG);
    if (!format) return -1;
    if (!(level & debugLevel)) return 0;
    va_start(arguments, format);
    result = s540GlobalRmLogV(format, arguments);
    va_end(arguments);
    return result;
}
void out_string(const char *text)
{
    if (text) nv_printf(~0U, "%s", text);
}
NvS32 os_snprintf(char *buffer, NvU32 length, const char *format, ...)
{
    va_list arguments;
    NvS32 result;
    MARK(CALL_STRING);
    va_start(arguments, format);
    result = s540GlobalRmFormatV(buffer, length, format, arguments);
    va_end(arguments);
    return result;
}
NvS32 os_vsnprintf(char *buffer, NvU32 length, const char *format, va_list arguments)
{
    MARK(CALL_STRING);
    return s540GlobalRmFormatV(buffer, length, format, arguments);
}
char *os_string_copy(char *to, const char *from)
{
    char *start = to;
    MARK(CALL_STRING);
    do { *to++ = *from; } while (*from++);
    return start;
}
NvU32 os_string_length(const char *text)
{
    NvU32 length = 0;
    MARK(CALL_STRING);
    while (text[length]) ++length;
    return length;
}
NvS32 os_string_compare(const char *a, const char *b)
{
    MARK(CALL_STRING);
    while (*a && *a == *b) { ++a; ++b; }
    return (NvS32)(NvU8)*a - (NvS32)(NvU8)*b;
}
void *os_mem_copy(void *to, const void *from, NvU32 size)
{
    NvU8 *d = to;
    const NvU8 *s = from;
    MARK(CALL_MEMORY);
    while (size--) *d++ = *s++;
    return to;
}
void *os_mem_set(void *to, NvU8 value, NvU32 size)
{
    NvU8 *d = to;
    MARK(CALL_MEMORY);
    while (size--) *d++ = value;
    return to;
}
NvS32 os_mem_cmp(const NvU8 *a, const NvU8 *b, NvU32 size)
{
    MARK(CALL_MEMORY);
    while (size--) {
        if (*a != *b) return (NvS32)*a - (NvS32)*b;
        ++a; ++b;
    }
    return 0;
}

// These are platform ABI mechanism declarations, not guessed device facts:
// Darwin offers neither Linux DMA-BUF nor Linux IMEX capability-file support.
NvU64 os_page_size = 4096;
NvU64 os_max_page_size = 4096;
NvU64 os_page_mask = ~4095ULL;
NvU8 os_page_shift = 12;
NvBool os_dma_buf_enabled = NV_FALSE;
NvBool os_imex_channel_is_supported = NV_FALSE;
NvBool os_cc_enabled = NV_FALSE;
NvBool os_cc_sev_snp_enabled = NV_FALSE;
NvBool os_cc_snp_vtom_enabled = NV_FALSE;
NvBool os_cc_tdx_enabled = NV_FALSE;
NvBool os_cc_sme_enabled = NV_FALSE;
nv_cap_t *nvidia_caps_root = NULL;

#undef STATUS_BRIDGE
#undef VOID_BRIDGE
#undef MARK
