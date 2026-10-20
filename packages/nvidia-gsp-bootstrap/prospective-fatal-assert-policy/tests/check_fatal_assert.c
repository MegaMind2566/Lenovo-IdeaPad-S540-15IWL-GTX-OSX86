/* SPDX-License-Identifier: MIT */
#include "nv.h"
#include "os-interface.h"
#include "utils/nvassert.h"
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <sys/wait.h>
#include <signal.h>
#include <string.h>

static unsigned checks, failures;
#define CHECK(x) do { ++checks; if (!(x)) ++failures; } while (0)

/* Actual selected macros and successor helpers reach the real host abort
 * implementation behind the original-header bug-check facade. */
static void trigger(unsigned which)
{
    switch (which) {
    case 0: NV_ASSERT_FAILED("literal %s %n"); break;
    case 1: NV_ASSERT_OK_FAILED("status invariant", 73); break;
    case 2: NV_ASSERT_FAILED_FUNC("function invariant"); break;
    case 3: NV_ASSERT_OK_FAILED_FUNC("function status", 91); break;
    case 4: NV_ASSERT_PRECOMP(0); break;
    case 5: NV_ASSERT_OR_RETURN(0, (void)0); break;
    case 6: nvAssertFailedNoLog(NV_ASSERT_FAILED_FUNC_PARAM(NULL)); break;
    case 7: nvAssertOkFailed(29 NV_ASSERT_FAILED_FUNC_COMMA_PARAM("direct status")); break;
    default: _exit(99);
    }
    _exit(98);
}

int main(void)
{
    NV_ASSERT(1);
    NV_ASSERT_PRECOMP(1);
    CHECK(1);
    for (unsigned which = 0; which < 8; ++which) {
        int status = 0;
        FILE *output = tmpfile();
        CHECK(output != NULL);
        if (!output) return 1;
        pid_t child = fork();
        CHECK(child >= 0);
        if (!child) {
            if (dup2(fileno(output), STDERR_FILENO) < 0) _exit(97);
            trigger(which);
        }
        CHECK(waitpid(child, &status, 0) == child);
        CHECK(WIFSIGNALED(status) && WTERMSIG(status) == SIGABRT);
        rewind(output);
        char text[1024] = {0};
        CHECK(fread(text, 1, sizeof(text)-1, output) > 0);
        CHECK(strstr(text, "S540 NVIDIA RM bug check") != NULL);
        if (which == 0) CHECK(strstr(text, "literal %s %n") != NULL);
        if (which == 1) CHECK(strstr(text, "bug check 73:") != NULL);
        if (which == 3) CHECK(strstr(text, "bug check 91:") != NULL);
        if (which == 6) CHECK(strstr(text, "RM assertion failed") != NULL);
        if (which == 7) CHECK(strstr(text, "bug check 29:") != NULL);
        fclose(output);
    }
    printf("{\"format\":1,\"status\":\"%s\",\"component\":\"fatal-rm-assert-policy\",\"checks\":%u,\"failures\":%u,\"fatal_cases\":8,\"execution\":\"native-user-space\",\"kernel_execution\":\"not_tested\",\"gpu_access\":false}\n", failures ? "failed" : "passed", checks, failures);
    return failures ? 1 : 0;
}
