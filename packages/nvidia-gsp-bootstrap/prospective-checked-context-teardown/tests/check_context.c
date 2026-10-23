/* SPDX-License-Identifier: MIT
 * CPU fixtures for endpoints; the complete selected production Context entry
 * bodies are included below. This does not claim original-layout/SDK or GPU
 * execution: those are separate full-translation-unit checks. */
#include "S540NvidiaGspContext.h"
#include <stdio.h>
#include <string.h>
typedef struct { NvU32 flags; } nv_state_t;
typedef struct { NvU32 unused; } nvidia_stack_t;
enum { MAIN = 0, NV_FLAG_INITIALIZED = 1 };
struct S540GspContext {
    nv_state_t nv;
    nvidia_stack_t stacks[1];
    S540GspContextSnapshot state;
};
static S540GspContext context;
static NvBool ownerValid, clean;
static NV_STATUS disableStatus, shutdownStatus;
static NvU32 disableCalls, shutdownCalls, legacyCalls, checks, failures;
static void expect(NvBool value, const char *message) {
    ++checks;
    if (!value) { ++failures; fprintf(stderr, "Context: %s\n", message); }
}
static NvBool owner(S540GspContext *value) { return value == &context && ownerValid; }
static NvBool cleanHost(void) { return clean; }
NV_STATUS s540RmDisableAdapterChecked(nvidia_stack_t *sp, nv_state_t *nv) {
    expect(sp == &context.stacks[MAIN] && nv == &context.nv, "exact disable original arguments");
    ++disableCalls; return disableStatus;
}
NV_STATUS s540RmShutdownAdapterChecked(nvidia_stack_t *sp, nv_state_t *nv) {
    expect(sp == &context.stacks[MAIN] && nv == &context.nv, "exact shutdown original arguments");
    ++shutdownCalls; return shutdownStatus;
}
void rm_disable_adapter(nvidia_stack_t *sp, nv_state_t *nv) { (void)sp; (void)nv; ++legacyCalls; }
void rm_shutdown_adapter(nvidia_stack_t *sp, nv_state_t *nv) { (void)sp; (void)nv; ++legacyCalls; }
#include "actual-context-bodies.inc"
static void reset(void) {
    memset(&context, 0, sizeof(context)); ownerValid = clean = NV_TRUE;
    disableStatus = shutdownStatus = NV_OK; disableCalls = shutdownCalls = legacyCalls = 0;
    context.state.adapterInitialized = NV_TRUE; context.nv.flags = NV_FLAG_INITIALIZED | 0x80U;
}
int main(void) {
    NV_STATUS errors[] = { NV_ERR_TIMEOUT, NV_ERR_OPERATION_ABORTED, NV_ERR_INVALID_LOCK_STATE };
    reset(); expect(s540GspContextDisableAdapter(NULL) == NV_ERR_INVALID_STATE, "null disable refused");
    expect(!disableCalls, "null disable has no endpoint");
    reset(); ownerValid = NV_FALSE;
    expect(s540GspContextDisableAdapter(&context) == NV_ERR_INVALID_STATE, "foreign disable refused");
    expect(!disableCalls, "foreign disable has no endpoint");
    reset(); context.state.adapterInitialized = NV_FALSE;
    expect(s540GspContextDisableAdapter(&context) == NV_ERR_INVALID_STATE, "uninitialized disable refused");
    expect(!disableCalls, "uninitialized disable has no endpoint");
    reset(); context.state.adapterDisabled = NV_TRUE;
    expect(s540GspContextDisableAdapter(&context) == NV_ERR_INVALID_STATE, "repeat disable refused");
    expect(!disableCalls, "repeat disable has no endpoint");
    for (NvU32 i = 0; i < sizeof(errors) / sizeof(errors[0]); ++i) {
        reset(); disableStatus = errors[i];
        expect(s540GspContextDisableAdapter(&context) == errors[i], "exact disable error propagated");
        expect(context.state.quarantined && !context.state.adapterDisabled &&
            context.nv.flags == (NV_FLAG_INITIALIZED | 0x80U), "failed disable retains flags and quarantines");
        expect(disableCalls == 1 && !legacyCalls, "checked disable endpoint only");
    }
    reset(); clean = NV_FALSE;
    expect(s540GspContextDisableAdapter(&context) == NV_ERR_INVALID_STATE, "dirty host disable refused");
    expect(context.state.quarantined && !context.state.adapterDisabled, "dirty disable retains state");
    reset(); expect(s540GspContextDisableAdapter(&context) == NV_OK, "checked disable succeeds");
    expect(context.state.adapterDisabled && !context.state.quarantined && disableCalls == 1 && !legacyCalls,
        "successful disable publishes actual completion");
    reset(); expect(s540GspContextShutdownAdapter(NULL, NV_TRUE) == NV_ERR_INVALID_STATE, "null shutdown refused");
    expect(!shutdownCalls, "null shutdown has no endpoint");
    reset(); context.state.adapterDisabled = NV_TRUE; ownerValid = NV_FALSE;
    expect(s540GspContextShutdownAdapter(&context, NV_TRUE) == NV_ERR_INVALID_STATE, "foreign shutdown refused");
    expect(!shutdownCalls, "foreign shutdown has no endpoint");
    reset(); context.state.adapterDisabled = NV_TRUE;
    expect(s540GspContextShutdownAdapter(&context, NV_FALSE) == NV_ERR_INVALID_STATE, "live IRQ shutdown refused");
    expect(!shutdownCalls, "live IRQ has no shutdown endpoint");
    reset(); expect(s540GspContextShutdownAdapter(&context, NV_TRUE) == NV_ERR_INVALID_STATE, "shutdown before disable refused");
    expect(!shutdownCalls, "undisabled has no shutdown endpoint");
    reset(); context.state.adapterDisabled = context.state.adapterShutdown = NV_TRUE;
    expect(s540GspContextShutdownAdapter(&context, NV_TRUE) == NV_ERR_INVALID_STATE, "repeat shutdown refused");
    expect(!shutdownCalls, "repeat shutdown has no endpoint");
    for (NvU32 i = 0; i < sizeof(errors) / sizeof(errors[0]); ++i) {
        reset(); context.state.adapterDisabled = NV_TRUE; shutdownStatus = errors[i];
        expect(s540GspContextShutdownAdapter(&context, NV_TRUE) == errors[i], "exact shutdown error propagated");
        expect(context.state.quarantined && !context.state.adapterShutdown &&
            context.nv.flags == (NV_FLAG_INITIALIZED | 0x80U), "failed shutdown retains initialized flag");
        expect(shutdownCalls == 1 && !legacyCalls, "checked shutdown endpoint only");
    }
    reset(); context.state.adapterDisabled = NV_TRUE; clean = NV_FALSE;
    expect(s540GspContextShutdownAdapter(&context, NV_TRUE) == NV_ERR_INVALID_STATE, "dirty host shutdown refused");
    expect(context.state.quarantined && !context.state.adapterShutdown &&
        context.nv.flags == (NV_FLAG_INITIALIZED | 0x80U), "dirty shutdown retains initialized flag");
    reset(); context.state.adapterDisabled = NV_TRUE;
    expect(s540GspContextShutdownAdapter(&context, NV_TRUE) == NV_OK, "checked shutdown succeeds");
    expect(context.state.adapterShutdown && !context.state.quarantined &&
        context.nv.flags == 0x80U && shutdownCalls == 1 && !legacyCalls, "actual shutdown clears only initialized bit");
    printf("{\"checks\":%u,\"failures\":%u}\n", checks, failures);
    return failures ? 1 : 0;
}
