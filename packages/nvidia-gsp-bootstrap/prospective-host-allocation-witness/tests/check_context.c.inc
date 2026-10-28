/* SPDX-License-Identifier: MIT; actual inserted post-wrapper C logger. */
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include "S540HostAllocationDiagnostics.h"
enum { NV_DBG_ERRORS = 1 };
typedef struct S540GspContext { unsigned nv; } S540GspContext;
static S540GspContext context;
static S540HostAllocationDiagnostics sample;
static NV_STATUS wantedStatus;
static unsigned checks, failures, calls, reads;
static char logBuffer[4096];
#define EXPECT(v) do { ++checks; if (!(v)) { ++failures; fprintf(stderr, "Context control line %d\n", __LINE__); } } while (0)
NV_STATUS s540GlobalRmReadAllocationDiagnostics(const void *nv,
    S540HostAllocationDiagnostics *out) {
    EXPECT(nv == &context.nv); ++reads;
    if (wantedStatus != NV_OK) return wantedStatus;
    *out = sample; return NV_OK;
}
static int nv_printf(unsigned level, const char *format, ...) {
    EXPECT(level == NV_DBG_ERRORS); ++calls;
    va_list args; va_start(args, format);
    int result = vsnprintf(logBuffer + strlen(logBuffer),
        sizeof(logBuffer) - strlen(logBuffer), format, args);
    va_end(args); return result;
}
#include "actual-context.inc"
static void clearLog(void) { calls = reads = 0; logBuffer[0] = 0; }
int main(void) {
    sample.format = 1; sample.bytes = sizeof(sample); sample.observedMask = 15;
    sample.producerCallsLifetime = 37; sample.producerMask = 0x1ff;
    sample.producerFirstState = 2; sample.producerFirstId = 5; sample.producerFirstService = 38;
    for (unsigned i = 0; i < 9; ++i) sample.producerCalls[i] = 100 + i;
    sample.allocationFailuresLifetime = 7; sample.allocationStagesMask = 0x10;
    sample.allocationFirstState = 2; sample.allocationFirstStage = 5;
    sample.allocationFirstStatus = 86; sample.allocationFirstBytes = 1234567890123ULL;
    sample.allocationFirstOriginal = 1;
    s540LogHostAllocationWitness(&context);
    EXPECT(calls == 2 && reads == 1);
    EXPECT(strstr(logBuffer, "scope=producer-subset-module-lifetime independentlySampled=1 firstPublisherOnly=1"));
    EXPECT(strstr(logBuffer, "observedMask=0xf total=37 producerMask=0x1ff firstState=2 firstObserved=1 firstProducer=5 firstService=38"));
    EXPECT(strstr(logBuffer, "unknown=100 osAllocContext=101 acpiD3cold=102 acpiDdc=103 acpiDod=104 acpiDsm=105 acpiPowerSource=106 acpiMux=107 acpiInitNull=108"));
    EXPECT(strstr(logBuffer, "scope=module-lifetime independentlySampled=1 firstPublisherOnly=1 failures=7 stageMask=0x10 firstState=2 firstObserved=1 firstStage=5 firstStatus=86 firstBytes=1234567890123 firstOriginal=1"));
    clearLog(); sample.observedMask = 3; sample.producerFirstState = sample.allocationFirstState = 1;
    s540LogHostAllocationWitness(&context);
    EXPECT(calls == 2 && reads == 1);
    EXPECT(strstr(logBuffer, "firstState=1 firstObserved=0 firstProducer=0 firstService=0"));
    EXPECT(strstr(logBuffer, "firstState=1 firstObserved=0 firstStage=0 firstStatus=0 firstBytes=0 firstOriginal=0"));
    clearLog(); sample.producerFirstState = sample.allocationFirstState = 0;
    s540LogHostAllocationWitness(&context);
    EXPECT(calls == 2 && reads == 1);
    EXPECT(strstr(logBuffer, "firstState=0 firstObserved=0 firstProducer=0 firstService=0"));
    EXPECT(strstr(logBuffer, "firstState=0 firstObserved=0 firstStage=0 firstStatus=0 firstBytes=0 firstOriginal=0"));
    clearLog(); wantedStatus = NV_ERR_NOT_READY;
    s540LogHostAllocationWitness(&context);
    EXPECT(calls == 1 && reads == 1 && strstr(logBuffer, "available=0 status="));
    EXPECT(!strstr(logBuffer, "S540 refusal producers:") && !strstr(logBuffer, "firstBytes="));
    printf("{\"cases\":4,\"checks\":%u,\"failures\":%u}\n", checks, failures);
    return failures ? 1 : 0;
}
