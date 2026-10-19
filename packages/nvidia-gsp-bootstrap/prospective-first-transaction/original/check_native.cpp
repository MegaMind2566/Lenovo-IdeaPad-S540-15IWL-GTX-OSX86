// SPDX-License-Identifier: MIT
#include "control_types.h"
#include "../../../nvidia-global-rm/src/S540NvidiaGlobalRm.h"
#include "../../../nvidia-global-rm-crypto/src/S540NvidiaGlobalCrypto.h"
#include <cstdio>
extern "C" NV_STATUS s540Global_os_get_page(NvU64);
extern "C" void s540DeviceMemoryResetStatistics(void);
static unsigned checks, failures;
static void expect(bool value, const char *why) {
    ++checks; if (!value) { ++failures; std::fprintf(stderr, "Original first transaction: %s\n", why); }
}
int main() {
    S540NvidiaGlobalRmPlatformFacts facts = {};
    facts.format = 1; facts.known = S540_GLOBAL_FACT_ALL; facts.cpuCount = 1;
    facts.cpuFrequencyHz = 1000000000ULL; facts.osMajor = 26;
    facts.osVersion = "explicit native control"; facts.osDate = "2026-10-19";
    expect(s540GlobalRmHostInitialize(&facts) == NV_OK, "actual lifetime host counter owner initializes");
    expect(s540OriginalControlInitialize() == NV_OK, "real native RW lock and GPU semaphore allocate");
    for (NvU32 which = 0; which < 5; ++which) {
        S540OriginalControlResult r = {};
        s540OriginalControlWrapper(which, &r);
        const unsigned tokens = which == 3 ? 0U : 1U;
        const NV_STATUS first = which == 0 || which == 4 ? NV_STATUS(NV_ERR_TIMEOUT) :
            which == 1 ? NV_STATUS(NV_OK) : which == 2 ? NV_STATUS(NV_ERR_NOT_SUPPORTED) : NV_STATUS(NV_ERR_NOT_READY);
        expect(r.apiAcquired == tokens && r.apiReleased == tokens, "actual original API lock bodies relinquish exactly acquired native token");
        expect(r.gpuAcquired == tokens && r.gpuReleased == tokens, "explicit GPU init endpoint relinquishes its real native semaphore");
        expect(r.deferredCalls == (which == 4 ? 2U : unsigned(which == 0)), "failed init records deferred intent and does not run hidden cleanup");
        expect(!r.cleanupCalls && r.ownershipPreserved && !r.identityErrors, "failed/retained paths preserve exact original GPU and owner flags");
        expect(r.exitAfterActualTokens && r.exitReadyCalls == 1 && !r.runtimeDepth && !r.threadDepth,
            "source exit-ready executes after actual API/GPU token release and thread/runtime boundary cleanup");
        expect(r.firstStatus == first, "failure or release-time refusal remains sticky before later destruction");
        expect(which != 0 || (r.apiHeldAtDeferred && r.gpuHeldAtDeferred && r.firmwareRetained),
            "deferred helper retains exact firmware handles while original owner tokens are held");
        expect(r.wrapperReturned && r.wrapperStatus == (which == 1 ? NV_STATUS(NV_OK) : NV_STATUS(NV_ERR_NOT_READY)),
            "actual wrapper returns before outer handoff and release-time refusal invalidates apparent success");
        expect(r.guardStatus != NV_OK && s540OriginalControlRealTokensAvailable(),
            "unsealed/refused transaction cannot enter destructive phase and both real tokens are available afterward");
    }
    expect(s540OriginalControlFullLocksStatus() == NV_ERR_NOT_SUPPORTED,
        "generic full lock-capability predicate refuses the unresolved RM semaphore service");
    for (NvU32 which = 0; which < 3; ++which) {
        S540OriginalControlResult r = {};
        s540OriginalControlNvoc(which, &r);
        expect(r.guardStatus == (which == 0 ? NV_STATUS(NV_ERR_NOT_READY) : which == 1 ? NV_STATUS(NV_ERR_NOT_SUPPORTED) : NV_STATUS(NV_OK)),
            "actual checked generic deletion preserves pre-destructor or post-destructor exact refusal");
        expect(r.originalDestructors == unsigned(which != 0) && r.originalFrees == unsigned(which == 2),
            "generic NVOC cannot free storage after either guard refuses");
        expect(!r.identityErrors && (which == 2 ? r.originalUnlinks == 1 : r.ownershipPreserved && !r.originalUnlinks),
            "actual NVOC unlink preserves parent ownership on refusal");
    }
    for (NvU32 which = 3; which < 6; ++which) {
        S540OriginalControlResult r = {};
        s540OriginalControlCtor(which, &r);
        expect(r.guardStatus == (which == 3 ? NV_STATUS(NV_ERR_TIMEOUT) : which == 4 ? NV_STATUS(NV_ERR_NOT_READY) : NV_STATUS(NV_OK)),
            "actual selected timer constructor preserves failure and refuses destructive rollback");
        expect(!r.constructorBaseDestructors && !r.originalFrees && !r.identityErrors,
            "unknown constructor owner remains retained before base destructor/free");
    }
    S540FirstTxnServiceCounters before = {}, after = {};
    s540OriginalControlCurrentCounters(&before);
    expect(before.hostInitialized && !before.hostUnavailable && !before.memoryUnavailableEver && !before.cryptoUnavailable,
        "strong original bridge reads actual initially clean lifetime counters");
    s540GlobalRmRecordUnavailable(501);
    s540OriginalControlCurrentCounters(&after);
    expect(after.hostUnavailable == before.hostUnavailable + 1, "actual central unavailable refusal survives the strong probe");
    expect(!s540Global_libspdm_check_crypto_backend(), "actual unsupported cryptographic operation refuses");
    s540OriginalControlCurrentCounters(&after);
    expect(after.cryptoUnavailable == 1 && (after.cryptoMaskLow || after.cryptoMaskHigh) && !after.cryptoOverflow,
        "actual cryptographic lifetime counter and masks are captured before destruction");
    expect(!s540Global_libspdm_sha384_hash_all(nullptr, 0, nullptr), "actual high-mask crypto operation refuses");
    s540OriginalControlCurrentCounters(&after);
    expect(after.cryptoUnavailable == 2 && after.cryptoMaskLow && after.cryptoMaskHigh,
        "strong probe retains both actual cryptographic symbol mask halves");
    expect(s540Global_os_get_page(0) == NV_ERR_NOT_SUPPORTED, "actual unsupported memory operation refuses");
    s540OriginalControlCurrentCounters(&after);
    expect(after.memoryUnavailableEver == 1 && !after.memoryViolationsEver,
        "strong probe reads actual lifetime memory refusal count");
    s540DeviceMemoryResetStatistics();
    s540OriginalControlCurrentCounters(&after);
    expect(after.memoryUnavailableEver == 1 && after.cryptoUnavailable == 2 && after.hostUnavailable == 1,
        "ordinary telemetry reset cannot erase any lifetime refusal evidence");
    expect(s540OriginalControlCurrentGuard() == NV_ERR_NOT_SUPPORTED,
        "nonzero actual central/memory/crypto counters refuse the predestruction boundary");
    s540OriginalControlShutdown();
    expect(s540GlobalRmHostShutdown(), "all native test lock storage is released without resetting lifetime refusal evidence");
    std::printf("{\"format\":1,\"component\":\"nvidia-first-transaction-original-bodies\","
        "\"checks\":%u,\"failures\":%u,\"status\":\"%s\",\"actual_original_wrapper\":true,"
        "\"actual_original_api_lock_bodies\":4,\"real_native_lock_tokens\":true,"
        "\"actual_nvoc_bodies\":4,\"actual_timer_ctor_body\":true,"
        "\"original_gpu_init_endpoint_fixture\":true,\"first_transaction_record_endpoint_fixture\":true,"
        "\"actual_service_counter_probes\":true,\"execution\":\"native-user-space\","
        "\"full_lock_capability_refused\":true,"
        "\"kernel_execution\":\"not_tested\",\"gpu_access\":false,\"original_entry_admission\":false}\n",
        checks, failures, failures ? "failed" : "passed");
}
