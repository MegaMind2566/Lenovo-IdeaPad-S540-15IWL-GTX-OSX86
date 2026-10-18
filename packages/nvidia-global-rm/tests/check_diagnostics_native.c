/* SPDX-License-Identifier: MIT */
/* Compile under the pinned original declarations and private namespace. This
 * control observes real formatted output and the native fatal boundary; it
 * does not execute RM, touch PCI or load a kernel image.
 */
#include "nv.h"
#include "nv-dev-printf.h"
#include "os-interface.h"
/* libc is the harness's actual observation machinery, not an RM dependency. */
#undef memset
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <unistd.h>
#include <sys/wait.h>
#include <signal.h>

static int device_log(nv_state_t *state, NV_LOG_LEVEL level,
                      const char *format, ...)
{
    va_list arguments;
    int result;
    va_start(arguments, format);
    result = nv_dev_vprintf(state, level, format, arguments);
    va_end(arguments);
    return result;
}

static NV_STATUS error_log(nv_state_t *state, NvU32 error,
                           const char *format, ...)
{
    va_list arguments;
    NV_STATUS result;
    va_start(arguments, format);
    result = nv_log_error(state, error, format, arguments);
    va_end(arguments);
    return result;
}

int main(void)
{
    NvU32 checks = 0;
    nv_state_t state = {0};
    FILE *capture;
    int saved;
    long start;
    int count;
    char output[4096] = {0};
    char long_text[2048];
    int status = 0;
    pid_t child;
#define EXPECT(value) do { ++checks; if (!(value)) { \
    dprintf(STDOUT_FILENO, "Diagnostics check failed at line %d\n", __LINE__); \
    return 1; } } while (0)
    state.pci_info.domain = 0;
    state.pci_info.bus = 2;
    state.pci_info.slot = 0;
    state.pci_info.function = 1;
    capture = tmpfile();
    EXPECT(capture != NULL);
    saved = dup(STDERR_FILENO);
    EXPECT(saved >= 0 && dup2(fileno(capture), STDERR_FILENO) >= 0);

    EXPECT(device_log(NULL, NV_LOG_LEVEL_ERROR, "must not appear\n") == 0);
    EXPECT(device_log(&state, NV_LOG_LEVEL_INFO, NULL) == -1);
    EXPECT(error_log(NULL, 31, "must not appear\n") == NV_ERR_INVALID_ARGUMENT);
    EXPECT(error_log(&state, 31, NULL) == NV_ERR_INVALID_ARGUMENT);
    fflush(stderr);
    EXPECT(ftell(capture) == 0);

    count = device_log(&state, NV_LOG_LEVEL_WARNING, "actual %d %s %%\n", 17, "text");
    fflush(stderr);
    EXPECT(fseek(capture, 0, SEEK_END) == 0);
    EXPECT(count == ftell(capture));
    EXPECT(count > 0);
    rewind(capture);
    EXPECT(fread(output, 1, sizeof(output) - 1, capture) == (size_t)count);
    EXPECT(strcmp(output, "S540 NVIDIA 0000:02:00.1 warning: actual 17 text %\n") == 0);
    EXPECT(fseek(capture, 0, SEEK_END) == 0);
    start = ftell(capture);
    EXPECT(error_log(&state, 79, "fault %08x\n", 0x1234) == NV_OK);
    fflush(stderr);
    EXPECT(fseek(capture, start, SEEK_SET) == 0);
    memset(output, 0, sizeof(output));
    EXPECT(fread(output, 1, sizeof(output) - 1, capture) > 0);
    EXPECT(strcmp(output, "S540 NVIDIA 0000:02:00.1 error Xid 79: fault 00001234\n") == 0);

    EXPECT(fseek(capture, 0, SEEK_END) == 0);
    start = ftell(capture);
    count = device_log(&state, (NV_LOG_LEVEL)99, "unknown-level\n");
    fflush(stderr);
    EXPECT(fseek(capture, 0, SEEK_END) == 0);
    EXPECT(count > 0 && ftell(capture) - start == count);
    EXPECT(fseek(capture, start, SEEK_SET) == 0);
    memset(output, 0, sizeof(output));
    EXPECT(fread(output, 1, sizeof(output) - 1, capture) > 0);
    EXPECT(strcmp(output, "S540 NVIDIA 0000:02:00.1 info: unknown-level\n") == 0);

    EXPECT(fseek(capture, 0, SEEK_END) == 0);
    start = ftell(capture);
    memset(long_text, 'x', sizeof(long_text) - 1);
    long_text[sizeof(long_text) - 1] = '\0';
    count = device_log(&state, NV_LOG_LEVEL_DEBUG, "%s", long_text);
    fflush(stderr);
    EXPECT(fseek(capture, 0, SEEK_END) == 0);
    EXPECT(count == 1023 && ftell(capture) - start == 1023);

    start = ftell(capture);
    child = fork();
    EXPECT(child >= 0);
    if (child == 0) os_bug_check(42, "literal %s %n");
    EXPECT(waitpid(child, &status, 0) == child);
    EXPECT(WIFSIGNALED(status) && WTERMSIG(status) == SIGABRT);
    EXPECT(fseek(capture, start, SEEK_SET) == 0);
    memset(output, 0, sizeof(output));
    EXPECT(fread(output, 1, sizeof(output) - 1, capture) > 0);
    EXPECT(strstr(output, "S540 NVIDIA RM bug check 42: literal %s %n\n") != NULL);

    EXPECT(fseek(capture, 0, SEEK_END) == 0);
    child = fork();
    EXPECT(child >= 0);
    if (child == 0) os_bug_check(0, NULL);
    EXPECT(waitpid(child, &status, 0) == child);
    EXPECT(WIFSIGNALED(status) && WTERMSIG(status) == SIGABRT);

    EXPECT(dup2(saved, STDERR_FILENO) >= 0);
    close(saved);
    fclose(capture);
    printf("{\"format\":1,\"component\":\"nvidia-global-diagnostics\","
           "\"status\":\"passed\",\"checks\":%u,\"failures\":0,"
           "\"actual_log_bytes_observed\":true,\"fatal_bug_checks\":2,"
           "\"execution\":\"native-user-space\","
           "\"kernel_execution\":\"not_tested\",\"gpu_access\":false}\n", checks);
    return 0;
#undef EXPECT
}
