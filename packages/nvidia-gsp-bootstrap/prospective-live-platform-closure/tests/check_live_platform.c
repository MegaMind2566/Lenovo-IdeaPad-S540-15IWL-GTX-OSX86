/* SPDX-License-Identifier: MIT; original callers with explicit endpoint fixtures. */
#include "nv.h"
#include "os-interface.h"
#include "gpu/gpu.h"
#include "os/os.h"
#include "../../prospective-first-transaction/record/S540NvidiaGspFirstTransaction.h"
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <sys/wait.h>
#undef memset
#undef memcpy
#undef memcmp
#include <string.h>

typedef struct fixtureLinuxStateTag { NvBool init_on_probe; } nv_linux_state_t;
static nv_linux_state_t linuxState;
static nv_state_t state, foreignState;
static NvU32 checks, unavailable, firstUnavailable, observations;
static NvU64 consoleBytes;
static NvBool bound = NV_TRUE;
static NvU64 transactionGeneration = 9;
nv_linux_state_t *fixtureLinuxState(nv_state_t *nv) { if (nv != &state) _Exit(93); return &linuxState; }
void s540GlobalRmRecordServiceName(const char *name) { if (name && *name) ++observations; }
void s540GlobalRmRecordUnavailable(NvU32 service) { ++unavailable; if (!firstUnavailable) firstUnavailable = service; }
NV_STATUS s540FirstTxnGetSnapshot(const void *nv, S540FirstTxnSnapshot *out) {
    if (!out || !bound || nv != &state) return NV_ERR_INVALID_ARGUMENT;
    memset(out, 0, sizeof(*out)); out->generation = transactionGeneration; out->phase = S540_FIRST_OP;
    out->firstStatus = unavailable ? NV_ERR_NOT_SUPPORTED : NV_OK;
    return NV_OK;
}
void NV_API_CALL os_bug_check(NvU32 code, const char *reason) {
    _Exit(!code && reason && *reason && unavailable && firstUnavailable == 580 ? 91 : 92);
}
int NV_API_CALL nv_printf(NvU32 level, const char *format, ...) { (void)level; (void)format; return 0; }
void NV_API_CALL nv_get_screen_info(nv_state_t *nv, NvU64 *physical,
    NvU32 *width, NvU32 *height, NvU32 *depth, NvU32 *pitch, NvU64 *bytes) {
    if (nv != &state) _Exit(94);
    *physical = 0; *width = *height = *depth = *pitch = 0; *bytes = consoleBytes;
}

NvBool original_os_is_bif_reset_supported(void *);
NV_STATUS original_os_allocate_temporary_file(void **, NvU64);
void original_os_close_file(void *);
NV_STATUS original_os_read_file(void *, NvU8 *, NvU64, NvU64);
NV_STATUS original_os_write_file(void *, NvU8 *, NvU64, NvU64);
void control_osModifyGpuSwStatePersistence(OS_GPU_INFO *, NvBool);
NV_STATUS control_osAllocateTemporaryFile(void **, NvU64);
void control_osCloseFile(void *);
NV_STATUS control_osReadFromFile(void *, NvU8 *, NvU64, NvU64);
NV_STATUS control_osWriteToFile(void *, NvU8 *, NvU64, NvU64);
NvBool control_rm_get_uefi_console_status(nv_state_t *);

#define EXACT(name, type) _Static_assert(__builtin_types_compatible_p(__typeof__(&name), type), #name " original ABI")
EXACT(os_is_bif_reset_supported, NvBool (NV_API_CALL *)(void *));
EXACT(os_allocate_temporary_file, NV_STATUS (NV_API_CALL *)(void **, NvU64));
EXACT(os_close_file, void (NV_API_CALL *)(void *));
EXACT(os_read_file, NV_STATUS (NV_API_CALL *)(void *, NvU8 *, NvU64, NvU64));
EXACT(os_write_file, NV_STATUS (NV_API_CALL *)(void *, NvU8 *, NvU64, NvU64));
EXACT(os_disable_console_access, void (NV_API_CALL *)(void));
EXACT(os_enable_console_access, void (NV_API_CALL *)(void));
#define EXPECT(x) do { ++checks; if (!(x)) { fprintf(stderr, "live platform line%d\n", __LINE__); return 1; } } while (0)

static NvBool panicCase(NvU32 mode) {
    pid_t child = fork(); int result = 0;
    if (child < 0) return NV_FALSE;
    if (!child) {
        if (mode == 0) os_disable_console_access();
        else if (mode == 1) os_enable_console_access();
        else if (mode == 2) os_close_file((void *)(NvUPtr)1);
        else if (mode == 3) (void)os_is_bif_reset_supported(NULL);
        else if (mode == 4) (void)os_is_bif_reset_supported(&foreignState);
        else if (mode == 5) { bound = NV_FALSE; (void)os_is_bif_reset_supported(&state); }
        else { transactionGeneration = 0; (void)os_is_bif_reset_supported(&state); }
        _Exit(95);
    }
    return waitpid(child, &result, 0) == child && WIFEXITED(result) && WEXITSTATUS(result) == 91;
}

int main(void) {
    NvU8 buffer[8], old[8]; void *file = (void *)(NvUPtr)0x1234, *originalFile = file;
    NvU32 i, failures;
    memset(&state, 0, sizeof(state)); memset(buffer, 0xa5, sizeof(buffer)); memcpy(old, buffer, sizeof(old));
    linuxState.init_on_probe = NV_FALSE;
    EXPECT(original_os_is_bif_reset_supported(&state) == NV_TRUE);
    EXPECT(os_is_bif_reset_supported(&state) == NV_TRUE);
    EXPECT(osIsBifResetSupported(&state) == NV_TRUE);
    control_osModifyGpuSwStatePersistence(&state, NV_TRUE);
    EXPECT((state.flags & NV_FLAG_PERSISTENT_SW_STATE) != 0);
    control_osModifyGpuSwStatePersistence(&state, NV_FALSE);
    EXPECT((state.flags & NV_FLAG_PERSISTENT_SW_STATE) == 0);
    linuxState.init_on_probe = NV_TRUE;
    EXPECT(original_os_is_bif_reset_supported(&state) == NV_FALSE);
    EXPECT(unavailable == 0);

    EXPECT(original_os_allocate_temporary_file(&originalFile, 1024) == NV_ERR_OPERATING_SYSTEM);
    EXPECT(originalFile == (void *)(NvUPtr)0x1234);
    EXPECT(control_osAllocateTemporaryFile(&file, 1024) == NV_ERR_OPERATING_SYSTEM);
    EXPECT(file == originalFile && unavailable == 1 && firstUnavailable == 580);
    EXPECT(os_allocate_temporary_file(NULL, 0) == NV_ERR_OPERATING_SYSTEM);
    EXPECT(original_os_read_file(file, buffer, sizeof(buffer), 9) == NV_ERR_NOT_SUPPORTED);
    EXPECT(control_osReadFromFile(file, buffer, sizeof(buffer), 9) == NV_ERR_NOT_SUPPORTED);
    EXPECT(memcmp(buffer, old, sizeof(buffer)) == 0);
    EXPECT(original_os_write_file(file, buffer, sizeof(buffer), 9) == NV_ERR_NOT_SUPPORTED);
    EXPECT(control_osWriteToFile(file, buffer, sizeof(buffer), 9) == NV_ERR_NOT_SUPPORTED);
    EXPECT(memcmp(buffer, old, sizeof(buffer)) == 0 && file == originalFile);
    failures = unavailable;
    original_os_close_file(NULL); control_osCloseFile(NULL);
    EXPECT(unavailable == failures);
    EXPECT(firstUnavailable == 580);
    consoleBytes = 0;
    EXPECT(control_rm_get_uefi_console_status(&state) == NV_FALSE);
    consoleBytes = 4096;
    EXPECT(control_rm_get_uefi_console_status(&state) == NV_TRUE);
    consoleBytes = 0;
    for (i = 0; i < 7; ++i) EXPECT(panicCase(i));
    EXPECT(os_is_bif_reset_supported(&state) == NV_TRUE && firstUnavailable == 580);
    EXPECT(observations != 0 && unavailable == failures);
    printf("{\"format\":1,\"component\":\"nvidia-prospective-live-platform-closure\","
        "\"status\":\"passed\",\"checks\":%u,\"failures\":0,"
        "\"execution\":\"native-user-space\",\"kernel_execution\":\"not_tested\",\"gpu_access\":false,"
        "\"official_bodies\":5,\"actual_callers\":7,\"callbacks\":7,\"fail_stop_cases\":7,"
        "\"linux_layout_and_transaction_identity_fixtures\":true,\"console_metadata_fixture\":true,"
        "\"original_entry_admission\":false}\n", checks);
    return 0;
}
