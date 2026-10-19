// SPDX-License-Identifier: MIT
// Stage fixtures for extracted, unmodified-or-patched original function bodies.
// These types do not attest the NVIDIA ABI or execute hardware operations.
#pragma once
#include "../../nvidia-os-adapter/upstream/include/nvtypes.h"
#include "../../nvidia-os-adapter/upstream/include/nvstatus.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>

#define RMCFG_FEATURE_GSPRM_BULLSEYE 0
#define NV_PRINTF(...) ((void)0)
#define NV_ASSERT(...) ((void)0)
#define NV_ASSERT_OK(...) ((void)(__VA_ARGS__))
#define NV_ASSERT_FAILED(...) ((void)0)
#define DBG_BREAKPOINT() ((void)0)
#define NV_ASSERT_OR_RETURN(c, e) do { if (!(c)) return (e); } while (0)
#define NV_ASSERT_OK_OR_RETURN(e) do { NV_STATUS s = (e); if (s != NV_OK) return s; } while (0)
#define NV_CHECK_OK(v, l, e) do { (v) = (e); } while (0)
#define staticCast(p, t) static_cast<t *>(p)
#define IS_GSP_CLIENT(p) ((p)->gspClient)
#define GPU_GET_KERNEL_GSP(p) (&(p)->gsp)
#define GPU_GET_KERNEL_SEC2(p) (&(p)->sec2)
#define API_GPU_IN_RESET_SANITY_CHECK(p) ((p)->resetting)
#define IS_GPU_GC6_STATE_ENTERING(p) ((p)->gc6)
#define IS_VGPU_GSP_PLUGIN_OFFLOAD_ENABLED(p) ((p)->vgpu)
#define IS_VIRTUAL_WITH_FULL_SRIOV(p) ((p)->sriov)
#define IS_FMODEL(p) ((p)->fmodel)
#define classId(c) 0
#define objDynamicCastById(p, c) ((void)(c), (p))
#define NVBIT(v) (1U << (v))
#define NV_RM_RPC_SAVE_HIBERNATION_DATA(p, s) do { (void)(p); (s) = f.hibernate; } while (0)
#define gpuStateUnload gpuStateUnload_IMPL
#define kgspUnloadRm kgspUnloadRm_IMPL
#define kgspTeardown_HAL kgspTeardown_TU102
#define kgspExecuteBooterUnloadIfNeeded_HAL kgspExecuteBooterUnloadIfNeeded_TU102

enum : NvU32 {
    KGSP_UNLOAD_MODE_NORMAL = 0, KGSP_UNLOAD_MODE_GC6_ENTER = 1,
    GMCAPI_GSP_SUSPEND_FLAGS_PM_TRANSITION = 1U << 0,
    GMCAPI_GSP_SUSPEND_FLAGS_GC6_ENTERING = 1U << 1,
    GMCAPI_GSP_SUSPEND_FLAGS_FAST = 1U << 2,
    GMCAPI_GSP_SUSPEND_FLAGS_FORCE = 1U << 3,
    GMCAPI_GSP_SUSPEND_FLAGS_HIBERNATE = 1U << 4,
    GPU_STATE_FLAGS_FAST_UNLOAD = 1U << 0,
    GPU_STATE_FLAGS_FORCE_GSP_UNLOAD = 1U << 1,
    GPU_STATE_FLAGS_PRESERVING = 1U << 2,
    NV2080_CTRL_GPU_SET_POWER_STATE_GPU_LEVEL_0 = 0,
    NV2080_CTRL_GPU_SET_POWER_STATE_GPU_LEVEL_7 = 7,
    NV_REG_STR_RM_GSP_PRESERVE_UNLOAD_LOGS_DISABLE = 0,
    NV_REG_STR_RM_GSP_PRESERVE_UNLOAD_LOGS_ENABLE_NO_WRAP = 1,
    NV_REG_STR_RM_GSP_PRESERVE_UNLOAD_LOGS_ENABLE_WRAP = 2,
    GMCAPI_CMD_GSP_SUSPEND = 1,
    ENGSTATE_STATE_PRE_UNLOAD = 1, ENGSTATE_STATE_UNLOAD = 2,
    ENGSTATE_STATE_POST_UNLOAD = 3, ENGSTATE_STATE_DESTROY = 4,
    PDB_PROP_GPU_STATE_INITIALIZED = 1,
    KERNEL_WATCHDOG = 2, KERNEL_WATCHDOG_OBJECT_ID = 3,
    RMAPI_GPU_LOCK_INTERNAL = 4, NV01_NULL_OBJECT = 0
};
using KernelGspUnloadMode = NvU32;
using ENGDESCRIPTOR = NvU32;
struct KernelFalcon {};
struct KernelSec2 : KernelFalcon {};
struct KernelGsp : KernelFalcon {
    bool bGspRmForceUnloaded = false, bGspRmUnloaded = false;
    NvU32 preserveLogs = 1;
    int logDecode = 0;
    void *pFwsecUcode = nullptr, *pBooterUnloadUcode = reinterpret_cast<void *>(1);
};
struct KernelGspPreparedFwsecCmd { int placeholder; };
struct GmcApiGspSuspendParams { NvU64 flags; };
struct ENGSTATE_TRANSITION_DATA { int placeholder; };
struct OBJENGSTATE { unsigned id; };
struct GpuArch { bool bGpuArchIsZeroFb = false; };
struct OBJGPU {
    KernelGsp gsp;
    KernelSec2 sec2;
    bool gspClient = true, resetting = false, gc6 = false, vgpu = false;
    bool sriov = false, fmodel = false, bStateUnloading = false, bStateLoaded = true;
    bool bFullyConstructed = true, initialized = true;
    NvU32 gpuInstance = 0, hInternalWatchdogClient = 0;
    NvU32 hInternalWatchdogDevice = 0, hInternalWatchdogSubdevice = 0;
    void *pKernelWatchdog = nullptr, *boardInfo = reinterpret_cast<void *>(2);
    void *pGpuFabricProbeInfoKernel = nullptr;
    void *pUserRegisterAccessMap = reinterpret_cast<void *>(3);
    void *pUnrestrictedRegisterAccessMap = reinterpret_cast<void *>(4);
    NvU32 userRegisterAccessMapSize = 64;
    GpuArch arch;
    GpuArch *pGpuArch = &arch;
    OBJENGSTATE engines[3] = {{0}, {1}, {2}};
    void setProperty(OBJGPU *, NvU32, NvBool v) { initialized = v; }
};
struct Fixture {
    NV_STATUS rpc = NV_OK, suspend = NV_OK, reset = NV_OK, secReset = NV_OK;
    NV_STATUS prep = NV_OK, fwsec = NV_OK, booter = NV_OK;
    NV_STATUS pre[3] = {}, unload[3] = {}, post[3] = {};
    NV_STATUS p2p = NV_OK, hibernate = NV_OK;
    bool wprUp = true;
    unsigned rpcCalls = 0, suspendCalls = 0, resetCalls = 0, secResetCalls = 0;
    unsigned prepCalls = 0, fwsecCalls = 0, booterCalls = 0, heartbeatStops = 0;
    unsigned logs = 0, preservedLogs = 0, resetTimeouts = 0, delays = 0;
    unsigned preCalls = 0, unloadCalls = 0, postCalls = 0, destroyCalls = 0;
    unsigned internalFrees = 0, falconFrees = 0, videoFrees = 0, hostFrees = 0;
    unsigned sharedDestroys = 0, sriovStops = 0;
} f;

inline NV_STATUS gmcapiCommand(OBJGPU *, NvU32, void *, NvU32, void *, void *) { ++f.rpcCalls; return f.rpc; }
inline bool gpuIsCCFeatureEnabled(OBJGPU *) { return false; }
inline void kgspCheckGspRmCcCleanup_HAL(OBJGPU *, KernelGsp *) { std::abort(); }
inline NV_STATUS kgspWaitForProcessorSuspend_HAL(OBJGPU *, KernelGsp *, NvBool) { ++f.suspendCalls; return f.suspend; }
inline void _kgspHeartbeatDisable(OBJGPU *, KernelGsp *) { ++f.heartbeatStops; }
inline void kgspDumpGspLogs(KernelGsp *, bool) { ++f.logs; }
inline void libosPreserveLogs(int *, bool, bool) { ++f.preservedLogs; }
inline bool gpuIsSriovEnabled(OBJGPU *p) { return p->sriov; }
inline void osDelay(NvU32) { ++f.delays; }
inline NV_STATUS threadStateResetTimeout(OBJGPU *) { ++f.resetTimeouts; return NV_OK; }
inline NV_STATUS kflcnReset_HAL(OBJGPU *p, KernelFalcon *target) {
    if (target == static_cast<KernelFalcon *>(&p->sec2)) { ++f.secResetCalls; return f.secReset; }
    ++f.resetCalls; return f.reset;
}
inline NV_STATUS kgspPrepareForFwsecSb_HAL(OBJGPU *, KernelGsp *, void *, KernelGspPreparedFwsecCmd *) { ++f.prepCalls; return f.prep; }
inline NV_STATUS kgspExecuteFwsec_HAL(OBJGPU *, KernelGsp *, KernelGspPreparedFwsecCmd *) { ++f.fwsecCalls; return f.fwsec; }
inline NvU64 _kgspGetBooterUnloadArgs(KernelGsp *, KernelGspUnloadMode) { return 0; }
inline bool kgspIsWpr2Up_HAL(OBJGPU *, KernelGsp *) { return f.wprUp; }
inline NV_STATUS s_executeBooterUcode_TU102(OBJGPU *p, KernelGsp *, void *, KernelFalcon *, NvU32, NvU32) {
    ++f.booterCalls;
    if (f.booter == NV_OK) f.wprUp = p->gc6;
    return f.booter;
}

inline NV_STATUS osGetPerformanceCounter(NvU64 *p) { *p = 1; return NV_OK; }
inline bool gpumgrGetBcEnabledStatus(OBJGPU *) { return false; }
inline bool hypervisorIsVgxHyper() { return false; }
inline void rmapiControlCacheFreeNonPersistentCacheForGpu(NvU32) {}
inline void gpuFabricProbeStop(void *) {}
inline void portMemFree(void *) { ++f.hostFrees; }
inline ENGDESCRIPTOR *gpuGetUnloadEngineDescriptors(OBJGPU *) { static ENGDESCRIPTOR d[] = {0, 1, 2}; return d; }
inline NvU32 gpuGetNumEngDescriptors(OBJGPU *) { return 3; }
inline ENGDESCRIPTOR *gpuGetDestroyEngineDescriptors(OBJGPU *p) { return gpuGetUnloadEngineDescriptors(p); }
inline OBJENGSTATE *gpuGetEngstate(OBJGPU *p, ENGDESCRIPTOR d) { return &p->engines[d]; }
inline void engstateLogStateTransitionPre(OBJENGSTATE *, NvU32, ENGSTATE_TRANSITION_DATA *) {}
inline void engstateLogStateTransitionPost(OBJENGSTATE *, NvU32, ENGSTATE_TRANSITION_DATA *) {}
inline NV_STATUS engstateStatePreUnload(OBJGPU *, OBJENGSTATE *p, NvU32) { ++f.preCalls; return f.pre[p->id]; }
inline NV_STATUS engstateStateUnload(OBJGPU *, OBJENGSTATE *p, NvU32) { ++f.unloadCalls; return f.unload[p->id]; }
inline NV_STATUS engstateStatePostUnload(OBJGPU *, OBJENGSTATE *p, NvU32) { ++f.postCalls; return f.post[p->id]; }
inline void engstateStateDestroy(OBJGPU *, OBJENGSTATE *) { ++f.destroyCalls; }
template <typename... T> void _gpuStatePreUnloadEngineFailureStore(T...) {}
template <typename... T> void _gpuStatePreUnloadUnknownFailureStore(T...) {}
template <typename... T> void _gpuStateUnloadEngineFailureStore(T...) {}
template <typename... T> void _gpuStateUnloadUnknownFailureStore(T...) {}
template <typename... T> void _gpuStatePostUnloadEngineFailureStore(T...) {}
template <typename... T> void _gpuStatePostUnloadUnknownFailureStore(T...) {}
inline void gpuServiceInterruptsAllGpus(OBJGPU *) {}
inline void rmapiReportLeakedDevices(NvU32) {}
inline void gpuOpEventImportDestruct(OBJGPU *) {}
inline void gpuStopRusdPollingOnUnload(OBJGPU *) {}
inline void gpuFreeVideoLogging(OBJGPU *) { ++f.videoFrees; }
inline void vgpuGspTeardownBuffers(OBJGPU *) {}
inline void gpuDestroyDefaultClientShare_HAL(OBJGPU *) { ++f.sharedDestroys; }
inline void gpuDeinitSriov_HAL(OBJGPU *) { ++f.sriovStops; }
inline NV_STATUS _gpuRemoveP2pCapsFromPeerGpus(OBJGPU *) { return f.p2p; }
inline void rmapiControlCacheFreeAllCacheForGpu(NvU32) {}
inline void videoRemoveAllBindpointsForGpu(OBJGPU *) {}
inline bool gpuIsClassSupported(OBJGPU *, NvU32) { return false; }
struct RM_API { void (*Free)(RM_API *, NvU32, NvU32); };
inline RM_API *rmapiGetInterface(NvU32) { return nullptr; }
inline void rmapiutilFreeClientAndDeviceHandles(RM_API *, NvU32 *, NvU32 *, NvU32 *) {}
inline void gpuStateInitStartedRetract_HAL(OBJGPU *) {}
inline void _gpuFreeInternalObjects(OBJGPU *) { ++f.internalFrees; }
inline void gpuDestroyGenericKernelFalconList(OBJGPU *) { ++f.falconFrees; }
inline void gpuDestroyKernelVideoEngineList(OBJGPU *) { ++f.videoFrees; }
inline void gpuDeinitOptimusSettings(OBJGPU *) {}

NV_STATUS kgspExecuteBooterUnloadIfNeeded_TU102(OBJGPU *, KernelGsp *, NvU64);
NV_STATUS kgspTeardown_TU102(OBJGPU *, KernelGsp *, KernelGspUnloadMode);
NV_STATUS kgspUnloadRm_IMPL(OBJGPU *, KernelGsp *, KernelGspUnloadMode, NvU32);
NV_STATUS gpuStateUnload_IMPL(OBJGPU *, NvU32);
