/* SPDX-License-Identifier: MIT; explicit CPU endpoints, no hardware execution. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "S540AttachFailureWitness.h"
#include "S540NvidiaGspFirstTransaction.h"

static unsigned checks;
static const char *caseName;
static void requireAt(int condition, const char *expression, unsigned line)
{
    ++checks;
    if (!condition) {
        fprintf(stderr, "case=%s line=%u failed=%s\n", caseName, line, expression);
        exit(2);
    }
}
#define REQUIRE(c) requireAt(!!(c), #c, __LINE__)

static unsigned nvIdentity, foreignNv, ownerIdentity;
static NvU64 currentThread = 71;
static NvBool maySleep = NV_TRUE;
static NV_STATUS currentThreadStatus = NV_OK, snapshotStatus = NV_OK, globalStatus = NV_OK;
static S540FirstTxnSnapshot record;
static S540FirstTxnGlobalSnapshot globalRecord;

NvBool s540Darwin_os_semaphore_may_sleep(void) { return maySleep; }
NV_STATUS s540Darwin_os_get_current_thread(NvU64 *out)
{
    if (currentThreadStatus == NV_OK) *out = currentThread;
    return currentThreadStatus;
}
NV_STATUS s540FirstTxnGetSnapshot(const void *nv, S540FirstTxnSnapshot *out)
{
    if (snapshotStatus != NV_OK) return snapshotStatus;
    if (nv != &nvIdentity || !out) return NV_ERR_INVALID_STATE;
    *out = record; return NV_OK;
}
NV_STATUS s540FirstTxnGlobalGetSnapshot(S540FirstTxnGlobalSnapshot *out)
{
    if (globalStatus != NV_OK) return globalStatus;
    if (!out) return NV_ERR_INVALID_ARGUMENT;
    *out = globalRecord; return NV_OK;
}
static void sticky(NV_STATUS status)
{
    if (status != NV_OK && record.firstStatus == NV_OK) {
        record.firstStatus = status; record.firstSite = 2;
        record.phase = S540_FIRST_RETAINED;
        globalRecord.firstStatus = status;
    }
}
static void setup(void)
{
    memset(&record, 0, sizeof(record)); memset(&globalRecord, 0, sizeof(globalRecord));
    record.generation = 0x1234567800000007ULL; record.masterThread = 71;
    record.phase = S540_FIRST_OP; record.originalInFlight = NV_TRUE;
    globalRecord.owner = &ownerIdentity; globalRecord.nv = &nvIdentity;
    globalRecord.generation = record.generation; globalRecord.masterThread = record.masterThread;
    globalRecord.state = S540_FIRST_GLOBAL_READY;
    globalRecord.originalReturned = NV_TRUE; globalRecord.validated = NV_TRUE;
}
static void wrapperReturned(void)
{
    record.originalReturned = NV_TRUE; record.originalInFlight = NV_FALSE;
}
static void readGood(S540AttachFailureWitness *out)
{
    memset(out, 0xa5, sizeof(*out));
    REQUIRE(s540AttachWitnessRead(&nvIdentity, out) == NV_OK);
    REQUIRE(out->format == 1 && out->bytes == sizeof(*out));
    REQUIRE(out->generation == record.generation);
    REQUIRE(out->complete == 1);
}
static void readRefused(const void *nv, NV_STATUS expected)
{
    S540AttachFailureWitness out, saved;
    memset(&out, 0xa5, sizeof(out)); saved = out;
    REQUIRE(s540AttachWitnessRead(nv, &out) == expected);
    REQUIRE(memcmp(&out, &saved, sizeof(out)) == 0);
}

/* Original GPU/NVOC types are explicit endpoint models; both function bodies
 * below are copied from the exact transformed source by the checker. */
typedef NvU32 NVOC_CLASS_ID;
typedef NvU64 ENGDESCRIPTOR;
typedef struct StubEngine StubEngine;
struct StubEngine { NvBool (*getProperty)(StubEngine *, NvU32); };
typedef StubEngine Dynamic;
typedef StubEngine OBJENGSTATE;
typedef struct { unsigned marker; } NVOC_CLASS_INFO;
typedef struct { unsigned marker; } ENGSTATE_TRANSITION_DATA;
typedef struct {
    NvU32 gpuInstance;
    struct { NvU32 oorArch; } busInfo;
    void *pOS;
    void *pOsGpuInfo;
    NvBool isGspClient;
} OBJGPU;
typedef struct { NvU32 gpuAttachMask, gpuAttachCount, gpuMonolithicRmMask; } OBJGPUMGR;
typedef struct { OBJGPUMGR *manager; } OBJSYS;
typedef struct { void *pOsAttachArg; NvU64 nvDomainBusDeviceFunc; } GPUATTACHARG;
typedef struct { unsigned marker; } Intr;

#define OOR_ARCH_X86_64 64U
#define NVBIT(n) (1U << (n))
#define SYS_GET_INSTANCE() (&systemObject)
#define SYS_GET_GPUMGR(s) ((s)->manager)
#define SYS_GET_OS(s) ((void *)(s))
#define IS_GSP_CLIENT(gpu) ((gpu)->isGspClient)
#define IS_FW_CLIENT(gpu) ((gpu)->isGspClient)
#define GPU_GET_INTR(gpu) ((void)(gpu), (Intr *)0)
#define INTERRUPT_TYPE_DISABLED 0U
#define PDB_PROP_ENGSTATE_IS_MISSING 3U
#define ENGSTATE_STATE_CONSTRUCT 5U
#define LEVEL_INFO 1U
#define MKENGDESC(id, instance) (((NvU64)(id) << 32) ^ (instance))
#define NV_ASSERT_OR_RETURN(c, status) do { if (!(c)) return (status); } while (0)
#define NV_ASSERT_OK_OR_RETURN(expr) do { NV_STATUS result_ = (expr); if (result_ != NV_OK) return result_; } while (0)
#define NV_ASSERT_TRUE_OR_GOTO(status, c, error, label) do { if (!(c)) { (status) = (error); goto label; } } while (0)
#define NV_CHECK_OR_GOTO(level, c, label) do { (void)(level); if (!(c)) goto label; } while (0)
#define NV_ASSERT(c) REQUIRE(c)
#define dynamicCast(object, type) ((type *)fakeEngstateCast(object))

static OBJGPUMGR manager;
static OBJSYS systemObject = { &manager };
static OBJGPU gpu = { 3U, { 0U }, NULL, &nvIdentity, NV_TRUE };
static StubEngine concrete;
static NVOC_CLASS_INFO classInfo;
static Dynamic *publishedChild;
static const NvU32 testClass = 0x00abc123U;
static const NvU64 testInstance = 0x100000005ULL;
static NV_STATUS classStatus = NV_OK, dynamicStatus = NV_OK,
    baseStatus = NV_OK, engineStatus = NV_OK;
static NvBool shouldCreate = NV_TRUE, nullConcrete, nullChildCast, nullEngstateCast,
    missingProperty, engineMakesSticky;
static unsigned classCalls, dynamicCalls, childCastCalls, engstateCastCalls,
    baseCalls, engineCalls, propertyCalls, transitionPreCalls, transitionPostCalls,
    deferredCalls, deleteCalls;
static NvBool getMissing(StubEngine *engine, NvU32 property)
{
    REQUIRE(engine == &concrete); REQUIRE(property == PDB_PROP_ENGSTATE_IS_MISSING);
    ++propertyCalls; return missingProperty;
}
static NvBool gpuShouldCreateObject(OBJGPU *object, NVOC_CLASS_ID id, NvU64 instance)
{
    REQUIRE(object == &gpu); REQUIRE(id == testClass); REQUIRE(instance == testInstance);
    return shouldCreate;
}
static NV_STATUS _gpuChildNvocClassInfoGet(OBJGPU *object, NVOC_CLASS_ID id,
                                         const NVOC_CLASS_INFO **out)
{
    REQUIRE(object == &gpu); REQUIRE(id == testClass); ++classCalls;
    if (classStatus == NV_OK) *out = &classInfo;
    return classStatus;
}
static NV_STATUS objCreateDynamic(Dynamic **out, OBJGPU *object, const NVOC_CLASS_INFO *info)
{
    REQUIRE(object == &gpu); REQUIRE(info == &classInfo); ++dynamicCalls;
    if (dynamicStatus == NV_OK) *out = nullConcrete ? NULL : &concrete;
    return dynamicStatus;
}
static Dynamic *objDynamicCastById(Dynamic *object, NVOC_CLASS_ID id)
{
    REQUIRE(object == &concrete); REQUIRE(id == testClass); ++childCastCalls;
    return nullChildCast ? NULL : object;
}
static void *fakeEngstateCast(Dynamic *object)
{
    REQUIRE(object == &concrete); ++engstateCastCalls;
    return nullEngstateCast ? NULL : object;
}
static NV_STATUS engstateConstructBase(OBJENGSTATE *engine, OBJGPU *object, ENGDESCRIPTOR desc)
{
    REQUIRE(engine == &concrete); REQUIRE(object == &gpu);
    REQUIRE(desc == MKENGDESC(testClass, testInstance)); ++baseCalls; return baseStatus;
}
static void engstateLogStateTransitionPre(OBJENGSTATE *engine, NvU32 state,
                                         ENGSTATE_TRANSITION_DATA *data)
{
    REQUIRE(engine == &concrete); REQUIRE(state == ENGSTATE_STATE_CONSTRUCT); REQUIRE(data != NULL);
    ++transitionPreCalls;
}
static NV_STATUS engstateConstructEngine(OBJGPU *object, OBJENGSTATE *engine, ENGDESCRIPTOR desc)
{
    REQUIRE(object == &gpu); REQUIRE(engine == &concrete);
    REQUIRE(desc == MKENGDESC(testClass, testInstance)); ++engineCalls;
    if (engineMakesSticky) sticky(engineStatus);
    return engineStatus;
}
static void engstateLogStateTransitionPost(OBJENGSTATE *engine, NvU32 state,
                                          ENGSTATE_TRANSITION_DATA *data)
{
    REQUIRE(engine == &concrete); REQUIRE(state == ENGSTATE_STATE_CONSTRUCT); REQUIRE(data != NULL);
    ++transitionPostCalls;
}
static NV_STATUS s540FirstTxnRequestDeferredCleanupGpu(OBJGPU *object, NV_STATUS status)
{
    REQUIRE(object == &gpu); REQUIRE(status != NV_OK); ++deferredCalls;
    record.cleanupRequested = NV_TRUE; sticky(status); return status;
}
/* Kept as a macro endpoint so deliberately restoring a destructor is detected. */
#define objDelete(object) do { (void)(object); ++deleteCalls; } while (0)

@GPU_BODY@

static NvU32 attachFailureStage, currentGpuInstance = 19U;
static unsigned setVisibilityCalls, createGpuCalls, dpcCalls, osCalls, capsCalls,
    postCalls, confCalls, statsCalls, topologyCalls, attachFailureCalls;
static NvBool nestedConstructor;
static NvU32 visibilityValues[3];
static NvBool rmapiLockIsOwner(void) { return NV_TRUE; }
static NV_STATUS _gpumgrCreateGpu(NvU32 instance, GPUATTACHARG *argument)
{
    REQUIRE(instance == gpu.gpuInstance); REQUIRE(argument->pOsAttachArg == &nvIdentity);
    ++createGpuCalls; return attachFailureStage == S540_ATTACH_GPU_CREATE ? NV_ERR_NOT_SUPPORTED : NV_OK;
}
static OBJGPU *gpumgrGetGpu(NvU32 instance)
{
    REQUIRE(instance == gpu.gpuInstance); return &gpu;
}
static NvU32 gpumgrSetCurrentGpuInstance(NvU32 instance)
{
    NvU32 prior = currentGpuInstance;
    REQUIRE(setVisibilityCalls < 3); visibilityValues[setVisibilityCalls++] = instance;
    currentGpuInstance = instance; return prior;
}
static void gpumgrSetAttachInfo(OBJGPU *object, GPUATTACHARG *argument)
{
    REQUIRE(object == &gpu); REQUIRE(argument->pOsAttachArg == &nvIdentity);
}
static NV_STATUS osDpcAttachGpu(OBJGPU *object, void *nv)
{
    REQUIRE(object == &gpu); REQUIRE(nv == &nvIdentity); ++dpcCalls;
    return attachFailureStage == S540_ATTACH_DPC ? NV_ERR_NOT_SUPPORTED : NV_OK;
}
static NV_STATUS osAttachGpu(OBJGPU *object, void *nv)
{
    REQUIRE(object == &gpu); REQUIRE(nv == &nvIdentity); ++osCalls;
    return attachFailureStage == S540_ATTACH_OS ? NV_ERR_NOT_SUPPORTED : NV_OK;
}
static NV_STATUS _gpumgrRegisterRmCapsForGpu(OBJGPU *object)
{
    REQUIRE(object == &gpu); ++capsCalls;
    return attachFailureStage == S540_ATTACH_CAPS ? NV_ERR_NOT_SUPPORTED : NV_OK;
}
static NV_STATUS gpuPostConstruct(OBJGPU *object, GPUATTACHARG *argument)
{
    REQUIRE(object == &gpu); REQUIRE(argument->pOsAttachArg == &nvIdentity); ++postCalls;
    if (nestedConstructor) return gpuCreateObject(object, testClass, testInstance, &publishedChild);
    return attachFailureStage == S540_ATTACH_POST_CONSTRUCT ? NV_ERR_NOT_SUPPORTED : NV_OK;
}
static void _gpumgrGetEncSessionStatsReportingState(OBJGPU *object)
{
    REQUIRE(object == &gpu); ++statsCalls;
}
static NvU32 intrGetIntrEnFromHw_HAL(OBJGPU *object, Intr *interrupt, void *unused)
{
    (void)object; (void)interrupt; (void)unused; REQUIRE(0); return 0;
}
static void intrSetIntrEnInHw_HAL(OBJGPU *object, Intr *interrupt, NvU32 state, void *unused)
{
    (void)object; (void)interrupt; (void)state; (void)unused; REQUIRE(0);
}
static void intrSetStall_HAL(OBJGPU *object, Intr *interrupt, NvU32 state, void *unused)
{
    (void)object; (void)interrupt; (void)state; (void)unused; REQUIRE(0);
}
static void gpumgrAddSystemNvlinkTopo(NvU64 dbdf) { REQUIRE(dbdf == 0x200U); ++topologyCalls; }
static void gpumgrAddSystemMIGInstanceTopo(NvU64 dbdf) { REQUIRE(dbdf == 0x200U); ++topologyCalls; }
static NV_STATUS _gpumgrDetermineConfComputeCapabilities(OBJGPUMGR *mgr, OBJGPU *object)
{
    REQUIRE(mgr == &manager); REQUIRE(object == &gpu); ++confCalls;
    return attachFailureStage == S540_ATTACH_CONF_COMPUTE ? NV_ERR_NOT_SUPPORTED : NV_OK;
}
static NV_STATUS s540FirstTxnOriginalGpuAttachFailed(void *nv, NV_STATUS status)
{
    REQUIRE(nv == &nvIdentity); REQUIRE(status != NV_OK); ++attachFailureCalls;
    record.cleanupRequested = NV_TRUE; sticky(status); return status;
}

@GPUMGR_BODY@

static void checkChild(NvU32 expectedStage, NV_STATUS expectedStatus)
{
    S540AttachFailureWitness view;
    s540AttachWitnessBegin(&nvIdentity);
    s540AttachWitnessProgress(&nvIdentity, S540_ATTACH_POST_CONSTRUCT);
    NV_STATUS result = gpuCreateObject(&gpu, testClass, testInstance, &publishedChild);
    REQUIRE(result == expectedStatus);
    REQUIRE(deleteCalls == 0);
    s540AttachWitnessComplete(&nvIdentity); wrapperReturned(); readGood(&view);
    if (expectedStatus == NV_OK) {
        REQUIRE(view.firstFailureValid == 0);
        if (shouldCreate) REQUIRE(view.lastCtorStage == S540_CTOR_COMPLETE);
    } else {
        REQUIRE(view.firstFailureValid == 1);
        REQUIRE(view.firstAttachStage == S540_ATTACH_POST_CONSTRUCT);
        REQUIRE(view.firstClassId == testClass); REQUIRE(view.firstInstance == testInstance);
        REQUIRE(view.firstCtorStage == expectedStage);
        REQUIRE(view.firstStatus == (engineStatus != NV_OK ? engineStatus : expectedStatus));
        REQUIRE((view.observedMask & S540_ATTACH_OBS_GSP_CLIENT) != 0);
        REQUIRE(view.gspClient == gpu.isGspClient);
        if (expectedStage == S540_CTOR_MISSING) {
            REQUIRE((view.observedMask & S540_ATTACH_OBS_MISSING) != 0); REQUIRE(view.missing == 1);
        } else {
            REQUIRE((view.observedMask & S540_ATTACH_OBS_MISSING) == 0); REQUIRE(view.missing == 0);
        }
    }
    if (!shouldCreate) {
        REQUIRE(!classCalls && !dynamicCalls && !baseCalls && !engineCalls && !propertyCalls);
    } else {
        REQUIRE(classCalls == 1);
        REQUIRE(dynamicCalls == (classStatus == NV_OK ? 1U : 0U));
    }
    if (expectedStage >= S540_CTOR_ENGSTATE_CAST || expectedStage == S540_CTOR_COMPLETE)
        REQUIRE(publishedChild == &concrete);
    else REQUIRE(publishedChild == NULL);
    if (expectedStage == S540_CTOR_BASE) {
        REQUIRE(baseCalls == 1 && engineCalls == 0 && propertyCalls == 0 && deferredCalls == 1);
    }
    if (expectedStage == S540_CTOR_ENGINE || expectedStage == S540_CTOR_MISSING || expectedStage == S540_CTOR_COMPLETE) {
        REQUIRE(baseCalls == 1 && engineCalls == 1);
        REQUIRE(transitionPreCalls == 1 && transitionPostCalls == 1 && propertyCalls == 1);
    }
}
static void checkAttach(NvU32 failStage)
{
    S540AttachFailureWitness view;
    GPUATTACHARG argument = { &nvIdentity, 0x200U };
    attachFailureStage = failStage;
    NV_STATUS result = gpumgrAttachGpu(gpu.gpuInstance, &argument);
    REQUIRE(result == (failStage || nestedConstructor ? NV_ERR_NOT_SUPPORTED : NV_OK));
    REQUIRE(createGpuCalls == 1); REQUIRE(currentGpuInstance == 19U);
    if (failStage == S540_ATTACH_GPU_CREATE) {
        REQUIRE(setVisibilityCalls == 0); REQUIRE(dpcCalls == 0);
    } else {
        REQUIRE(setVisibilityCalls == 2); REQUIRE(visibilityValues[0] == gpu.gpuInstance);
        REQUIRE(visibilityValues[1] == 19U); REQUIRE(dpcCalls == 1);
    }
    REQUIRE(deleteCalls == 0);
    wrapperReturned(); readGood(&view);
    if (!failStage && !nestedConstructor) {
        REQUIRE(view.firstFailureValid == 0); REQUIRE(view.lastAttachStage == S540_ATTACH_COMPLETE);
        REQUIRE(statsCalls == 1 && confCalls == 1 && topologyCalls == 2);
        REQUIRE(manager.gpuAttachMask == NVBIT(gpu.gpuInstance) && manager.gpuAttachCount == 1);
    } else if (nestedConstructor) {
        REQUIRE(view.firstFailureValid == 1 && view.firstStatus == NV_ERR_NOT_SUPPORTED);
        REQUIRE(view.firstAttachStage == S540_ATTACH_POST_CONSTRUCT);
        REQUIRE(view.firstClassId == testClass && view.firstInstance == testInstance);
        REQUIRE(view.firstCtorStage == S540_CTOR_ENGINE);
        REQUIRE(view.observedMask == S540_ATTACH_OBS_GSP_CLIENT && view.gspClient == 1);
        REQUIRE(publishedChild == &concrete && deferredCalls == 1 && attachFailureCalls == 1);
        REQUIRE(record.firstStatus == NV_ERR_NOT_SUPPORTED && record.cleanupRequested == 1);
    } else {
        REQUIRE(view.firstFailureValid == 1 && view.firstStatus == NV_ERR_NOT_SUPPORTED);
        REQUIRE(view.firstAttachStage == failStage);
        REQUIRE(view.firstClassId == 0 && view.firstInstance == 0 && view.firstCtorStage == 0);
        REQUIRE(view.observedMask == 0); REQUIRE(attachFailureCalls == 1);
    }
    if (failStage >= S540_ATTACH_CAPS || nestedConstructor)
        REQUIRE(manager.gpuAttachMask == NVBIT(gpu.gpuInstance) && manager.gpuAttachCount == 1);
    else if (failStage)
        REQUIRE(manager.gpuAttachMask == 0 && manager.gpuAttachCount == 0);
}
static void beginProgress(void)
{
    s540AttachWitnessBegin(&nvIdentity);
    s540AttachWitnessProgress(&nvIdentity, S540_ATTACH_POST_CONSTRUCT);
    s540AttachWitnessChildProgress(&nvIdentity, testClass, testInstance, S540_CTOR_BASE);
}
static void addFailure(const void *nv)
{
    s540AttachWitnessChildFailure(nv, testClass, testInstance, S540_CTOR_ENGINE,
        NV_ERR_NOT_SUPPORTED, S540_ATTACH_OBS_GSP_CLIENT, 0, 1);
}
static void finalize(void)
{
    s540AttachWitnessComplete(&nvIdentity); wrapperReturned();
}
static void checkLifecycle(void)
{
    S540AttachFailureWitness view;
    if (!strcmp(caseName, "lifecycle_unbegun")) { readRefused(&nvIdentity, NV_ERR_NOT_READY); return; }
    beginProgress();
    if (!strcmp(caseName, "active_read")) { readRefused(&nvIdentity, NV_ERR_NOT_READY); return; }
    if (!strcmp(caseName, "early_original_read")) {
        s540AttachWitnessComplete(&nvIdentity); readRefused(&nvIdentity, NV_ERR_INVALID_STATE); return;
    }
    if (!strcmp(caseName, "sticky_read")) { sticky(NV_ERR_NOT_SUPPORTED); addFailure(&nvIdentity); }
    else if (!strcmp(caseName, "repeated_begin")) {
        addFailure(&nvIdentity); s540AttachWitnessBegin(&nvIdentity);
        s540AttachWitnessAttachFailure(&nvIdentity, S540_ATTACH_CONF_COMPUTE, NV_ERR_INVALID_STATE);
    } else if (!strcmp(caseName, "foreign_update") || !strcmp(caseName, "irq_update") ||
               !strcmp(caseName, "stale_update") || !strcmp(caseName, "wrong_nv_update")) {
        const void *nv = &nvIdentity;
        if (!strcmp(caseName, "foreign_update")) currentThread = 72;
        if (!strcmp(caseName, "irq_update")) maySleep = NV_FALSE;
        if (!strcmp(caseName, "stale_update")) ++globalRecord.generation;
        if (!strcmp(caseName, "wrong_nv_update")) nv = &foreignNv;
        s540AttachWitnessProgress(nv, S540_ATTACH_CONF_COMPUTE);
        s540AttachWitnessChildProgress(nv, 0x999U, 9, S540_CTOR_MISSING);
        addFailure(nv); s540AttachWitnessAttachFailure(nv, S540_ATTACH_CONF_COMPUTE, NV_ERR_INVALID_STATE);
        s540AttachWitnessComplete(nv);
        currentThread = 71; maySleep = NV_TRUE; globalRecord.generation = record.generation;
        finalize(); readGood(&view);
        REQUIRE(view.firstFailureValid == 0 && view.lastAttachStage == S540_ATTACH_POST_CONSTRUCT);
        REQUIRE(view.lastClassId == testClass && view.lastInstance == testInstance && view.lastCtorStage == S540_CTOR_BASE);
        return;
    } else if (!strcmp(caseName, "stale_read") || !strcmp(caseName, "foreign_read") || !strcmp(caseName, "irq_read")) {
        finalize();
        if (!strcmp(caseName, "stale_read")) ++record.generation;
        if (!strcmp(caseName, "foreign_read")) currentThread = 72;
        if (!strcmp(caseName, "irq_read")) maySleep = NV_FALSE;
        readRefused(&nvIdentity, NV_ERR_INVALID_STATE); return;
    } else if (!strcmp(caseName, "bad_getter")) {
        finalize(); readRefused(NULL, NV_ERR_INVALID_ARGUMENT);
        REQUIRE(s540AttachWitnessRead(&nvIdentity, NULL) == NV_ERR_INVALID_ARGUMENT);
        readRefused(&foreignNv, NV_ERR_INVALID_STATE);
        snapshotStatus = NV_ERR_NOT_SUPPORTED; readRefused(&nvIdentity, NV_ERR_INVALID_STATE); return;
    } else if (!strcmp(caseName, "invalid_notes")) {
        s540AttachWitnessProgress(&nvIdentity, 0); s540AttachWitnessProgress(&nvIdentity, 8);
        s540AttachWitnessChildProgress(&nvIdentity, 3, 7, 0); s540AttachWitnessChildProgress(&nvIdentity, 3, 7, 10);
        s540AttachWitnessChildFailure(&nvIdentity, 3, 7, 0, NV_ERR_NOT_SUPPORTED, 0, 0, 0);
        s540AttachWitnessChildFailure(&nvIdentity, 3, 7, S540_CTOR_ENGINE, NV_OK, 0, 0, 0);
        s540AttachWitnessChildFailure(&nvIdentity, 3, 7, S540_CTOR_ENGINE, NV_ERR_NOT_SUPPORTED, 4, 0, 0);
        s540AttachWitnessChildFailure(&nvIdentity, 3, 7, S540_CTOR_ENGINE, NV_ERR_NOT_SUPPORTED, S540_ATTACH_OBS_MISSING, 2, 0);
        s540AttachWitnessChildFailure(&nvIdentity, 3, 7, S540_CTOR_ENGINE, NV_ERR_NOT_SUPPORTED, S540_ATTACH_OBS_GSP_CLIENT, 0, 2);
        s540AttachWitnessAttachFailure(&nvIdentity, S540_ATTACH_COMPLETE, NV_ERR_NOT_SUPPORTED);
        s540AttachWitnessAttachFailure(&nvIdentity, S540_ATTACH_GPU_CREATE, NV_OK);
        addFailure(&nvIdentity);
    } else { REQUIRE(0); }
    finalize(); readGood(&view);
    REQUIRE(view.firstFailureValid == 1 && view.firstStatus == NV_ERR_NOT_SUPPORTED);
    REQUIRE(view.firstClassId == testClass && view.firstInstance == testInstance && view.firstCtorStage == S540_CTOR_ENGINE);
    REQUIRE(view.observedMask == S540_ATTACH_OBS_GSP_CLIENT && view.missing == 0 && view.gspClient == 1);
}
static void checkGpuIdentity(void *actualOsIdentity)
{
    S540AttachFailureWitness view;
    s540AttachWitnessBegin(&nvIdentity);
    s540AttachWitnessProgress(&nvIdentity, S540_ATTACH_POST_CONSTRUCT);
    gpu.pOsGpuInfo = actualOsIdentity;
    baseStatus = NV_ERR_NOT_SUPPORTED;
    REQUIRE(gpuCreateObject(&gpu, testClass, testInstance, &publishedChild) == NV_ERR_NOT_SUPPORTED);
    REQUIRE(baseCalls == 1 && engineCalls == 0 && publishedChild == &concrete);
    REQUIRE(deferredCalls == 1 && deleteCalls == 0);
    gpu.pOsGpuInfo = &nvIdentity;
    finalize(); readGood(&view);
    REQUIRE(view.firstFailureValid == 0 && view.lastClassId == 0 && view.lastCtorStage == 0);
    REQUIRE(view.lastAttachStage == S540_ATTACH_POST_CONSTRUCT);
}
int main(int argc, char **argv)
{
    if (argc != 2) return 64;
    caseName = argv[1]; setup(); concrete.getProperty = getMissing;
    if (!strcmp(caseName, "gpu_skip")) { shouldCreate = NV_FALSE; checkChild(0, NV_OK); }
    else if (!strcmp(caseName, "class_info")) { classStatus = NV_ERR_NOT_SUPPORTED; checkChild(S540_CTOR_CLASS_INFO, NV_ERR_NOT_SUPPORTED); }
    else if (!strcmp(caseName, "dynamic_create")) { dynamicStatus = NV_ERR_NOT_SUPPORTED; checkChild(S540_CTOR_DYNAMIC_CREATE, NV_ERR_NOT_SUPPORTED); }
    else if (!strcmp(caseName, "concrete_null")) { nullConcrete = NV_TRUE; checkChild(S540_CTOR_CONCRETE_CHECK, NV_ERR_INVALID_STATE); }
    else if (!strcmp(caseName, "child_cast")) { nullChildCast = NV_TRUE; checkChild(S540_CTOR_CHILD_CAST, NV_ERR_INVALID_STATE); }
    else if (!strcmp(caseName, "engstate_cast")) { nullEngstateCast = NV_TRUE; checkChild(S540_CTOR_ENGSTATE_CAST, NV_ERR_INVALID_STATE); }
    else if (!strcmp(caseName, "base86")) { baseStatus = NV_ERR_NOT_SUPPORTED; checkChild(S540_CTOR_BASE, NV_ERR_NOT_SUPPORTED); }
    else if (!strcmp(caseName, "engine86")) { engineStatus = NV_ERR_NOT_SUPPORTED; checkChild(S540_CTOR_ENGINE, NV_ERR_NOT_SUPPORTED); }
    else if (!strcmp(caseName, "engine86_not_gsp")) { gpu.isGspClient = NV_FALSE; engineStatus = NV_ERR_NOT_SUPPORTED; checkChild(S540_CTOR_ENGINE, NV_ERR_NOT_SUPPORTED); }
    else if (!strcmp(caseName, "engine_error_missing")) { engineStatus = NV_ERR_GENERIC; missingProperty = NV_TRUE; checkChild(S540_CTOR_ENGINE, NV_ERR_NOT_SUPPORTED); }
    else if (!strcmp(caseName, "missing")) { missingProperty = NV_TRUE; checkChild(S540_CTOR_MISSING, NV_ERR_NOT_SUPPORTED); }
    else if (!strcmp(caseName, "child_success")) { checkChild(S540_CTOR_COMPLETE, NV_OK); }
    else if (!strcmp(caseName, "gpu_foreign_nv")) checkGpuIdentity(&foreignNv);
    else if (!strcmp(caseName, "gpu_null_nv")) checkGpuIdentity(NULL);
    else if (!strcmp(caseName, "attach_create")) checkAttach(S540_ATTACH_GPU_CREATE);
    else if (!strcmp(caseName, "dpc")) checkAttach(S540_ATTACH_DPC);
    else if (!strcmp(caseName, "os")) checkAttach(S540_ATTACH_OS);
    else if (!strcmp(caseName, "caps")) checkAttach(S540_ATTACH_CAPS);
    else if (!strcmp(caseName, "post")) checkAttach(S540_ATTACH_POST_CONSTRUCT);
    else if (!strcmp(caseName, "conf")) checkAttach(S540_ATTACH_CONF_COMPUTE);
    else if (!strcmp(caseName, "attach_success")) checkAttach(0);
    else if (!strcmp(caseName, "nested_first")) { nestedConstructor = NV_TRUE; engineStatus = NV_ERR_NOT_SUPPORTED; engineMakesSticky = NV_TRUE; checkAttach(0); }
    else checkLifecycle();
    printf("{\"status\":\"passed\",\"case\":\"%s\",\"checks\":%u}\n", caseName, checks);
    return 0;
}
