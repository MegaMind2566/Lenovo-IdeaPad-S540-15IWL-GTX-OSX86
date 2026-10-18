// SPDX-License-Identifier: MIT
// Original ABI calls into real tracked allocation, scheduling and fault-recoverable OS-copy
// backends. The fatal diagnostic endpoint is an explicit process-exit fixture.
#include "nv.h"
#include "os-interface.h"
#include "nvlink_os.h"
#include "../src/S540NvidiaGlobalRm.h"
#include "../../nvidia-darwin-services/src/S540NvidiaDarwinServices.h"
#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <sys/wait.h>
#include <unistd.h>

extern void hostServicesNativeContext(NvBool interruptContext, NvBool enabled);
static unsigned checks;
static void require(NvBool passed, const char *reason)
{
    ++checks;
    if (!passed) { fprintf(stderr, "Host services failed: %s\n", reason); exit(1); }
}
void NV_API_CALL os_bug_check(NvU32 code, const char *reason)
{
    (void)code; (void)reason; _Exit(47);
}
static NvBool fatalCase(unsigned mode)
{
    pid_t child = fork();
    int status = 0;
    if (child < 0) return NV_FALSE;
    if (!child) {
        if (!mode) nvlink_assert(0);
        else { hostServicesNativeContext(NV_TRUE, NV_TRUE); nvlink_sleep(1); }
        _Exit(3);
    }
    return waitpid(child, &status, 0) == child && WIFEXITED(status) && WEXITSTATUS(status) == 47;
}
static S540NvidiaGlobalRmPlatformFacts facts(void)
{
    S540NvidiaGlobalRmPlatformFacts out = {0};
    out.format = 1; out.known = S540_GLOBAL_FACT_ALL;
    out.cpuCount = 1; out.cpuFrequencyHz = 2000000000ULL;
    out.osMajor = 25; out.osVersion = out.osDate = "native-host-services-fixture";
    return out;
}
static void fill(void *memory, unsigned value, size_t bytes)
{
    volatile unsigned char *p = memory;
    while (bytes--) *p++ = (unsigned char)value;
}
static int compare(const void *a, const void *b, size_t bytes)
{
    const volatile unsigned char *x = a, *y = b;
    while (bytes--) if (*x++ != *y++) return 1;
    return 0;
}
static NvBool sameByte(const void *memory, size_t bytes, unsigned value)
{
    const unsigned char *p = memory;
    while (bytes--) if (*p++ != value) return NV_FALSE;
    return NV_TRUE;
}
int main(void)
{
    S540NvidiaGlobalRmPlatformFacts host = facts();
    S540NvidiaGlobalRmHostSnapshot snapshot;
    const NvU32 bytes = 2U * 1024U * 1024U + 37U;
    unsigned char *source = malloc(bytes), *destination = malloc(bytes);
    long page = sysconf(_SC_PAGESIZE);
    unsigned char *guard;
    NvU32 i;
    void *empty, *allocation, *second;
    NvU64 before;
    require(source && destination && page > 0, "native buffers and page size available");
    require(s540GlobalRmHostInitialize(&host) == NV_OK, "real tracked allocator initialized");
    for (i = 0; i < bytes; ++i) source[i] = (unsigned char)(i * 29U + 7U);
    fill(destination, 0, bytes);
    require(os_memcpy_from_user(destination, source, bytes) == NV_OK && !compare(destination, source, bytes),
            "original from-user ABI copies multiple bounded OS operations");
    fill(destination, 0, bytes);
    require(os_memcpy_to_user(destination, source, bytes) == NV_OK && !compare(destination, source, bytes),
            "original to-user ABI copies every byte across chunk boundaries");
    require(os_memcpy_from_user(NULL, NULL, 0) == NV_OK &&
            os_memcpy_to_user(NULL, NULL, 0) == NV_OK, "zero copies perform no memory access");
    fill(destination, 0x61, 64);
    require(os_memcpy_from_user(destination, (const void *)(NvUPtr)1, 64) == NV_ERR_INVALID_ADDRESS &&
            sameByte(destination, 64, 0x61), "inaccessible source is an OS error without a native fault");
    require(os_memcpy_to_user((void *)(NvUPtr)1, source, 64) == NV_ERR_INVALID_ADDRESS,
            "inaccessible destination is an OS error without a native fault");
    require(os_memcpy_from_user(destination, (const void *)(~(NvUPtr)0 - 7), 16) == NV_ERR_INVALID_ADDRESS &&
            sameByte(destination, 64, 0x61), "overflowing range is rejected before copying");
    require(os_memcpy_to_user(NULL, source, 1) == NV_ERR_INVALID_ADDRESS &&
            os_memcpy_from_user(destination, NULL, 1) == NV_ERR_INVALID_ADDRESS,
            "nonempty null ranges are refused");
    hostServicesNativeContext(NV_TRUE, NV_TRUE);
    require(os_memcpy_from_user(destination, source, 64) == NV_ERR_INVALID_STATE &&
            os_memcpy_to_user(destination, source, 64) == NV_ERR_INVALID_STATE &&
            sameByte(destination, 64, 0x61), "interrupt context performs no user copy");
    hostServicesNativeContext(NV_FALSE, NV_FALSE);
    require(os_memcpy_from_user(destination, source, 64) == NV_ERR_INVALID_STATE &&
            sameByte(destination, 64, 0x61), "disabled interrupts preserve caller buffer");
    hostServicesNativeContext(NV_FALSE, NV_TRUE);
    guard = mmap(NULL, (size_t)page * 3U, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON, -1, 0);
    require(guard != MAP_FAILED, "native guarded mapping allocated");
    fill(guard, 0x35, (size_t)page * 3U);
    require(mprotect(guard + page, (size_t)page, PROT_NONE) == 0, "middle page inaccessible");
    fill(destination, 0x61, (size_t)page * 2U + 1U);
    require(os_memcpy_from_user(destination, guard, (NvU32)page * 2U) == NV_ERR_INVALID_ADDRESS &&
            destination[page * 2] == 0x61, "faulted copy may change prefix but cannot overrun destination");
    require(os_memcpy_to_user(guard, source, (NvU32)page * 2U) == NV_ERR_INVALID_ADDRESS &&
            guard[page * 2] == 0x35, "faulted write cannot bypass protected page or overrun length");
    require(mprotect(guard, (size_t)page, PROT_READ) == 0 &&
            os_memcpy_to_user(guard, source, 64) == NV_ERR_INVALID_ADDRESS,
            "read-only user destination does not become writable");
    require(munmap(guard, (size_t)page * 3U) == 0, "guarded native mapping released");
    empty = nvlink_malloc(0); allocation = nvlink_malloc(1234); second = nvlink_malloc(1234);
    require(empty && allocation && second && allocation != second && empty != allocation,
            "real NVLink allocations have tracked independent freeable identities");
    s540GlobalRmHostSnapshot(&snapshot);
    require(snapshot.originalLiveAllocations == 3 && snapshot.originalLiveBytes == 2469 &&
            snapshot.externalLiveAllocations == 0 && snapshot.externalLiveBytes == 0,
            "original NVLink ABI allocates in the original ownership domain");
    require(nvlink_memset(allocation, 0x1a5, 1234) == allocation && sameByte(allocation, 1234, 0xa5),
            "NVLink memset writes the truncated byte value");
    require(nvlink_memcpy(second, allocation, 1234) == second && !compare(second, allocation, 1234),
            "NVLink memcpy moves actual caller bytes");
    require(nvlink_memset(NULL, 0, 0) == NULL && nvlink_memcpy(NULL, NULL, 0) == NULL,
            "zero-length NVLink operations touch no storage");
    before = s540Darwin_os_get_monotonic_time_ns(); nvlink_sleep(1);
    require(s540Darwin_os_get_monotonic_time_ns() >= before + 1000000ULL,
            "NVLink sleep uses the real scheduler delay");
    nvlink_assert(1);
    require(fatalCase(0) && fatalCase(1), "failed assertion and forbidden sleep reach fatal endpoint");
    nvlink_free(NULL); nvlink_free(second); nvlink_free(allocation); nvlink_free(empty);
#if defined(NV_GRID_BUILD)
    require(os_is_grid_supported() == NV_TRUE, "GRID build flag reflects actual compiled profile");
#else
    require(os_is_grid_supported() == NV_FALSE, "non-GRID predicate follows original compile-time branch");
#endif
#if defined(NV_GRID_BUILD_CSP)
    require(os_get_grid_csp_support() == NV_GRID_BUILD_CSP, "CSP value reflects actual build definition");
#else
    require(os_get_grid_csp_support() == 0, "absent CSP build definition follows original branch");
#endif
    s540GlobalRmHostSnapshot(&snapshot);
    require(!snapshot.liveAllocations && snapshot.allocations == snapshot.frees &&
            !snapshot.invalidFrees && !snapshot.unavailableCalls && !s540DarwinLiveObjects(),
            "host services release every tracked allocation and OS object");
    require(s540GlobalRmHostShutdown(), "host services finish cleanly");
    free(destination); free(source);
    printf("{\"format\":1,\"component\":\"nvidia-global-host-services\",\"status\":\"passed\",\"checks\":%u,\"failures\":0,\"real_os_copy\":true,\"usercopy_kernel_execution\":false,\"fatal_endpoint_fixture\":true,\"build_profile_verified\":true,\"cleanup\":true,\"execution\":\"native-user-space\",\"kernel_execution\":\"not_tested\",\"gpu_access\":false}\n", checks);
    return 0;
}
