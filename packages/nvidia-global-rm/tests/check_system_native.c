/* SPDX-License-Identifier: MIT */
#include "nv.h"
#include "os-interface.h"
#include "../src/S540NvidiaGlobalRmSystem.h"
#undef memset
#include <stdio.h>
#include <string.h>
#include <unistd.h>

int main(void)
{
    NvU32 checks = 0, frames = 0, lines = 0;
    FILE *capture;
    int saved;
    char output[8192] = {0};
    char *line;
#define EXPECT(value) do { ++checks; if (!(value)) { \
    dprintf(STDOUT_FILENO, "System service check failed at line %d\n", __LINE__); \
    return 1; } } while (0)
    /* Compare the original-header facade with the actual selected platform
     * backend, including repeated query and real diagnostic output.
     */
    EXPECT(os_get_max_user_va() == s540GlobalRmSystemUserAddressLimit());
    EXPECT(os_get_max_user_va() == S540_DARWIN_X86_64_USER_MAP_LIMIT);
    EXPECT(os_get_max_user_va() > 0xFFFFFFFFULL);
    EXPECT((os_get_max_user_va() & 4095ULL) == 0);
    EXPECT(os_get_reclaimable_memory_usage() == 0);
    EXPECT(S540_DARWIN_NVIDIA_RECYCLING_PAGE_POOLS == 0);

    capture = tmpfile();
    EXPECT(capture != NULL);
    saved = dup(STDERR_FILENO);
    EXPECT(saved >= 0);
    EXPECT(dup2(fileno(capture), STDERR_FILENO) >= 0);
    os_dump_stack();
    fflush(stderr);
    EXPECT(fseek(capture, 0, SEEK_SET) == 0);
    EXPECT(fread(output, 1, sizeof(output) - 1, capture) > 0);
    EXPECT(sscanf(output, "S540 NVIDIA RM stack trace (%u frames):", &frames) == 1);
    EXPECT(frames > 0 && frames <= S540_GLOBAL_RM_STACK_TRACE_FRAMES);
    for (line = strstr(output, "S540 NVIDIA RM frame "); line;
         line = strstr(line + 1, "S540 NVIDIA RM frame ")) ++lines;
    EXPECT(lines == frames);
    EXPECT(strstr(output, "frame 0: 0x") != NULL);
    EXPECT(dup2(saved, STDERR_FILENO) >= 0);
    close(saved);
    fclose(capture);
    EXPECT(os_get_reclaimable_memory_usage() == 0);
    EXPECT(os_get_max_user_va() == S540_DARWIN_X86_64_USER_MAP_LIMIT);
    printf("{\"format\":1,\"component\":\"nvidia-global-system\","
           "\"status\":\"passed\",\"checks\":%u,\"failures\":0,"
           "\"real_native_stack_frames\":%u,\"darwin_source_profile_user_map_limit\":%llu,"
           "\"target_kernel_admission\":false,\"nvidia_recycling_pool_bytes\":0,"
           "\"execution\":\"native-user-space\",\"kernel_execution\":\"not_tested\","
           "\"gpu_access\":false}\n",
           checks, frames, (unsigned long long)S540_DARWIN_X86_64_USER_MAP_LIMIT);
    return 0;
}
