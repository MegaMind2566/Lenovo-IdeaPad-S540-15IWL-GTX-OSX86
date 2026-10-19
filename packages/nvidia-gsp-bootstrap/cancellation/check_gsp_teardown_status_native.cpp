// SPDX-License-Identifier: MIT
#include "gsp_teardown_status_fixture.hpp"
// Generated verbatim from the pinned source after applying only the candidate.
#include "gsp_teardown_actual_bodies.inc"
namespace {
unsigned checks, failures;
void expect(bool value, const char *reason) {
    ++checks;
    if (!value) { ++failures; std::fprintf(stderr, "GSP teardown: %s\n", reason); }
}
void reset(OBJGPU &gpu) { f = Fixture{}; gpu = OBJGPU{}; gpu.pGpuArch = &gpu.arch; }
NV_STATUS unload(OBJGPU &gpu, KernelGspUnloadMode mode = KGSP_UNLOAD_MODE_NORMAL) {
    return kgspUnloadRm_IMPL(&gpu, &gpu.gsp, mode, 0);
}
}
int main(int argc, char **argv) {
    const bool baseline = argc == 2 && std::strcmp(argv[1], "--baseline") == 0;
    OBJGPU gpu;
    reset(gpu);
    expect(unload(gpu) == NV_OK && gpu.gsp.bGspRmUnloaded, "real staged success publishes unload");
    expect(f.rpcCalls == 1 && f.suspendCalls == 1 && f.resetCalls == 1 && f.prepCalls == 1 &&
        f.fwsecCalls == 1 && f.secResetCalls == 1 && f.booterCalls == 1,
        "healthy original path actually runs every hardware boundary");
    expect(f.heartbeatStops == 1 && f.logs == 1 && f.preservedLogs == 1,
        "confirmed suspend retains original logging and heartbeat shutdown");
    expect(unload(gpu) == NV_OK && f.rpcCalls == 1 && f.suspendCalls == 1,
        "completed unload avoids repeated suspend after engine destruction");

    reset(gpu); f.rpc = NV_ERR_OPERATING_SYSTEM; f.suspend = NV_ERR_TIMEOUT;
    expect(unload(gpu) == NV_ERR_OPERATING_SYSTEM, "first RPC failure cannot be overwritten");
    expect(!gpu.gsp.bGspRmUnloaded && !f.suspendCalls && !f.resetCalls && !f.logs,
        "failed RPC preserves state and admits no subsequent teardown");

    reset(gpu); f.suspend = NV_ERR_TIMEOUT;
    expect(unload(gpu) == NV_ERR_TIMEOUT, "processor-suspend error reaches caller");
    expect(!gpu.gsp.bGspRmUnloaded && !f.heartbeatStops && !f.logs && !f.resetCalls,
        "failed suspend cannot claim unloaded or initiate teardown");

    reset(gpu); f.reset = NV_ERR_GPU_IN_FULLCHIP_RESET;
    expect(unload(gpu) == NV_ERR_GPU_IN_FULLCHIP_RESET, "reset-in-progress is preserved as incomplete");
    expect(!gpu.gsp.bGspRmUnloaded && !f.prepCalls && !f.fwsecCalls && !f.booterCalls,
        "failed GSP reset cannot be replaced by later Booter success");

    reset(gpu); f.prep = NV_ERR_NO_MEMORY;
    expect(unload(gpu) == NV_ERR_NO_MEMORY, "FWSEC preparation status reaches caller");
    expect(!gpu.gsp.bGspRmUnloaded && !f.fwsecCalls && !f.booterCalls,
        "FWSEC preparation failure retains subsequent hardware stages");

    reset(gpu); f.fwsec = NV_ERR_OPERATION_ABORTED;
    expect(unload(gpu) == NV_ERR_OPERATION_ABORTED, "FWSEC execution cancellation reaches caller");
    expect(!gpu.gsp.bGspRmUnloaded && !f.secResetCalls && !f.booterCalls,
        "FWSEC cancellation cannot be overwritten by Booter success");

    reset(gpu); f.secReset = NV_ERR_OPERATING_SYSTEM;
    expect(unload(gpu) == NV_ERR_OPERATING_SYSTEM, "Booter SEC2 reset error reaches caller");
    expect(!gpu.gsp.bGspRmUnloaded && !f.booterCalls,
        "failed SEC2 reset cannot start Booter ucode");

    reset(gpu); f.booter = NV_ERR_TIMEOUT;
    expect(unload(gpu) == NV_ERR_TIMEOUT && !gpu.gsp.bGspRmUnloaded,
        "Booter failure cannot publish completed hardware teardown");
    expect(f.heartbeatStops == 1 && f.logs == 1,
        "failed late stage acknowledges earlier actual suspend without claiming full completion");

    reset(gpu); gpu.gsp.bGspRmForceUnloaded = true;
    expect(unload(gpu) == NV_ERR_INVALID_STATE && !gpu.gsp.bGspRmUnloaded && !f.rpcCalls,
        "force-unload flag alone cannot attest previous hardware success");

    reset(gpu); gpu.gc6 = true;
    expect(unload(gpu, KGSP_UNLOAD_MODE_GC6_ENTER) == NV_OK && gpu.gsp.bGspRmUnloaded,
        "original GC6 success remains supported by the staged body");
    expect(!f.resetCalls && !f.prepCalls && !f.fwsecCalls && f.secResetCalls == 1 && f.wprUp,
        "GC6 preserves WPR and skips FWSEC-SB as originally required");

    reset(gpu); f.pre[0] = NV_ERR_OPERATING_SYSTEM;
    expect(gpuStateUnload_IMPL(&gpu, 0) == NV_ERR_OPERATING_SYSTEM,
        "pre-unload engine failure reaches top-level unload");
    expect(f.preCalls == 1 && !f.unloadCalls && !f.postCalls && gpu.bStateLoaded && gpu.bStateUnloading,
        "pre-unload failure retains loaded state and stops later engines");

    reset(gpu); f.unload[1] = NV_ERR_TIMEOUT;
    expect(gpuStateUnload_IMPL(&gpu, 0) == NV_ERR_TIMEOUT,
        "engine unload failure cannot be overwritten by later engine or post stage");
    expect(f.unloadCalls == 2 && !f.postCalls && !f.sharedDestroys && !f.sriovStops && gpu.bStateLoaded,
        "failed unload stops later state destruction and retains loaded indicator");

    reset(gpu); f.post[0] = NV_ERR_OPERATION_ABORTED;
    expect(gpuStateUnload_IMPL(&gpu, 0) == NV_ERR_OPERATION_ABORTED,
        "post-unload cancellation propagates through its original caller");
    expect(f.postCalls == 1 && !f.sharedDestroys && !f.sriovStops && gpu.bStateLoaded,
        "post-unload failure cannot mark state successfully unloaded");

    reset(gpu); gpu.vgpu = true; f.p2p = NV_ERR_OPERATING_SYSTEM;
    expect(gpuStateUnload_IMPL(&gpu, 0) == NV_ERR_OPERATING_SYSTEM && gpu.bStateLoaded,
        "P2P removal error is not hidden by an assertion");

    reset(gpu); f.unload[0] = NV_ERR_TIMEOUT; f.rpc = NV_ERR_OPERATING_SYSTEM;
    expect(gpuEnterShutdown_IMPL(&gpu) == NV_ERR_TIMEOUT && !f.rpcCalls,
        "shutdown entry preserves prior unload error rather than replacing it with GSP status");

    reset(gpu); f.suspend = NV_ERR_TIMEOUT;
    expect(gpuStateDestroy_IMPL(&gpu) == NV_ERR_TIMEOUT,
        "late GSP suspend error reaches state-destroy caller");
    expect(f.destroyCalls == 3,
        "test exposes original void engine-destroy stages that already ran before late GSP failure");
    expect(!f.internalFrees && !f.falconFrees && !f.videoFrees && !f.hostFrees && gpu.bFullyConstructed &&
        gpu.pUserRegisterAccessMap && gpu.pUnrestrictedRegisterAccessMap,
        "late GSP failure retains internal objects, engine lists and register-access maps");
    expect(gpu.initialized, "late GSP failure cannot publish a completed initialized-state transition");

    reset(gpu);
    expect(gpuStateUnload_IMPL(&gpu, 0) == NV_OK && !gpu.bStateLoaded && !gpu.bStateUnloading,
        "healthy original engine unload completes and clears loaded state");
    expect(f.preCalls == 3 && f.unloadCalls == 3 && f.postCalls == 3 && f.sharedDestroys == 1 && f.sriovStops == 1,
        "healthy unload preserves all original stage sequencing");
    expect(gpuStateDestroy_IMPL(&gpu) == NV_OK && !gpu.bFullyConstructed,
        "healthy original destroy still completes through real GSP stages");
    expect(!gpu.initialized, "healthy complete teardown publishes the initialized-state transition");
    expect(f.internalFrees == 1 && f.falconFrees == 1 && f.hostFrees == 3,
        "success releases each final host resource once");

    std::printf("{\"format\":1,\"component\":\"gsp-teardown-status-prospective\","
        "\"checks\":%u,\"failed_assertions\":%u,\"baseline\":%s,"
        "\"actual_original_bodies\":8,\"stage_fixtures\":true,\"abi_validation\":false,"
        "\"hardware_execution\":false,\"void_engine_destroy_gap_closed\":false,"
        "\"original_entry_admission\":false}\n", checks, failures, baseline ? "true" : "false");
    return baseline ? (failures ? 0 : 1) : (failures ? 1 : 0);
}
