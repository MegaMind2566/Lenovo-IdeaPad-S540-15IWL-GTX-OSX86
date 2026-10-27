/* SPDX-License-Identifier: MIT; actual C bodies with explicit CPU endpoints. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#include "S540NvidiaGspFirstTransaction.h"
#include "S540OptionalNvlinkAbsence.h"
#include "S540AttachFailureWitness.h"

static unsigned checks;
static const char *caseName;
static void expectAt(int good, const char *expression, unsigned line)
{
    ++checks;
    if (!good) { fprintf(stderr, "case=%s line=%u failed=%s\n", caseName, line, expression); exit(2); }
}
#define EXPECT(c) expectAt(!!(c), #c, __LINE__)
#define LD(p) __atomic_load_n((p), __ATOMIC_ACQUIRE)
#define ST(p,v) __atomic_store_n((p),(v), __ATOMIC_RELEASE)
typedef struct { unsigned nv; } S540GspContext;
static S540GspContext contextFixture;
#define nvIdentity (contextFixture.nv)
static unsigned foreignNv, ownerIdentity, foreignOwner;
static NvU64 actualThread = 71;
static NvBool maySleep = NV_TRUE;
static NV_STATUS threadStatus = NV_OK;
static unsigned cancellationChecks, refuseAtCheck, changeGenerationAtCheck;
static unsigned cancellationWordReads;
static NvBool corruptCancelFormat, corruptCancelBound, corruptCancelGeneration, cancellationWordRace;
NvBool s540Darwin_os_semaphore_may_sleep(void) { return maySleep; }
NV_STATUS s540Darwin_os_get_current_thread(NvU64 *out)
{ if (threadStatus == NV_OK) *out = actualThread; return threadStatus; }

/* These declarations and functions are copied from the real transformed
 * record, never from a caller-provided readiness or diagnostic snapshot. */
@RECORD_STORAGE@
@CANCELLATION_STORAGE@
@CANCELLATION_WORD@
static NvU64 word(void)
{
    ++cancellationWordReads;
    if (cancellationWordRace && cancellationWordReads % 2U == 0) slot.control |= REVOKED;
    return actualCancellationWord();
}
@CANCELLATION_HELPERS@
@CANCELLATION_SNAPSHOT@
NV_STATUS s540GspCancellationGetSnapshot(S540GspCancellationToken token, S540GspCancellationSnapshot *out)
{
    ++cancellationChecks;
    if (changeGenerationAtCheck == cancellationChecks) { ++record.generation; ++globalEpoch.generation; }
    if (refuseAtCheck == cancellationChecks) slot.control |= REVOKED;
    NV_STATUS status = actualCancellationSnapshot(token, out);
    if (status == NV_OK) {
        if (corruptCancelFormat) out->format = 0;
        if (corruptCancelBound) out->bound = NV_FALSE;
        if (corruptCancelGeneration) ++out->generation;
    }
    return status;
}
@RECORD_HELPERS@
@RECORD_PROBES@

typedef NvU32 NVOC_CLASS_ID;
typedef NvU64 ENGDESCRIPTOR;
typedef struct StubEngine StubEngine;
struct StubEngine { NvBool (*getProperty)(StubEngine *, NvU32); };
typedef StubEngine Dynamic;
typedef StubEngine OBJENGSTATE;
typedef struct { unsigned marker; } NVOC_CLASS_INFO;
typedef struct { unsigned marker; } ENGSTATE_TRANSITION_DATA;
typedef struct { void *pOsGpuInfo; NvBool isGspClient; } OBJGPU;
typedef unsigned nv_state_t;
@REGISTRY_NV_MACRO@
#define classId(name) __nvoc_class_id_##name
@CLASS_MACRO@
#define IS_GSP_CLIENT(gpu) ((gpu)->isGspClient)
#define PDB_PROP_ENGSTATE_IS_MISSING 3U
#define ENGSTATE_STATE_CONSTRUCT 5U
#define LEVEL_INFO 1U
#define MKENGDESC(id, instance) (((NvU64)(id) << 32) ^ (instance))
#define NV_ASSERT_OR_RETURN(c, s) do { if (!(c)) return (s); } while (0)
#define NV_ASSERT_OK_OR_RETURN(expr) do { NV_STATUS result_ = (expr); if (result_ != NV_OK) return result_; } while (0)
#define NV_ASSERT_TRUE_OR_GOTO(s,c,e,label) do { if (!(c)) { (s)=(e); goto label; } } while (0)
#define NV_CHECK_OR_GOTO(l,c,label) do { (void)(l); if (!(c)) goto label; } while (0)
#define dynamicCast(object, type) ((type *)fakeEngstateCast(object))
#ifndef RMCFG_FEATURE_PLATFORM_WINDOWS
#define RMCFG_FEATURE_PLATFORM_WINDOWS 0
#endif
#define INCLUDE_NVLINK_LIB 1

/* Exact original getter body, with a CPU model for its real library context. */
static struct { struct { NvU8 initialized; } nv_devicelist_head; } nvlinkLibCtx;
@BACKEND_GETTER@

static OBJGPU gpu = { &nvIdentity, NV_TRUE };
static StubEngine concrete, previousChild;
static NVOC_CLASS_INFO classInfo;
static Dynamic *child;
static NVOC_CLASS_ID selectedClass = 0xce6818U;
static NvU64 selectedInstance;
static NvBool shouldCreate = NV_TRUE, missingProperty;
static NV_STATUS classStatus = NV_OK, dynamicStatus = NV_OK,
    baseStatus = NV_OK, engineStatus = NV_OK, registryStatus = NV_OK;
static NvU32 registryValue = 1U;
static NvBool registryMakesSticky, registryRevokesScope;
static unsigned registryCalls, classCalls, dynamicCalls, baseCalls, engineCalls,
    deferredCalls, deleteCalls, progressCalls, failureCalls;
static void sticky(NV_STATUS status)
{
    if (status != NV_OK && !first()) {
        record.control = ((NvU64)2U << 32) | (NvU32)status;
        record.phase = S540_FIRST_RETAINED;
    }
}
static NV_STATUS RmReadRegistryDword(nv_state_t *object, const char *name, NvU32 *out)
{
    EXPECT(object == NULL); EXPECT(name && strcmp(name, "NvLinkDisable") == 0); EXPECT(out != NULL);
    ++registryCalls;
    if (registryStatus == NV_OK) *out = registryValue;
    if (registryMakesSticky) sticky(NV_ERR_NOT_SUPPORTED);
    if (registryRevokesScope) slot.control |= REVOKED;
    return registryStatus;
}
@REGISTRY_BASE@
static NvBool getMissing(StubEngine *engine, NvU32 property)
{ EXPECT(engine == &concrete && property == PDB_PROP_ENGSTATE_IS_MISSING); return missingProperty; }
static NvBool gpuShouldCreateObject(OBJGPU *object, NVOC_CLASS_ID id, NvU64 instance)
{ EXPECT(object == &gpu && id == selectedClass && instance == selectedInstance); return shouldCreate; }
static NV_STATUS _gpuChildNvocClassInfoGet(OBJGPU *object, NVOC_CLASS_ID id, const NVOC_CLASS_INFO **out)
{ EXPECT(object == &gpu && id == selectedClass && out); ++classCalls; if (classStatus == NV_OK) *out = &classInfo; return classStatus; }
static NV_STATUS objCreateDynamic(Dynamic **out, OBJGPU *object, const NVOC_CLASS_INFO *info)
{ EXPECT(object == &gpu && info == &classInfo && out); ++dynamicCalls; if (dynamicStatus == NV_OK) *out = &concrete; return dynamicStatus; }
static Dynamic *objDynamicCastById(Dynamic *object, NVOC_CLASS_ID id)
{ EXPECT(object == &concrete && id == selectedClass); return object; }
static void *fakeEngstateCast(Dynamic *object) { EXPECT(object == &concrete); return object; }
static NV_STATUS engstateConstructBase(OBJENGSTATE *engine, OBJGPU *object, ENGDESCRIPTOR desc)
{ EXPECT(engine == &concrete && object == &gpu && desc == MKENGDESC(selectedClass, selectedInstance)); ++baseCalls; return baseStatus; }
static void engstateLogStateTransitionPre(OBJENGSTATE *engine, NvU32 state, ENGSTATE_TRANSITION_DATA *data)
{ EXPECT(engine == &concrete && state == ENGSTATE_STATE_CONSTRUCT && data); }
static void engstateLogStateTransitionPost(OBJENGSTATE *engine, NvU32 state, ENGSTATE_TRANSITION_DATA *data)
{ EXPECT(engine == &concrete && state == ENGSTATE_STATE_CONSTRUCT && data); }
static NV_STATUS engstateConstructEngine(OBJGPU *object, OBJENGSTATE *engine, ENGDESCRIPTOR desc)
{ EXPECT(object == &gpu && engine == &concrete && desc == MKENGDESC(selectedClass, selectedInstance)); ++engineCalls; return engineStatus; }
static NV_STATUS s540FirstTxnRequestDeferredCleanupGpu(OBJGPU *object, NV_STATUS status)
{ EXPECT(object == &gpu && status != NV_OK); ++deferredCalls; record.cleanupRequested = 1U; sticky(status); return status; }
void s540AttachWitnessChildProgress(const void *nv, NvU32 id, NvU64 instance, NvU32 stage)
{ (void)nv; EXPECT(id == selectedClass && instance == selectedInstance && stage); ++progressCalls; }
void s540AttachWitnessChildFailure(const void *nv, NvU32 id, NvU64 instance, NvU32 stage,
    NV_STATUS status, NvU32 mask, NvU32 missing, NvU32 gspClient)
{ (void)nv; (void)mask; (void)missing; (void)gspClient; EXPECT(id == selectedClass && instance == selectedInstance && stage && status != NV_OK); ++failureCalls; }
#define objDelete(p) do { (void)(p); ++deleteCalls; } while (0)

@GPU_HELPER@
@GPU_BODY@

static char logged[1024];
static unsigned logCalls;
#define NV_DBG_ERRORS 3U
static void nv_printf(NvU32 level, const char *format, ...)
{
    EXPECT(level == NV_DBG_ERRORS); EXPECT(format != NULL); ++logCalls;
    va_list args; va_start(args, format); vsnprintf(logged, sizeof(logged), format, args); va_end(args);
}
@CONTEXT_LOGGER@

static void setup(void)
{
    memset(&record, 0, sizeof(record)); memset(&globalEpoch, 0, sizeof(globalEpoch));
    record.owner = &ownerIdentity; record.nv = &nvIdentity;
    record.generation = 0x1234567800000007ULL; record.masterThread = actualThread;
    record.phase = S540_FIRST_OP; record.originalInFlight = 1U;
    globalEpoch.owner = record.owner; globalEpoch.generation = record.generation;
    globalEpoch.thread = actualThread; globalEpoch.state = S540_FIRST_GLOBAL_READY;
    globalEpoch.validated = globalEpoch.originalReturned = 1U;
    record.cancelToken = 13U;
    slot.control = (record.cancelToken << SHIFT) | BOUND | OPERATION;
    slot.generation = record.cancelToken; slot.ownerThread = actualThread; slot.state = &nvIdentity;
    slot.checks = 31U; slot.operationAborts = 7U; slot.cleanupExpirations = 5U;
    concrete.getProperty = getMissing;
}
static void wrapperReturned(void)
{ record.originalExitReady = record.originalReturned = 1U; record.originalInFlight = 0; }
static NV_STATUS callGpu(void) { return gpuCreateObject(&gpu, selectedClass, selectedInstance, &child); }
static void noConstruction(void)
{ EXPECT(classCalls == 0 && dynamicCalls == 0 && baseCalls == 0 && engineCalls == 0 && deleteCalls == 0 && deferredCalls == 0); }
static void readRefused(const void *nv)
{
    S540OptionalNvlinkAbsence out, before;
    memset(&out, 0xa5, sizeof(out)); before = out;
    EXPECT(s540OptionalNvlinkRead(nv, &out) != NV_OK);
    EXPECT(memcmp(&before, &out, sizeof(out)) == 0);
}
static void readGood(void)
{
    S540OptionalNvlinkAbsence out;
    memset(&out, 0xa5, sizeof(out));
    EXPECT(s540OptionalNvlinkRead(&nvIdentity, &out) == NV_OK);
    EXPECT(out.format == 1U && out.bytes == sizeof(out) && sizeof(out) == 32U);
    EXPECT(out.generation == record.generation && out.absent == 1U);
    EXPECT(out.classId == 0xce6818U && out.instance == 0);
}
static void activeRefused(const void *nv)
{
    NvU64 generation = ~0ULL;
    unsigned char savedRecord[sizeof(record)], savedGlobal[sizeof(globalEpoch)];
    NvU32 savedChecks = slot.checks, savedAborts = slot.operationAborts, savedExpirations = slot.cleanupExpirations;
    memcpy(savedRecord, &record, sizeof(record)); memcpy(savedGlobal, &globalEpoch, sizeof(globalEpoch));
    EXPECT(s540FirstTxnOptionalNvlinkActive(nv, &generation) != NV_OK);
    EXPECT(generation == 0);
    EXPECT(memcmp(savedRecord, &record, sizeof(record)) == 0);
    EXPECT(memcmp(savedGlobal, &globalEpoch, sizeof(globalEpoch)) == 0);
    EXPECT(slot.checks == savedChecks && slot.operationAborts == savedAborts && slot.cleanupExpirations == savedExpirations);
}
static void invalidate(const char *name)
{
    if (!strcmp(name, "foreign_nv")) gpu.pOsGpuInfo = &foreignNv;
    else if (!strcmp(name, "null_nv")) gpu.pOsGpuInfo = NULL;
    else if (!strcmp(name, "foreign_master")) ++actualThread;
    else if (!strcmp(name, "irq")) maySleep = NV_FALSE;
    else if (!strcmp(name, "thread_error")) threadStatus = NV_ERR_NOT_SUPPORTED;
    else if (!strcmp(name, "thread_zero")) actualThread = 0;
    else if (!strcmp(name, "unbound")) record.generation = 0;
    else if (!strcmp(name, "owner_missing")) record.owner = NULL;
    else if (!strcmp(name, "owner_mismatch")) globalEpoch.owner = &foreignOwner;
    else if (!strcmp(name, "generation_mismatch")) ++globalEpoch.generation;
    else if (!strcmp(name, "master_mismatch")) ++globalEpoch.thread;
    else if (!strcmp(name, "sticky")) record.control = NV_ERR_NOT_SUPPORTED;
    else if (!strcmp(name, "phase")) record.phase = S540_FIRST_RETAINED;
    else if (!strcmp(name, "not_inflight")) record.originalInFlight = 0;
    else if (!strcmp(name, "exit_ready")) record.originalExitReady = 1U;
    else if (!strcmp(name, "already_returned")) record.originalReturned = 1U;
    else if (!strcmp(name, "global_state")) globalEpoch.state = S540_FIRST_GLOBAL_RETAINED;
    else if (!strcmp(name, "global_unvalidated")) globalEpoch.validated = 0;
    else if (!strcmp(name, "global_not_returned")) globalEpoch.originalReturned = 0;
    else if (!strcmp(name, "global_status")) globalEpoch.originalStatus = NV_ERR_NOT_SUPPORTED;
    else if (!strcmp(name, "global_validation")) globalEpoch.validationStatus = NV_ERR_NOT_SUPPORTED;
    else if (!strcmp(name, "cancel_scope") || !strcmp(name, "cancel_idle")) slot.control = (record.cancelToken << SHIFT) | BOUND;
    else if (!strcmp(name, "cancel_status") || !strcmp(name, "cancel_token")) record.cancelToken = 0;
    else if (!strcmp(name, "cancel_unbound")) slot.control &= ~(NvU64)BOUND;
    else if (!strcmp(name, "cancel_owner")) ++slot.ownerThread;
    else if (!strcmp(name, "cancel_cleanup")) slot.control = (record.cancelToken << SHIFT) | BOUND | CLEANUP;
    else if (!strcmp(name, "cancel_revoked")) slot.control |= REVOKED;
    else if (!strcmp(name, "cancel_publication")) slot.control |= PUBLISHING;
    else if (!strcmp(name, "cancel_generation")) slot.control += 1ULL << SHIFT;
    else if (!strcmp(name, "cancel_format")) corruptCancelFormat = NV_TRUE;
    else if (!strcmp(name, "cancel_bound")) corruptCancelBound = NV_TRUE;
    else if (!strcmp(name, "cancel_output_generation")) corruptCancelGeneration = NV_TRUE;
    else if (!strcmp(name, "cancel_race")) cancellationWordRace = NV_TRUE;
    else EXPECT(0);
}
int main(int argc, char **argv)
{
    EXPECT(argc == 2); caseName = argv[1]; setup();
    if (!strcmp(caseName, "active")) {
        unsigned char savedRecord[sizeof(record)], savedGlobal[sizeof(globalEpoch)], savedCancel[sizeof(slot)];
        NvU64 observed = 0;
        memcpy(savedRecord, &record, sizeof(record)); memcpy(savedGlobal, &globalEpoch, sizeof(globalEpoch));
        memcpy(savedCancel, &slot, sizeof(slot));
        EXPECT(s540FirstTxnOptionalNvlinkActive(&nvIdentity, &observed) == NV_OK);
        EXPECT(observed == record.generation);
        EXPECT(memcmp(savedRecord, &record, sizeof(record)) == 0);
        EXPECT(memcmp(savedGlobal, &globalEpoch, sizeof(globalEpoch)) == 0);
        EXPECT(memcmp(savedCancel, &slot, sizeof(slot)) == 0);
        readRefused(&nvIdentity);
    } else if (!strcmp(caseName, "helper_null_out")) {
        EXPECT(s540GpuOptionalNvlinkAbsent(&gpu, &child, NULL) == NV_ERR_INVALID_ARGUMENT); noConstruction();
    } else if (!strcmp(caseName, "helper_null_gpu") || !strcmp(caseName, "helper_null_slot")) {
        NvBool absent = NV_TRUE;
        EXPECT(s540GpuOptionalNvlinkAbsent(!strcmp(caseName, "helper_null_gpu") ? NULL : &gpu,
            !strcmp(caseName, "helper_null_slot") ? NULL : &child, &absent) == NV_ERR_INVALID_STATE);
        EXPECT(absent == NV_FALSE); noConstruction();
    } else if (!strcmp(caseName, "absence")) {
        EXPECT(callGpu() == NV_OK); EXPECT(child == NULL && registryCalls == 1U); noConstruction();
        readRefused(&nvIdentity); wrapperReturned(); readGood();
    } else if (!strcmp(caseName, "repeat")) {
        EXPECT(callGpu() == NV_OK); EXPECT(callGpu() == NV_ERR_IN_USE); EXPECT(child == NULL); noConstruction();
        wrapperReturned(); readGood();
    } else if (!strcmp(caseName, "hal_skip")) {
        shouldCreate = NV_FALSE; EXPECT(callGpu() == NV_OK); EXPECT(child == NULL && registryCalls == 0); noConstruction();
        wrapperReturned(); readRefused(&nvIdentity);
    } else if (!strcmp(caseName, "other_class") || !strcmp(caseName, "other_instance") ||
               !strcmp(caseName, "initialized") || !strcmp(caseName, "windows")) {
        if (!strcmp(caseName, "other_class")) selectedClass = 0xabc123U;
        if (!strcmp(caseName, "other_instance")) selectedInstance = 1ULL << 40;
        if (!strcmp(caseName, "initialized")) nvlinkLibCtx.nv_devicelist_head.initialized = 1U;
        EXPECT(callGpu() == NV_OK); EXPECT(child == &concrete && dynamicCalls == 1U && engineCalls == 1U);
        EXPECT(registryCalls == 0 && deleteCalls == 0 && deferredCalls == 0);
        wrapperReturned(); readRefused(&nvIdentity);
    } else if (!strcmp(caseName, "engine86") || !strcmp(caseName, "base86") || !strcmp(caseName, "missing")) {
        nvlinkLibCtx.nv_devicelist_head.initialized = 1U;
        if (!strcmp(caseName, "engine86")) engineStatus = NV_ERR_NOT_SUPPORTED;
        if (!strcmp(caseName, "base86")) baseStatus = NV_ERR_NOT_SUPPORTED;
        if (!strcmp(caseName, "missing")) missingProperty = NV_TRUE;
        EXPECT(callGpu() == NV_ERR_NOT_SUPPORTED); EXPECT(child == &concrete && dynamicCalls == 1U);
        EXPECT(deferredCalls == 1U && deleteCalls == 0 && record.cleanupRequested == 1U && first() == NV_ERR_NOT_SUPPORTED);
        wrapperReturned(); readRefused(&nvIdentity);
    } else if (!strcmp(caseName, "published")) {
        child = &previousChild; EXPECT(callGpu() != NV_OK); EXPECT(child == &previousChild); noConstruction();
        wrapperReturned(); readRefused(&nvIdentity);
    } else if (!strcmp(caseName, "registry_error") || !strcmp(caseName, "registry_zero") || !strcmp(caseName, "registry_other") ||
               !strcmp(caseName, "registry_sticky") || !strcmp(caseName, "registry_cancel")) {
        if (!strcmp(caseName, "registry_error")) registryStatus = NV_ERR_OBJECT_NOT_FOUND;
        if (!strcmp(caseName, "registry_zero")) registryValue = 0;
        if (!strcmp(caseName, "registry_other")) registryValue = 2;
        if (!strcmp(caseName, "registry_sticky")) registryMakesSticky = NV_TRUE;
        if (!strcmp(caseName, "registry_cancel")) registryRevokesScope = NV_TRUE;
        NV_STATUS status = callGpu();
        EXPECT(status != NV_OK);
        if (!strcmp(caseName, "registry_error")) EXPECT(status == registryStatus);
        EXPECT(child == NULL); noConstruction(); wrapperReturned(); readRefused(&nvIdentity);
    } else if (!strcmp(caseName, "reserve_failure") || !strcmp(caseName, "reserve_generation")) {
        if (!strcmp(caseName, "reserve_failure")) refuseAtCheck = 3U;
        else changeGenerationAtCheck = 3U;
        EXPECT(callGpu() != NV_OK); EXPECT(child == NULL); noConstruction();
        wrapperReturned(); readRefused(&nvIdentity);
    } else if (!strncmp(caseName, "log_", 4)) {
        if (strcmp(caseName, "log_unavailable")) EXPECT(callGpu() == NV_OK);
        wrapperReturned();
        if (!strcmp(caseName, "log_sticky")) sticky(NV_ERR_NOT_SUPPORTED);
        if (!strcmp(caseName, "log_foreign")) ++actualThread;
        s540LogOptionalNvlinkAbsence(&contextFixture);
        EXPECT(logCalls == 1U);
        if (!strcmp(caseName, "log_unavailable") || !strcmp(caseName, "log_foreign")) {
            EXPECT(strstr(logged, "available=0") != NULL); EXPECT(strstr(logged, "available=1") == NULL);
        } else {
            EXPECT(strstr(logged, "available=1") != NULL); EXPECT(strstr(logged, "absent=1") != NULL);
            EXPECT(strstr(logged, "classId=0xce6818") != NULL); EXPECT(strstr(logged, "instance=0") != NULL);
        }
    } else if (!strcmp(caseName, "get_unpublished")) {
        wrapperReturned(); readRefused(&nvIdentity);
    } else if (!strcmp(caseName, "get_null")) {
        EXPECT(s540OptionalNvlinkRead(NULL, NULL) == NV_ERR_INVALID_ARGUMENT);
        EXPECT(s540FirstTxnOptionalNvlinkActive(&nvIdentity, NULL) == NV_ERR_INVALID_ARGUMENT);
    } else if (!strncmp(caseName, "get_", 4)) {
        EXPECT(callGpu() == NV_OK); wrapperReturned();
        const char *which = caseName + 4;
        if (!strcmp(which, "sticky")) { sticky(NV_ERR_NOT_SUPPORTED); readGood(); }
        else if (!strcmp(which, "inflight")) { record.originalInFlight = 1U; readRefused(&nvIdentity); }
        else if (!strcmp(which, "no_exit")) { record.originalExitReady = 0; readRefused(&nvIdentity); }
        else if (!strcmp(which, "not_returned")) { record.originalReturned = 0; readRefused(&nvIdentity); }
        else if (!strcmp(which, "stale")) { ++record.generation; ++globalEpoch.generation; readRefused(&nvIdentity); }
        else { invalidate(which); readRefused(gpu.pOsGpuInfo); }
    } else {
        invalidate(caseName); activeRefused(gpu.pOsGpuInfo);
        EXPECT(callGpu() != NV_OK); EXPECT(child == NULL); noConstruction();
        wrapperReturned(); readRefused(&nvIdentity);
    }
    EXPECT(deleteCalls == 0);
    EXPECT(slot.checks == 31U && slot.operationAborts == 7U && slot.cleanupExpirations == 5U);
    printf("{\"status\":\"passed\",\"case\":\"%s\",\"checks\":%u}\n", caseName, checks);
    return 0;
}
