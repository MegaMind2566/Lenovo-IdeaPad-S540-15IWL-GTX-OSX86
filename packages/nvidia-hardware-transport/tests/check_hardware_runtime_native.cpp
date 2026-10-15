// SPDX-License-Identifier: MIT
// The exact aggregate entry point used by the probe, with native backends.
#include "../src/S540NvidiaHardwareRuntime.hpp"
#include "../src/S540NvidiaDma.hpp"
#include "../../nvidia-caller-integration/src/S540NvidiaReserve.hpp"
#include "../../nvidia-caller-integration/src/S540NvidiaMutex.hpp"
#include "../../nvidia-nvport-lifecycle/src/S540NvidiaSpinlock.hpp"
#include "../../nvidia-nvport-runtime/upstream/nvport_runtime.h"
#include <cstdio>

int main()
{
    const auto integrated = S540NvidiaHardwareRuntime::checkIntegrated(nullptr);
    const auto &r = integrated.preparation;
    const auto &v7 = integrated.v7;
    const auto &foundations = v7.v6.v5.foundations;
    const bool previous = v7.acquired && v7.v6.acquired && v7.v6.v5.acquired &&
        foundations.passed() && v7.v6.v5.callers.passed() &&
        v7.v6.lifecycle.passed() && v7.support.passed();
    const bool reserveCold = !S540NvidiaReserve::ready() &&
        S540NvidiaReserve::liveSlots() == 0;
    const bool coreCold = s540NvportRuntimeIsCold() == NV_TRUE;
    const bool objects = S540NvidiaMutex::liveObjects() == 0 &&
        S540NvidiaSpinlock::liveObjects() == 0 &&
        S540NvidiaDma::nativeLiveResources() == 0 &&
        S540NvidiaDma::nativeIllegalOperations() == 0;
    const bool passed = integrated.acquired && previous && r.passed() &&
        reserveCold && coreCold && objects;
    std::printf("{\"format\":1,\"component\":\"nvidia-hardware-runtime\","
        "\"entrypoint\":\"S540NvidiaHardwareRuntime::checkIntegrated\","
        "\"status\":\"%s\",\"checks\":%u,\"failures\":%u,"
        "\"foundation_checks\":%u,\"caller_checks\":%u,"
        "\"lifecycle_checks\":%u,\"support_checks\":%u,"
        "\"previous_blocks_passed\":%s,\"acquired\":%s,"
        "\"host_dma\":%s,\"pci_read_adapter\":%s,"
        "\"interrupt_inventory\":%s,\"firmware_parser\":%s,"
        "\"firmware_rpc\":%s,\"cleanup\":%s,"
        "\"dma_mode\":\"%s\",\"dma_reason\":\"%s\","
        "\"dma_bytes\":%llu,\"dma_segments\":%u,"
        "\"pci_reason\":\"%s\",\"pci_capabilities\":%u,"
        "\"msi_vectors\":%u,\"msix_vectors\":%u,"
        "\"msi_observed_enabled\":%s,\"msix_observed_enabled\":%s,"
        "\"reserve_cold_after\":%s,\"core_cold_after\":%s,"
        "\"os_objects_released\":%s,\"device_dma_verified\":false,"
        "\"firmware_loaded\":false,\"firmware_image_verified\":false,"
        "\"interrupts_enabled\":false,\"gpu_initialized\":false,"
        "\"rm_initialized\":false,\"execution\":\"native-user-space\","
        "\"kernel_runtime\":\"not_tested\",\"gpu_access\":false}\n",
        passed ? "passed" : "failed", r.checks, r.failures,
        foundations.checks, v7.v6.v5.callers.checks, v7.v6.lifecycle.checks,
        v7.support.checks, previous ? "true" : "false",
        integrated.acquired ? "true" : "false", r.hostDma ? "true" : "false",
        r.pciReadAdapter ? "true" : "false", r.interruptInventory ? "true" : "false",
        r.firmwareParser ? "true" : "false", r.firmwareRpc ? "true" : "false",
        r.cleanup ? "true" : "false", r.dmaMode, r.dmaReason,
        static_cast<unsigned long long>(r.dmaBytes), r.dmaSegments,
        r.pciReason, r.pciCapabilities, r.msiVectors, r.msixVectors,
        r.msiObservedEnabled ? "true" : "false", r.msixObservedEnabled ? "true" : "false",
        reserveCold ? "true" : "false", coreCold ? "true" : "false",
        objects ? "true" : "false");
    return passed ? 0 : 1;
}
