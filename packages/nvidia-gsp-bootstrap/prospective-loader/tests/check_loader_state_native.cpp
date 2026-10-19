// SPDX-License-Identifier: MIT
#include "../S540ProspectiveLoaderState.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <mutex>
#include <thread>
#include <atomic>
namespace {
unsigned checks = 0;
void expect(bool ok,const char *why) { ++checks; if (!ok) { std::fprintf(stderr,"Loader state: %s\n",why); std::exit(1); } }
S540ProspectiveRequest request(NvU64 generation) {
    return {S540_PROSPECTIVE_PROTOCOL_VERSION,sizeof(S540ProspectiveRequest),generation};
}
bool clean(const S540ProspectiveState &s) {
    return s.snapshot.entryPolicyClosed && !s.snapshot.targetLoaderAdmissionProven &&
        !s.snapshot.originalCalls && !s.snapshot.providerPreparations && !s.snapshot.pmRegistrations;
}
}
int main() {
    S540ProspectiveState state{}; auto command = request(77);
    expect(s540ProspectiveModuleEnter(nullptr) == NV_ERR_INVALID_ARGUMENT,"null module state rejected");
    expect(s540ProspectiveServiceStart(&state,77,NV_TRUE) == NV_ERR_INVALID_STATE,"service cannot precede module callback");
    expect(s540ProspectiveRequestOnce(&state,NV_FALSE,&command) == NV_ERR_INSUFFICIENT_PERMISSIONS,"permission first before partial load");
    expect(s540ProspectiveRequestOnce(&state,NV_TRUE,&command) == NV_ERR_INVALID_STATE,"partial load cannot request entry");
    expect(s540ProspectiveBeginStop(&state) == NV_ERR_INVALID_STATE,"cold stop is not successful initialization");
    expect(s540ProspectiveModuleEnter(&state) == NV_OK,"actual module callback transition");
    expect(state.snapshot.phase == S540_PROSPECTIVE_MODULE_ENTERED && state.snapshot.moduleEntryAccepted && clean(state),"module callback does not prove target loader admission");
    expect(s540ProspectiveModuleEnter(&state) == NV_ERR_STATE_IN_USE,"module callback cannot reset existing epoch");
    expect(s540ProspectiveRequestOnce(&state,NV_TRUE,&command) == NV_ERR_INVALID_STATE,"module callback alone cannot activate");
    expect(s540ProspectiveServiceStart(&state,0,NV_TRUE) == NV_ERR_INVALID_ARGUMENT,"registry generation must be actual nonzero identity");
    expect(s540ProspectiveServiceStart(&state,77,NV_FALSE) == NV_ERR_INVALID_ARGUMENT,"foreign provider cannot create control readiness");
    expect(s540ProspectiveServiceStart(&state,77,NV_TRUE) == NV_OK,"IOResources control callback transition");
    expect(state.snapshot.phase == S540_PROSPECTIVE_CONTROL_STARTED && state.snapshot.generation == 77 && clean(state),"control started does not claim loader-return proof");
    expect(s540ProspectiveServiceStart(&state,88,NV_TRUE) == NV_ERR_INVALID_STATE,"duplicate start cannot rotate identity");
    auto before = state.snapshot;
    expect(s540ProspectiveRequestOnce(&state,NV_FALSE,&command) == NV_ERR_INSUFFICIENT_PERMISSIONS,"root-only request denies transferred unprivileged connection");
    expect(!std::memcmp(&before,&state.snapshot,sizeof(before)),"unauthorized request has no state side effect");
    expect(s540ProspectiveRequestOnce(&state,NV_TRUE,nullptr) == NV_ERR_INVALID_ARGUMENT,"null command rejected");
    auto malformed = command; malformed.format = 2;
    expect(s540ProspectiveRequestOnce(&state,NV_TRUE,&malformed) == NV_ERR_INVALID_ARGUMENT,"unknown protocol rejected");
    malformed = command; --malformed.bytes;
    expect(s540ProspectiveRequestOnce(&state,NV_TRUE,&malformed) == NV_ERR_INVALID_ARGUMENT,"partial command rejected");
    malformed = request(0);
    expect(s540ProspectiveRequestOnce(&state,NV_TRUE,&malformed) == NV_ERR_INVALID_ARGUMENT,"zero generation rejected");
    malformed = request(76);
    expect(s540ProspectiveRequestOnce(&state,NV_TRUE,&malformed) == NV_ERR_INVALID_ARGUMENT,"stale epoch rejected");
    expect(!state.snapshot.rootRequestConsumed && !std::memcmp(&before,&state.snapshot,sizeof(before)),"malformed requests cannot consume the only request");
    std::mutex lock; std::atomic<unsigned> blocked{0}, repeated{0}, other{0};
    std::thread threads[8];
    for (auto &thread:threads) thread = std::thread([&]{
        std::lock_guard<std::mutex> held(lock);
        NV_STATUS status=s540ProspectiveRequestOnce(&state,NV_TRUE,&command);
        if (status==NV_ERR_NOT_READY) ++blocked;
        else if (status==NV_ERR_STATE_IN_USE) ++repeated;
        else ++other;
    });
    for (auto &thread:threads) thread.join();
    expect(blocked==1 && repeated==7 && !other,"one serialized concurrent request reaches fixed closed policy");
    expect(state.snapshot.rootRequestConsumed == 1 && state.snapshot.requestsAccepted == 1,"actual one-shot consumption is permanent");
    expect(state.snapshot.phase == S540_PROSPECTIVE_ENTRY_BLOCKED && state.snapshot.lastStatus == NV_ERR_NOT_READY && clean(state),"policy refusal is never successful RM entry");
    expect(s540ProspectiveRequestOnce(&state,NV_TRUE,&command) == NV_ERR_STATE_IN_USE,"repeated root command rejected");
    expect(s540ProspectiveRequestOnce(&state,NV_FALSE,&command) == NV_ERR_INSUFFICIENT_PERMISSIONS,"privilege is rechecked after one-shot consumption");
    expect(s540ProspectiveBeginStop(&state) == NV_OK,"stop closes new calls");
    expect(s540ProspectiveRequestOnce(&state,NV_TRUE,&command) == NV_ERR_INVALID_STATE,"closing owner cannot re-enter");
    expect(s540ProspectiveFinishStop(&state,1,0) == NV_ERR_IN_USE,"actual service owner prevents module stop completion");
    s540ProspectiveServiceGone(&state);
    expect(!state.snapshot.controlServiceStarted && state.snapshot.stopping,"service stop revokes control readiness");
    expect(s540ProspectiveFinishStop(&state,0,1) == NV_ERR_IN_USE,"actual live client prevents module stop completion");
    expect(s540ProspectiveFinishStop(&state,0,0) == NV_OK && state.snapshot.phase == S540_PROSPECTIVE_STOPPED,"stop completes only after both owner counts reach zero");
    expect(s540ProspectiveRequestOnce(&state,NV_TRUE,&command) == NV_ERR_INVALID_STATE,"stopped epoch cannot activate");
    expect(s540ProspectiveModuleEnter(&state) == NV_ERR_STATE_IN_USE && state.snapshot.rootRequestConsumed,"stop never resets consumed epoch");
    expect(s540ProspectiveFinishStop(&state,0,0) == NV_OK,"completed stop is idempotent");
    S540ProspectiveState partial{};
    expect(s540ProspectiveModuleEnter(&partial) == NV_OK,"partial-load fixture starts actual module transition");
    partial.snapshot.moduleEntryAccepted = 0;
    expect(s540ProspectiveServiceStart(&partial,99,NV_TRUE) == NV_ERR_INVALID_STATE,"missing module fact rejects fabricated control start");
    for (unsigned fault=0; fault<4; ++fault) {
        S540ProspectiveState damaged{};
        expect(s540ProspectiveModuleEnter(&damaged)==NV_OK && s540ProspectiveServiceStart(&damaged,77,NV_TRUE)==NV_OK,"fresh canonical fault fixture");
        switch(fault) {
            case 0: damaged.snapshot.targetLoaderAdmissionProven=1; break;
            case 1: damaged.snapshot.originalCalls=1; break;
            case 2: damaged.snapshot.providerPreparations=1; break;
            case 3: damaged.snapshot.entryPolicyClosed=0; break;
        }
        expect(s540ProspectiveRequestOnce(&damaged,NV_TRUE,&command)==NV_ERR_INVALID_STATE && !damaged.snapshot.rootRequestConsumed,"inconsistent alleged proof cannot authorize entry");
    }
    std::printf("{\"format\":1,\"component\":\"nvidia-prospective-loader-state\",\"status\":\"passed\",\"checks\":%u,\"failures\":0,\"execution\":\"native-user-space\",\"kernel_execution\":\"not_tested\",\"gpu_access\":false,\"entry_policy_closed\":true,\"target_loader_admission_proven\":false,\"original_rm_called\":false}\n",checks);
}
