// SPDX-License-Identifier: MIT
#include "original_status_edges_fixture.hpp"
#include "original_status_edges_actual_bodies.inc"
namespace {
unsigned checks, failures;
void expect(bool value, const char *reason) {
    ++checks;
    if (!value) { ++failures; std::fprintf(stderr, "Original status edge: %s\n", reason); }
}
}
int main(int argc, char **argv) {
    const bool baseline = argc == 2 && std::strcmp(argv[1], "--baseline") == 0;
    OBJGPU gpu; KernelFalcon falcon;
    f = {}; f.preWait = NV_ERR_OPERATION_ABORTED;
    expect(kflcnReset_TU102(&gpu, &falcon) == NV_ERR_OPERATION_ABORTED && !f.resetCalls && !f.waitCalls,
        "pre-reset cancellation preserves first failure before hardware reset");
    f = {}; f.resetHw = NV_ERR_OPERATING_SYSTEM;
    expect(kflcnReset_TU102(&gpu, &falcon) == NV_ERR_OPERATING_SYSTEM,
        "hardware-reset status cannot be overwritten by a successful wait");
    expect(f.resetCalls == 1 && !f.waitCalls && !f.switches && !f.writes,
        "failed reset cannot switch processor or publish reset completion");
    f = {}; f.resetHw = NV_ERR_GPU_IN_FULLCHIP_RESET;
    expect(kflcnReset_TU102(&gpu, &falcon) == NV_ERR_GPU_IN_FULLCHIP_RESET && !f.waitCalls,
        "reset-in-progress stays incomplete even when a later fixture wait would succeed");
    f = {}; f.resetWait = NV_ERR_TIMEOUT;
    expect(kflcnReset_TU102(&gpu, &falcon) == NV_ERR_TIMEOUT && !f.switches && !f.writes,
        "reset completion timeout remains statusful");
    f = {}; f.resetWait = NV_ERR_GPU_IN_FULLCHIP_RESET;
    expect(kflcnReset_TU102(&gpu, &falcon) == NV_ERR_GPU_IN_FULLCHIP_RESET && !f.switches,
        "original reset-completion in-progress result is preserved");
    f = {};
    expect(kflcnReset_TU102(&gpu, &falcon) == NV_OK && f.preCalls == 1 && f.resetCalls == 1 &&
        f.waitCalls == 1 && f.switches == 1 && f.writes == 1,
        "healthy original reset performs every stage exactly once");

    OS_GPU_INFO minor = 42;
    OS_RM_CAPS *caps = &f.caps;
    f = {}; nvidia_caps_root = nullptr;
    expect(osRmCapRegisterGpu(&minor, &caps) == NV_OK,
        "official unsupported caps-root branch keeps successful return");
    expect(!f.getters && !f.allocations && !f.directories && !f.unregisters && caps == &f.caps,
        "null caps root never evaluates Linux minor getter or touches caller output");
    f = {}; nvidia_caps_root = &rootCap; caps = &f.caps;
    expect(osRmCapRegisterGpu(&minor, &caps) == NV_ERR_INVALID_ARGUMENT && f.getters == 1 && !f.allocations,
        "real caps root preserves getter ordering before original argument refusal");
    f = {}; caps = nullptr; f.allocation = NV_ERR_NO_MEMORY;
    expect(osRmCapRegisterGpu(&minor, &caps) == NV_ERR_NO_MEMORY && f.getters == 1 && !caps,
        "real caps allocation failure preserves status and caller ownership");
    expect(f.getterOrder == 1 && f.allocationOrder == 2 && !f.directories,
        "non-null root preserves exact getter-before-allocation order");
    f = {}; caps = nullptr; f.directoryFailure = 1;
    expect(osRmCapRegisterGpu(&minor, &caps) == NV_ERR_OPERATING_SYSTEM && !caps && f.getters == 1 &&
        f.directories == 1 && f.unregisters == 1,
        "GPU directory failure preserves original unregister path");
    f = {}; caps = nullptr; f.directoryFailure = 2;
    expect(osRmCapRegisterGpu(&minor, &caps) == NV_ERR_OPERATING_SYSTEM && !caps && f.getters == 1 &&
        f.directories == 2 && f.unregisters == 1,
        "MIG directory failure preserves original unregister path");
    f = {}; caps = nullptr;
    expect(osRmCapRegisterGpu(&minor, &caps) == NV_OK && caps == &f.caps && f.getters == 1 &&
        f.directories == 2 && !f.unregisters,
        "real caps root invokes getter once and retains successful original registration");
    expect(std::strcmp(f.gpuName, "gpu42") == 0 && std::strcmp(f.migName, "mig") == 0 &&
        caps->caps[0] == &gpuCap && caps->caps[1] == &migCap,
        "real root preserves exact directory names and resulting ownership");
    std::printf("{\"format\":1,\"component\":\"original-status-edges-prospective\","
        "\"checks\":%u,\"failed_assertions\":%u,\"baseline\":%s,\"actual_original_bodies\":2,"
        "\"stage_fixtures\":true,\"abi_validation\":false,\"hardware_execution\":false,"
        "\"original_entry_admission\":false}\n", checks, failures, baseline ? "true" : "false");
    return baseline ? (failures ? 0 : 1) : (failures ? 1 : 0);
}
