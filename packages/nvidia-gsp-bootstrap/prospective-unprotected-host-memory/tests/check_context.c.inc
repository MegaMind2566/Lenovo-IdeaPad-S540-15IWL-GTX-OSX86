/* SPDX-License-Identifier: MIT; actual C bodies, explicit CPU-only endpoints. */
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "S540NvidiaGspContext.h"
#include "S540NvidiaGspFirstTransaction.h"
#include "nvidia-os-adapter/upstream/include/nv-kernel-interface-api.h"

/* Only the state fields touched by the extracted actual adapter boundary are
 * modeled here. This is not an nv_state_t/kernel-layout or RM execution test. */
struct FixtureNv { NvU32 flags; };
struct S540GspContext {
    struct FixtureNv nv;
    NvU32 stacks[1];
    NvU64 firstTxnGeneration;
    S540GspContextSnapshot state;
};
enum { MAIN = 0, NV_DBG_ERRORS = 4, NV_FLAG_INITIALIZED = 1U << 12 };
static S540GspContext context;
static S540FirstTxnSnapshot providedSnapshot;
static NV_STATUS snapshotResult, wrapperResult, enterResult, irqResult, preflightResult;
static NvBool ownerAllowed, hostClean, adapterResult;
static NvU32 checks, snapshotCalls, logCalls, wrapperCalls, enterCalls, adapterCalls;
static char logged[768];

static void expect(NvBool condition, const char *description)
{
    ++checks;
    if (!condition) {
        fprintf(stderr, "context diagnostic check failed: %s\n", description);
        exit(1);
    }
}
static NvBool owner(S540GspContext *value) { return value == &context && ownerAllowed; }
static NvBool cleanHost(void) { return hostClean; }
NV_STATUS s540GspIrqInstallationCheckContext(S540GspContext *value)
{
    expect(value == &context, "actual IRQ check context");
    return irqResult;
}
static NV_STATUS s540GlobalRmFeatureProfilePreflight(const void *value)
{
    expect(value == &context.nv, "actual preflight state identity");
    return preflightResult;
}
NV_STATUS s540FirstTxnOriginalEnter(const void *value)
{
    expect(value == &context.nv, "actual original-enter state identity");
    ++enterCalls;
    return enterResult;
}
static NvBool rm_init_adapter(void *stack, void *value)
{
    expect(stack == &context.stacks[MAIN] && value == &context.nv,
        "actual original adapter endpoint identities");
    expect(enterCalls == 1 && !wrapperCalls && !snapshotCalls && !logCalls,
        "adapter runs before wrapper-return and diagnostics");
    ++adapterCalls;
    return adapterResult;
}
NV_STATUS s540FirstTxnOriginalWrapperReturned(const void *value)
{
    expect(value == &context.nv && adapterCalls == 1 && !snapshotCalls && !logCalls,
        "diagnostic is after the original wrapper actually returned");
    ++wrapperCalls;
    return wrapperResult;
}
NV_STATUS s540FirstTxnGetSnapshot(const void *value, S540FirstTxnSnapshot *out)
{
    expect(value == &context.nv && out && wrapperCalls == 1 && wrapperResult != NV_OK,
        "diagnostic samples exact state only after a nonzero wrapper result");
    ++snapshotCalls;
    if (snapshotResult != NV_OK) return snapshotResult;
    *out = providedSnapshot;
    return NV_OK;
}
int NV_API_CALL nv_printf(NvU32 level, const char *format, ...)
    __attribute__((format(printf, 2, 3)));
int NV_API_CALL nv_printf(NvU32 level, const char *format, ...)
{
    va_list args;
    int count;
    expect(level == NV_DBG_ERRORS && wrapperCalls == 1 && snapshotCalls == 1,
        "one error logger endpoint after one snapshot attempt");
    expect(!logCalls, "one bounded diagnostic call");
    va_start(args, format);
    count = vsnprintf(logged, sizeof(logged), format, args);
    va_end(args);
    expect(count > 0 && (size_t)count < sizeof(logged), "bounded scalar diagnostic line");
    expect(logged[count - 1] == '\n' && strchr(logged, '\n') == &logged[count - 1],
        "exactly one complete log line");
    expect(!strstr(format, "%p") && !strstr(logged, "firmware=") &&
        !strstr(logged, "generation=") && !strstr(logged, "masterThread="),
        "no pointer, firmware or thread identity output");
    ++logCalls;
    return count;
}

#include "actual-context-failure.inc"
#include "actual-initialize-adapter.inc"

static void reset(void)
{
    memset(&context, 0, sizeof(context));
    memset(&providedSnapshot, 0, sizeof(providedSnapshot));
    memset(logged, 0, sizeof(logged));
    context.firstTxnGeneration = 19;
    context.state.privateState = NV_TRUE;
    snapshotResult = wrapperResult = enterResult = irqResult = preflightResult = NV_OK;
    ownerAllowed = hostClean = adapterResult = NV_TRUE;
    snapshotCalls = logCalls = wrapperCalls = enterCalls = adapterCalls = 0;
}
static void decimalField(const char *name, unsigned long long value)
{
    char expected[96];
    int count = snprintf(expected, sizeof(expected), " %s=%llu", name, value);
    const char *found = strstr(logged, expected);
    expect(count > 0 && (size_t)count < sizeof(expected) && found &&
        (found[count] == ' ' || found[count] == '\n'), name);
}
static void hexField(const char *name, unsigned long long value)
{
    char expected[96];
    int count = snprintf(expected, sizeof(expected), " %s=0x%llx", name, value);
    const char *found = strstr(logged, expected);
    expect(count > 0 && (size_t)count < sizeof(expected) && found &&
        (found[count] == ' ' || found[count] == '\n'), name);
}
static void available(NvU32 firstSite, NvU64 counter)
{
    S540FirstTxnSnapshot old;
    reset();
    adapterResult = NV_FALSE;
    wrapperResult = NV_ERR_NOT_SUPPORTED;
    providedSnapshot.firstStatus = NV_ERR_INVALID_STATE;
    providedSnapshot.firstSite = firstSite;
    providedSnapshot.phase = S540_FIRST_RETAINED;
    providedSnapshot.counters.hostUnavailable = counter;
    providedSnapshot.counters.hostInvalidFrees = counter - 1;
    providedSnapshot.counters.memoryUnavailableEver = counter - 2;
    providedSnapshot.counters.memoryViolationsEver = counter - 3;
    providedSnapshot.counters.cryptoUnavailable = counter - 4;
    providedSnapshot.counters.cryptoMaskLow = 0x8000000000000001ULL;
    providedSnapshot.counters.cryptoMaskHigh = 0x123456789abcdef0ULL;
    providedSnapshot.counters.cryptoOverflow = NV_TRUE;
    providedSnapshot.firmware[0] = &context;
    old = providedSnapshot;
    expect(s540GspContextInitializeAdapter(&context) == wrapperResult,
        "diagnostic preserves actual wrapper error");
    expect(context.state.quarantined && context.state.adapterAttempted &&
        !context.state.adapterInitialized && !context.nv.flags,
        "diagnostic preserves quarantine and initialized guards");
    expect(snapshotCalls == 1 && logCalls == 1 &&
        strstr(logged, "snapshot=available ") && !strstr(logged, "snapshotStatus="),
        "successful snapshot is explicitly available");
    decimalField("profile", wrapperResult);
    decimalField("firstStatus", providedSnapshot.firstStatus);
    decimalField("firstSite", firstSite);
    decimalField("phase", S540_FIRST_RETAINED);
    decimalField("hostUnavailable", counter);
    decimalField("invalidFrees", counter - 1);
    decimalField("memoryUnavailableEver", counter - 2);
    decimalField("violationsEver", counter - 3);
    decimalField("cryptoUnavailable", counter - 4);
    decimalField("cryptoOverflow", NV_TRUE);
    hexField("cryptoMaskLow", providedSnapshot.counters.cryptoMaskLow);
    hexField("cryptoMaskHigh", providedSnapshot.counters.cryptoMaskHigh);
    expect(!memcmp(&providedSnapshot, &old, sizeof(old)), "diagnostic does not mutate snapshot source");
}
static void unavailable(NV_STATUS unavailableStatus)
{
    reset();
    wrapperResult = NV_ERR_NOT_SUPPORTED;
    snapshotResult = unavailableStatus;
    expect(s540GspContextInitializeAdapter(&context) == wrapperResult,
        "missing snapshot preserves original wrapper error");
    expect(context.state.quarantined && snapshotCalls == 1 && logCalls == 1,
        "missing snapshot is still one diagnostic attempt");
    expect(strstr(logged, "snapshot=unavailable ") && !strstr(logged, "firstStatus=") &&
        !strstr(logged, "firstSite=") && !strstr(logged, "phase=") &&
        !strstr(logged, "hostUnavailable=") && !strstr(logged, "cryptoMask"),
        "unavailable snapshot never invents zero evidence");
    decimalField("profile", wrapperResult);
    decimalField("snapshotStatus", unavailableStatus);
}
int main(void)
{
    available(0x89abcdefU, ~(NvU64)0);
    available(617U, 47U);
    unavailable(NV_ERR_INVALID_STATE);
    unavailable(NV_ERR_OBJECT_NOT_FOUND);

    reset();
    expect(s540GspContextInitializeAdapter(&context) == NV_OK &&
        context.state.adapterInitialized && (context.nv.flags & NV_FLAG_INITIALIZED) &&
        !context.state.quarantined && !snapshotCalls && !logCalls,
        "successful wrapper has no error diagnostic");
    reset(); adapterResult = NV_FALSE;
    expect(s540GspContextInitializeAdapter(&context) == NV_ERR_NOT_READY &&
        context.state.quarantined && !snapshotCalls && !logCalls,
        "Boolean adapter failure with clean wrapper retains existing status path");
    reset(); ownerAllowed = NV_FALSE;
    expect(s540GspContextInitializeAdapter(&context) == NV_ERR_INVALID_STATE &&
        !adapterCalls && !snapshotCalls && !logCalls, "owner refusal does not sample unreturned original");
    reset(); enterResult = NV_ERR_TIMEOUT;
    expect(s540GspContextInitializeAdapter(&context) == NV_ERR_TIMEOUT &&
        context.state.quarantined && !adapterCalls && !snapshotCalls && !logCalls,
        "original-enter refusal keeps existing status and no diagnostics");
    reset(); irqResult = NV_ERR_NOT_SUPPORTED;
    expect(s540GspContextInitializeAdapter(&context) == NV_ERR_NOT_SUPPORTED &&
        !enterCalls && !adapterCalls && !snapshotCalls && !logCalls,
        "IRQ admission refusal is unchanged");
    reset(); preflightResult = NV_ERR_NOT_SUPPORTED;
    expect(s540GspContextInitializeAdapter(&context) == NV_ERR_NOT_SUPPORTED &&
        !enterCalls && !adapterCalls && !snapshotCalls && !logCalls,
        "feature admission refusal is unchanged");
    printf("{\"status\":\"passed\",\"checks\":%u,\"available_cases\":2,"
        "\"unavailable_cases\":2,\"nonlogging_cases\":6}\n", checks);
    return 0;
}
