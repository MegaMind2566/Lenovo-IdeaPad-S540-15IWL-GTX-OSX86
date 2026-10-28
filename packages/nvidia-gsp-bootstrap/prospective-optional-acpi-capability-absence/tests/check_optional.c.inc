/* SPDX-License-Identifier: MIT; actual C bodies with explicit CPU endpoints. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#include "S540NvidiaGspFirstTransaction.h"
#include "S540OptionalAcpiAbsence.h"


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

/* Actual source declarations/macros, with typed CPU endpoints for device and
 * OS calls. No AML, GPU registers or physical allocation is exercised. */
#define NV_API_CALL
#define ct_assert(c) _Static_assert(c, #c)
#include "nvmisc.h"
#include "acpigenfuncs.h"
#include "jt.h"
#include "nbci.h"
#include "nvop.h"
#include "nvhybridacpi.h"
@CALLBACK_MACROS@
#define MAX_DSM_SUPPORTED_FUNCS_RTN_LEN 8
#define NV_PRINTF(...) ((void)0)
#define NV_ASSERT_OR_RETURN(c,s) do { if (!(c)) return (s); } while (0)
#define NV_ASSERT_OR_RETURN_VOID(c) do { if (!(c)) return; } while (0)
#define portMemSet(p,v,n) memset((p),(v),(n))
#define portMemCopy(d,dn,s,sn) (EXPECT((sn) <= (dn)), memcpy((d),(s),(sn)))
#define isDsmGetSuppFuncListCached(p,f) ((p)->acpi.dsm[f].suppFuncStatus != DSM_FUNC_STATUS_UNKNOWN)
#define isDsmGetSuppFuncListFailed(p,f) ((p)->acpi.dsm[f].suppFuncStatus == DSM_FUNC_STATUS_FAILED)
#define PDB_PROP_KDISP_INTERNAL_PANEL_DISCONNECTED 1U
#define GPU_GET_KERNEL_DISPLAY(p) ((void)(p), (KernelDisplay *)NULL)
typedef unsigned nv_state_t;
typedef struct KernelDisplay KernelDisplay;
struct KernelDisplay { NvBool (*getProperty)(KernelDisplay *, NvU32); };
typedef struct {
    NvU32 suppFuncStatus; NvU8 suppFuncs[MAX_DSM_SUPPORTED_FUNCS_RTN_LEN];
    NvU32 suppFuncsLen; NvBool bArg3isInteger; NvU32 callbackStatus, callback;
} ACPI_DSM_CACHE;
typedef struct { NvU32 acpiId, mode; NV_STATUS status; } MUX_ELEMENT;
typedef struct OBJGPU {
    void *pOsGpuInfo; NvBool tegra;
    struct {
        ACPI_DSM_CACHE dsm[ACPI_DSM_FUNCTION_COUNT];
        ACPI_DSM_FUNCTION dispStatusHotplugFunc,dispStatusConfigFunc,perfPostPowerStateFunc,stereo3dStateActiveFunc;
        NvU32 dsmPlatCapsCache[ACPI_DSM_FUNCTION_COUNT], MDTLFeatureSupport;
        ACPI_DSM_FUNCTION dsmCurrentFunc[NV_ACPI_GENERIC_FUNC_COUNT];
        NvU32 dsmCurrentSubFunc[NV_ACPI_GENERIC_FUNC_COUNT],dsmCurrentFuncSupport;
    } acpi;
    struct {
        NvBool bValid;
        struct { NV_STATUS status; NvU32 acpiIdListLen,acpiIdList[8]; } dodMethodData;
        struct { NV_STATUS status; NvU32 jtCaps; NvU16 jtRevId; NvBool bSBIOSCaps; } jtMethodData;
        struct { NvU32 tableLen; MUX_ELEMENT acpiIdMuxModeTable[8],acpiIdMuxPartTable[8],acpiIdMuxStateTable[8]; } muxMethodData;
        struct { NV_STATUS status; NvU32 optimusCaps; } capsMethodData;
    } acpiMethodData;
} OBJGPU;
@REGISTRY_NV_MACRO@
#define IsTEGRA(p) ((p)->tegra)
static OBJGPU gpu;
static unsigned osDsmCalls, osDodCalls, muxCalls, gc6Calls, unavailableCalls;
static NvBool retryInvalidArgument;
static void sticky(NV_STATUS status)
{
    if (status != NV_OK && !first()) {
        record.control = ((NvU64)4U << 32) | (NvU32)status;
        record.phase = S540_FIRST_RETAINED;
    }
}
void s540GlobalRmRecordServiceName(const char *name) { EXPECT(name != NULL); }
void s540GlobalRmRecordUnavailable(NvU32 service)
{ EXPECT(service == 0); ++unavailableCalls; sticky(NV_ERR_NOT_SUPPORTED); }
@ACPI_FACADE@
static NV_STATUS remapDsmFunctionAndSubFunction(OBJGPU *p,ACPI_DSM_FUNCTION *function,NvU32 *subfunction)
{
    EXPECT(p == &gpu && function && subfunction);
    /* Explicit CPU endpoint: direct reviewed enum mappings are identities;
     * generic mappings have no available backend capability. */
    return *function < ACPI_DSM_FUNCTION_COUNT ? NV_OK : NV_ERR_NOT_SUPPORTED;
}
@DSM_SUBFUNCTION_CHECK@
@DSM_CALL_CHECK@
@DSM_ERROR@
static NV_STATUS osCallACPI_DSM(OBJGPU *p,ACPI_DSM_FUNCTION function,NvU32 subfunction,NvU32 *value,NvU16 *size)
{
    EXPECT(p == &gpu && value && size);
    NV_STATUS status = checkDsmCall(p,&function,&subfunction,value,size);
    if (status != NV_WARN_MORE_PROCESSING_REQUIRED) return status;
    ++osDsmCalls;
    if (retryInvalidArgument && !p->acpi.dsm[function].bArg3isInteger) {
        /* The original retry sets the cache FAILED before the first call.
         * This endpoint fault is the original malformed-arg result only. */
        return NV_ERR_INVALID_ARGUMENT;
    }
    return nv_acpi_dsm_method((nv_state_t *)NV_GET_NV_STATE(p),NULL,1,NV_FALSE,subfunction,
        value,4,NULL,value,size);
}
static NV_STATUS osCallACPI_DOD(OBJGPU *p,NvU32 *out,NvU32 *size)
{ EXPECT(p == &gpu && out && size); ++osDodCalls; return nv_acpi_dod_method((nv_state_t *)NV_GET_NV_STATE(p),out,size); }
static NV_STATUS osCallACPI_MXDM(OBJGPU *p,NvU32 id,NvU32 *out)
{ (void)p;(void)id;(void)out; ++muxCalls; return NV_ERR_NOT_SUPPORTED; }
static NV_STATUS osCallACPI_MXID(OBJGPU *p,NvU32 id,NvU32 *out)
{ (void)p;(void)id;(void)out; ++muxCalls; return NV_ERR_NOT_SUPPORTED; }
static NV_STATUS osCallACPI_MXDS(OBJGPU *p,NvU32 id,NvU32 *out)
{ (void)p;(void)id;(void)out; ++muxCalls; return NV_ERR_NOT_SUPPORTED; }
static void gpuSetGC6SBIOSCapabilities(OBJGPU *p)
{ EXPECT(p == &gpu); ++gc6Calls; EXPECT(p->acpiMethodData.jtMethodData.status != NV_OK); }
@CACHE_SUPPORT@
@CACHE_GENERIC@
@CACHE_CALLBACK@
@CACHE_CAPS@
@CACHE_FEATURE@
@CACHE_METHODS@
@ACPI_INIT@

static char logged[1024];
static unsigned logCalls;
#define NV_DBG_ERRORS 3U
static void nv_printf(NvU32 level, const char *format, ...)
{
    EXPECT(level == NV_DBG_ERRORS && format != NULL); ++logCalls;
    va_list args; va_start(args, format); vsnprintf(logged,sizeof(logged),format,args); va_end(args);
}
@CONTEXT_LOGGER@
static void setup(void)
{
    memset(&record,0,sizeof(record)); memset(&globalEpoch,0,sizeof(globalEpoch));
    record.owner=&ownerIdentity;record.nv=&nvIdentity;
    record.generation=0x1234567800000007ULL;record.masterThread=actualThread;
    record.phase=S540_FIRST_OP;record.originalInFlight=1U;
    globalEpoch.owner=record.owner;globalEpoch.generation=record.generation;
    globalEpoch.thread=actualThread;globalEpoch.state=S540_FIRST_GLOBAL_READY;
    globalEpoch.validated=globalEpoch.originalReturned=1U;
    record.cancelToken=13U;slot.control=(record.cancelToken<<SHIFT)|BOUND|OPERATION;
    slot.generation=record.cancelToken;slot.ownerThread=actualThread;slot.state=&nvIdentity;
    slot.checks=31U;slot.operationAborts=7U;slot.cleanupExpirations=5U;
    gpu.pOsGpuInfo=&nvIdentity;
}
static void wrapperReturned(void)
{record.originalExitReady=record.originalReturned=1U;record.originalInFlight=0;}
static void readRefused(const void *nv)
{
    S540OptionalAcpiAbsence out,before;memset(&out,0xa5,sizeof(out));before=out;
    EXPECT(s540OptionalAcpiRead(nv,&out)!=NV_OK);EXPECT(!memcmp(&before,&out,sizeof(out)));
}
static void readGood(NvU32 mask,NvU32 dsm,NvU32 dod)
{
    S540OptionalAcpiAbsence out;memset(&out,0xa5,sizeof(out));
    EXPECT(s540OptionalAcpiRead(&nvIdentity,&out)==NV_OK);
    EXPECT(out.format==1U&&out.bytes==32U&&out.generation==record.generation);
    EXPECT(out.dsmAbsentMask==mask&&out.dsmQueries==dsm&&out.dodQueries==dod&&out.reserved==0U);
}
static void absenceDefaults(void)
{
    for(unsigned i=0;i<ACPI_DSM_FUNCTION_COUNT;++i)EXPECT(gpu.acpi.dsm[i].suppFuncStatus==DSM_FUNC_STATUS_FAILED);
    EXPECT(gpu.acpiMethodData.bValid==NV_TRUE);
    EXPECT(gpu.acpiMethodData.dodMethodData.status==NV_ERR_NOT_SUPPORTED);
    EXPECT(gpu.acpiMethodData.jtMethodData.status!=NV_OK&&gpu.acpiMethodData.capsMethodData.status!=NV_OK);
    EXPECT(gpu.acpiMethodData.jtMethodData.jtCaps==0&&gpu.acpiMethodData.capsMethodData.optimusCaps==0);
    EXPECT(gpu.acpiMethodData.muxMethodData.tableLen==0&&muxCalls==0);
    EXPECT(gpu.acpi.dsmCurrentFuncSupport==0&&gpu.acpi.MDTLFeatureSupport==DSM_FUNC_STATUS_FAILED);
    EXPECT(gpu.acpi.dispStatusHotplugFunc==ACPI_DSM_FUNCTION_COUNT&&gpu.acpi.dispStatusConfigFunc==ACPI_DSM_FUNCTION_COUNT);
    EXPECT(gpu.acpi.perfPostPowerStateFunc==ACPI_DSM_FUNCTION_COUNT&&gpu.acpi.stereo3dStateActiveFunc==ACPI_DSM_FUNCTION_COUNT);
}
static void invalidate(const char *name)
{
    if(!strcmp(name,"foreign_nv"))gpu.pOsGpuInfo=&foreignNv;
    else if(!strcmp(name,"null_nv"))gpu.pOsGpuInfo=NULL;
    else if(!strcmp(name,"foreign_master"))++actualThread;
    else if(!strcmp(name,"irq"))maySleep=NV_FALSE;
    else if(!strcmp(name,"thread_error"))threadStatus=NV_ERR_NOT_SUPPORTED;
    else if(!strcmp(name,"thread_zero"))actualThread=0;
    else if(!strcmp(name,"unbound"))record.generation=0;
    else if(!strcmp(name,"owner_missing"))record.owner=NULL;
    else if(!strcmp(name,"owner_mismatch"))globalEpoch.owner=&foreignOwner;
    else if(!strcmp(name,"generation_mismatch"))++globalEpoch.generation;
    else if(!strcmp(name,"master_mismatch"))++globalEpoch.thread;
    else if(!strcmp(name,"sticky"))record.control=NV_ERR_NOT_SUPPORTED;
    else if(!strcmp(name,"phase"))record.phase=S540_FIRST_RETAINED;
    else if(!strcmp(name,"not_inflight"))record.originalInFlight=0;
    else if(!strcmp(name,"exit_ready"))record.originalExitReady=1U;
    else if(!strcmp(name,"already_returned"))record.originalReturned=1U;
    else if(!strcmp(name,"global_state"))globalEpoch.state=S540_FIRST_GLOBAL_RETAINED;
    else if(!strcmp(name,"global_unvalidated"))globalEpoch.validated=0;
    else if(!strcmp(name,"global_not_returned"))globalEpoch.originalReturned=0;
    else if(!strcmp(name,"global_status"))globalEpoch.originalStatus=NV_ERR_NOT_SUPPORTED;
    else if(!strcmp(name,"global_validation"))globalEpoch.validationStatus=NV_ERR_NOT_SUPPORTED;
    else if(!strcmp(name,"cancel_scope")||!strcmp(name,"cancel_idle"))slot.control=(record.cancelToken<<SHIFT)|BOUND;
    else if(!strcmp(name,"cancel_token"))record.cancelToken=0;
    else if(!strcmp(name,"cancel_unbound"))slot.control&=~(NvU64)BOUND;
    else if(!strcmp(name,"cancel_owner"))++slot.ownerThread;
    else if(!strcmp(name,"cancel_cleanup"))slot.control=(record.cancelToken<<SHIFT)|BOUND|CLEANUP;
    else if(!strcmp(name,"cancel_revoked"))slot.control|=REVOKED;
    else if(!strcmp(name,"cancel_publication"))slot.control|=PUBLISHING;
    else if(!strcmp(name,"cancel_generation"))slot.control+=1ULL<<SHIFT;
    else if(!strcmp(name,"cancel_format"))corruptCancelFormat=NV_TRUE;
    else if(!strcmp(name,"cancel_bound"))corruptCancelBound=NV_TRUE;
    else if(!strcmp(name,"cancel_output_generation"))corruptCancelGeneration=NV_TRUE;
    else if(!strcmp(name,"cancel_race"))cancellationWordRace=NV_TRUE;
    else EXPECT(0);
}
int main(int argc,char **argv)
{
    EXPECT(argc==2);caseName=argv[1];setup();
    if(!strcmp(caseName,"active")) {
        unsigned char before[sizeof(record)],cancelBefore[sizeof(slot)];NvU64 generation=0;
        memcpy(before,&record,sizeof(record));memcpy(cancelBefore,&slot,sizeof(slot));
        EXPECT(s540FirstTxnOptionalNvlinkActive(&nvIdentity,&generation)==NV_OK&&generation==record.generation);
        EXPECT(!memcmp(before,&record,sizeof(record))&&!memcmp(cancelBefore,&slot,sizeof(slot)));
        readRefused(&nvIdentity);
    } else if(!strcmp(caseName,"all_absence")) {
        acpiDsmInit(&gpu);absenceDefaults();EXPECT(osDsmCalls==0&&osDodCalls==0&&unavailableCalls==0&&first()==NV_OK);
        readRefused(&nvIdentity);wrapperReturned();readGood(0xfffU,12U,1U);
    } else if(!strcmp(caseName,"dod_only")) {
        EXPECT(s540OptionalAcpiCommitAbsent(&nvIdentity,S540_OPTIONAL_ACPI_DOD,0)==NV_OK);
        wrapperReturned();readGood(0,0,1);
    } else if(!strcmp(caseName,"each_dsm")) {
        for(unsigned i=0;i<12;++i)EXPECT(s540OptionalAcpiCommitAbsent(&nvIdentity,S540_OPTIONAL_ACPI_DSM_SUPPORT,i)==NV_OK);
        wrapperReturned();readGood(0xfffU,12U,0);
    } else if(!strcmp(caseName,"repeat_dsm")||!strcmp(caseName,"repeat_dod")) {
        NvU32 query=!strcmp(caseName,"repeat_dsm")?S540_OPTIONAL_ACPI_DSM_SUPPORT:S540_OPTIONAL_ACPI_DOD;
        EXPECT(s540OptionalAcpiCommitAbsent(&nvIdentity,query,0)==NV_OK);
        EXPECT(s540OptionalAcpiCommitAbsent(&nvIdentity,query,0)==NV_OK);
        wrapperReturned();readGood(query==S540_OPTIONAL_ACPI_DSM_SUPPORT?1U:0U,query==S540_OPTIONAL_ACPI_DSM_SUPPORT?1U:0U,query==S540_OPTIONAL_ACPI_DOD?1U:0U);
    } else if(!strcmp(caseName,"bad_query")||!strcmp(caseName,"bad_dsm_function")||!strcmp(caseName,"bad_dod_function")) {
        NvU32 query=!strcmp(caseName,"bad_query")?0U:(!strcmp(caseName,"bad_dsm_function")?S540_OPTIONAL_ACPI_DSM_SUPPORT:S540_OPTIONAL_ACPI_DOD);
        NvU32 fn=!strcmp(caseName,"bad_dsm_function")?12U:1U;
        EXPECT(s540OptionalAcpiCommitAbsent(&nvIdentity,query,fn)!=NV_OK);wrapperReturned();readRefused(&nvIdentity);
    } else if(!strcmp(caseName,"prefailed")||!strcmp(caseName,"override")||!strcmp(caseName,"success")) {
        NvU32 keep=!strcmp(caseName,"prefailed")?DSM_FUNC_STATUS_FAILED:(!strcmp(caseName,"override")?DSM_FUNC_STATUS_OVERRIDE:DSM_FUNC_STATUS_SUCCESS);
        gpu.acpi.dsm[2].suppFuncStatus=keep;gpu.acpi.dsm[2].suppFuncsLen=0;
        _acpiDsmSupportedFuncCacheInit(&gpu);
        EXPECT(gpu.acpi.dsm[2].suppFuncStatus==keep);EXPECT(osDsmCalls==0&&unavailableCalls==0);
        wrapperReturned();readGood(0xffbU,11U,0);
    } else if(!strcmp(caseName,"tegra")) {
        gpu.tegra=NV_TRUE;_acpiDsmSupportedFuncCacheInit(&gpu);EXPECT(osDsmCalls==0);
        for(unsigned i=0;i<12;++i)EXPECT(gpu.acpi.dsm[i].suppFuncStatus==DSM_FUNC_STATUS_FAILED);
        wrapperReturned();readGood(1U<<ACPI_DSM_FUNCTION_NBCI,1,0);
    } else if(!strcmp(caseName,"gps_skip")) {
        gpu.acpi.dsm[ACPI_DSM_FUNCTION_GPS_2X].suppFuncStatus=DSM_FUNC_STATUS_SUCCESS;
        _acpiDsmSupportedFuncCacheInit(&gpu);EXPECT(gpu.acpi.dsm[ACPI_DSM_FUNCTION_GPS].suppFuncStatus==DSM_FUNC_STATUS_FAILED);
        wrapperReturned();readGood(0xfffU&~(1U<<ACPI_DSM_FUNCTION_GPS_2X)&~(1U<<ACPI_DSM_FUNCTION_GPS),10,0);
    } else if(!strcmp(caseName,"raw_facades")) {
        NvU32 x=0xaabbccddU,n=4,handles=~0U;NvU16 sn=4;
        nv_acpi_methods_init(&handles);EXPECT(handles==0&&unavailableCalls==0);nv_acpi_methods_uninit();
        EXPECT(nv_acpi_d3cold_dsm_for_upstream_port(NULL,NULL,1,0,&x)==NV_ERR_NOT_SUPPORTED);
        EXPECT(nv_acpi_ddc_method(NULL,&x,&n,NV_FALSE)==NV_ERR_NOT_SUPPORTED);
        EXPECT(nv_acpi_dod_method(NULL,&x,&n)==NV_ERR_NOT_SUPPORTED);
        EXPECT(nv_acpi_dsm_method(NULL,NULL,1,NV_FALSE,0,&x,4,&n,&x,&sn)==NV_ERR_NOT_SUPPORTED);
        EXPECT(nv_acpi_get_powersource(&x)==NV_ERR_NOT_SUPPORTED);
        EXPECT(nv_acpi_mux_method(NULL,&x,0,"_DSM")==NV_ERR_NOT_SUPPORTED);
        EXPECT(x==0xaabbccddU&&n==4&&sn==4&&unavailableCalls==6&&first()==NV_ERR_NOT_SUPPORTED);
    } else if(!strcmp(caseName,"direct_probe")) {
        NvU32 x=0xaabbccddU;NvU16 n=4;
        EXPECT(osCallACPI_DSM(&gpu,ACPI_DSM_FUNCTION_NBSI,0,&x,&n)==NV_ERR_NOT_SUPPORTED);
        EXPECT(osDsmCalls==1&&unavailableCalls==1&&first()==NV_ERR_NOT_SUPPORTED&&x==0xaabbccddU);
        wrapperReturned();readRefused(&nvIdentity);
    } else if(!strcmp(caseName,"fallback_nonzero")) {
        NvU32 x=0;NvU16 n=4;
        gpu.acpi.dsm[0].suppFuncStatus=DSM_FUNC_STATUS_SUCCESS;gpu.acpi.dsm[0].suppFuncsLen=1;gpu.acpi.dsm[0].suppFuncs[0]=2;
        EXPECT(osCallACPI_DSM(&gpu,ACPI_DSM_FUNCTION_NBSI,1,&x,&n)==NV_ERR_NOT_SUPPORTED);
        EXPECT(osDsmCalls==1&&unavailableCalls==1);wrapperReturned();readRefused(&nvIdentity);
    } else if(!strcmp(caseName,"arg3_retry")||!strcmp(caseName,"profile_enabled")||!strcmp(caseName,"profile_version")) {
        if(!strcmp(caseName,"arg3_retry")){record.control=NV_ERR_NOT_SUPPORTED;retryInvalidArgument=NV_TRUE;}
        _acpiDsmSupportedFuncCacheInit(&gpu);
        EXPECT(osDsmCalls>0);
        if(retryInvalidArgument) { EXPECT(unavailableCalls==0); EXPECT(gpu.acpi.dsm[0].bArg3isInteger==NV_TRUE); }
        else EXPECT(unavailableCalls>0);
        wrapperReturned();readRefused(&nvIdentity);
    } else if(!strcmp(caseName,"pending_existing")) {
        EXPECT(s540OptionalAcpiCommitAbsent(&nvIdentity,S540_OPTIONAL_ACPI_DSM_SUPPORT,0)==NV_OK);
        refuseAtCheck=cancellationChecks+2U;
        EXPECT(s540OptionalAcpiCommitAbsent(&nvIdentity,S540_OPTIONAL_ACPI_DOD,0)!=NV_OK);
        wrapperReturned();readRefused(&nvIdentity);
    } else if(!strcmp(caseName,"stale_commit")) {
        EXPECT(s540OptionalAcpiCommitAbsent(&nvIdentity,S540_OPTIONAL_ACPI_DSM_SUPPORT,0)==NV_OK);
        ++record.generation;++globalEpoch.generation;
        EXPECT(s540OptionalAcpiCommitAbsent(&nvIdentity,S540_OPTIONAL_ACPI_DOD,0)!=NV_OK);
        wrapperReturned();readRefused(&nvIdentity);
    } else if(!strcmp(caseName,"reserve_failure")||!strcmp(caseName,"reserve_generation")) {
        if(!strcmp(caseName,"reserve_failure"))refuseAtCheck=2U;else changeGenerationAtCheck=2U;
        EXPECT(s540OptionalAcpiCommitAbsent(&nvIdentity,S540_OPTIONAL_ACPI_DOD,0)!=NV_OK);
        wrapperReturned();readRefused(&nvIdentity);
    } else if(!strncmp(caseName,"log_",4)) {
        if(strcmp(caseName,"log_unavailable"))acpiDsmInit(&gpu);wrapperReturned();
        if(!strcmp(caseName,"log_sticky"))sticky(NV_ERR_NOT_SUPPORTED);
        if(!strcmp(caseName,"log_foreign"))++actualThread;
        s540LogOptionalAcpiAbsence(&contextFixture);EXPECT(logCalls==1);
        if(!strcmp(caseName,"log_unavailable")||!strcmp(caseName,"log_foreign"))EXPECT(strstr(logged,"available=0")!=NULL);
        else {EXPECT(strstr(logged,"available=1")&&strstr(logged,"dsmAbsentMask=0xfff")&&strstr(logged,"dsmQueries=12")&&strstr(logged,"dodQueries=1"));EXPECT(strstr(logged,"amlExecuted=0 hardwareAbsenceClaimed=0")!=NULL);}
    } else if(!strcmp(caseName,"get_null")) {
        EXPECT(s540OptionalAcpiRead(NULL,NULL)==NV_ERR_INVALID_ARGUMENT);
    } else if(!strcmp(caseName,"get_unpublished")) {wrapperReturned();readRefused(&nvIdentity);
    } else if(!strncmp(caseName,"get_",4)) {
        EXPECT(s540OptionalAcpiCommitAbsent(&nvIdentity,S540_OPTIONAL_ACPI_DOD,0)==NV_OK);wrapperReturned();
        const char *which=caseName+4;
        if(!strcmp(which,"sticky")){sticky(NV_ERR_NOT_SUPPORTED);readGood(0,0,1);}
        else if(!strcmp(which,"inflight")){record.originalInFlight=1U;readRefused(&nvIdentity);}
        else if(!strcmp(which,"no_exit")){record.originalExitReady=0;readRefused(&nvIdentity);}
        else if(!strcmp(which,"not_returned")){record.originalReturned=0;readRefused(&nvIdentity);}
        else if(!strcmp(which,"stale")){++record.generation;++globalEpoch.generation;readRefused(&nvIdentity);}
        else {invalidate(which);readRefused(gpu.pOsGpuInfo);}
    } else {
        NvU64 generation=~0ULL;invalidate(caseName);
        EXPECT(s540FirstTxnOptionalNvlinkActive(gpu.pOsGpuInfo,&generation)!=NV_OK);EXPECT(generation==0);
        EXPECT(s540OptionalAcpiCommitAbsent(gpu.pOsGpuInfo,S540_OPTIONAL_ACPI_DOD,0)!=NV_OK);
        _acpiDsmSupportedFuncCacheInit(&gpu);EXPECT(osDsmCalls>0&&unavailableCalls>0);wrapperReturned();readRefused(&nvIdentity);
    }
    EXPECT(slot.checks==31U&&slot.operationAborts==7U&&slot.cleanupExpirations==5U);
    printf("{\"status\":\"passed\",\"case\":\"%s\",\"checks\":%u}\n",caseName,checks);return 0;
}
