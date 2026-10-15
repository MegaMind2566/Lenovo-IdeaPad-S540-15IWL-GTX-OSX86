// SPDX-License-Identifier: MIT
#include "../src/S540NvidiaGspFirmware.hpp"
#include <atomic>
#include <cstdio>
#include <fstream>
#include <thread>
#include <vector>

namespace {
using namespace S540NvidiaGspFirmware;
unsigned checks;
unsigned failures;
constexpr NvU64 ownerThread = 0x101;
constexpr NvU64 wrongThread = 0x202;

void expect(bool condition)
{
    ++checks;
    if (!condition)
        ++failures;
}

bool readImage(const char *path, std::vector<NvU8> &out)
{
    std::ifstream file(path, std::ios::binary | std::ios::ate);
    if (!file)
        return false;
    const auto length = file.tellg();
    if (length <= 0 || length > 128 * 1024 * 1024)
        return false;
    out.resize(static_cast<size_t>(length));
    file.seekg(0);
    return bool(file.read(reinterpret_cast<char *>(out.data()), length));
}

void rejectedGet(Store &store, const void *owner, NvU64 thread,
                 NvU32 type, NvU32 family)
{
    const auto before = store.snapshot();
    const void *bytes = &store;
    NvU32 size = 0xA5A5;
    expect(store.get(owner, thread, type, family, &bytes, &size) == nullptr);
    expect(bytes == &store && size == 0xA5A5);
    const auto after = store.snapshot();
    expect(after.rejected == before.rejected + 1);
    expect(after.acquisitions == before.acquisitions &&
           after.releases == before.releases &&
           after.liveLeases == before.liveLeases);
}

void checkBadInitialization(std::vector<NvU8> &gsp,
                            std::vector<NvU8> &ucodes)
{
    unsigned owner = 1;
    Store missingOwner;
    expect(missingOwner.initialize(nullptr, ownerThread, gsp.data(), gsp.size(),
                                  ucodes.data(), ucodes.size()) == NV_ERR_INVALID_ARGUMENT);
    expect(missingOwner.initialize(&owner, 0, gsp.data(), gsp.size(),
                                  ucodes.data(), ucodes.size()) == NV_ERR_INVALID_ARGUMENT);
    auto state = missingOwner.snapshot();
    expect(!state.active && !state.verified && state.rejected == 2 &&
           state.liveLeases == 0 && !state.cleanShutdown);

    Store wrongBytes;
    expect(wrongBytes.initialize(&owner, ownerThread, nullptr, gsp.size(),
                                ucodes.data(), ucodes.size()) == NV_ERR_INVALID_DATA);
    expect(wrongBytes.initialize(&owner, ownerThread, gsp.data(), gsp.size(),
                                nullptr, ucodes.size()) == NV_ERR_INVALID_DATA);
    expect(wrongBytes.initialize(&owner, ownerThread, gsp.data(), gsp.size() - 1,
                                ucodes.data(), ucodes.size()) == NV_ERR_INVALID_DATA);
    expect(wrongBytes.initialize(&owner, ownerThread, gsp.data(), gsp.size(),
                                ucodes.data(), ucodes.size() - 1) == NV_ERR_INVALID_DATA);
    expect(wrongBytes.initialize(&owner, ownerThread, ucodes.data(), ucodes.size(),
                                gsp.data(), gsp.size()) == NV_ERR_INVALID_DATA);
    expect(wrongBytes.initialize(&owner, ownerThread, gsp.data(), ~NvU64(0),
                                ucodes.data(), ucodes.size()) == NV_ERR_INVALID_DATA);

    gsp[0] ^= 1;
    expect(wrongBytes.initialize(&owner, ownerThread, gsp.data(), gsp.size(),
                                ucodes.data(), ucodes.size()) == NV_ERR_INVALID_DATA);
    gsp[0] ^= 1;
    ucodes.back() ^= 1;
    expect(wrongBytes.initialize(&owner, ownerThread, gsp.data(), gsp.size(),
                                ucodes.data(), ucodes.size()) == NV_ERR_INVALID_DATA);
    ucodes.back() ^= 1;
    state = wrongBytes.snapshot();
    expect(!state.active && !state.verified && state.rejected == 8 &&
           state.acquisitions == 0 && state.releases == 0 &&
           state.liveLeases == 0 && !state.overflow);
    rejectedGet(wrongBytes, &owner, ownerThread, kGsp, kTu117Family);
    expect(!wrongBytes.shutdown(ownerThread));
    expect(!wrongBytes.put(ownerThread, nullptr));
    // Failed validation publishes no store state; a corrected pair can start.
    expect(wrongBytes.initialize(&owner, ownerThread, gsp.data(), gsp.size(),
                                ucodes.data(), ucodes.size()) == NV_OK);
    expect(wrongBytes.snapshot().rejected == 11);
    expect(wrongBytes.shutdown(ownerThread));
}

void checkMainLifecycle(const std::vector<NvU8> &gsp,
                        const std::vector<NvU8> &ucodes)
{
    unsigned owner = 1, foreignOwner = 2;
    Store store;
    auto state = store.snapshot();
    expect(!state.active && !state.verified && !state.deliveredGsp &&
           !state.deliveredUcodes && !state.cleanShutdown && !state.overflow);
    expect(state.acquisitions == 0 && state.releases == 0 &&
           state.rejected == 0 && state.liveLeases == 0);
    expect(!store.ownedBy(ownerThread) && !store.ownedBy(0));
    rejectedGet(store, &owner, ownerThread, kGsp, kTu117Family);
    expect(store.initialize(&owner, ownerThread, gsp.data(), gsp.size(),
                            ucodes.data(), ucodes.size()) == NV_OK);
    state = store.snapshot();
    expect(state.verified && state.active && !state.deliveredGsp &&
           !state.deliveredUcodes && state.rejected == 1);
    expect(store.ownedBy(ownerThread) && !store.ownedBy(wrongThread));
    expect(store.initialize(&owner, ownerThread, gsp.data(), gsp.size(),
                            ucodes.data(), ucodes.size()) == NV_ERR_STATE_IN_USE);

    rejectedGet(store, &foreignOwner, ownerThread, kGsp, kTu117Family);
    rejectedGet(store, nullptr, ownerThread, kGsp, kTu117Family);
    rejectedGet(store, &owner, wrongThread, kGsp, kTu117Family);
    rejectedGet(store, &owner, 0, kGsp, kTu117Family);
    rejectedGet(store, &owner, ownerThread, kGsp, 1);
    rejectedGet(store, &owner, ownerThread, kGsp, ~NvU32(0));
    rejectedGet(store, &owner, ownerThread, 1, kTu117Family);
    rejectedGet(store, &owner, ownerThread, 3, kTu117Family);
    rejectedGet(store, &owner, ownerThread, ~NvU32(0), kTu117Family);
    const void *bytes = &store;
    NvU32 size = 0x1234;
    expect(store.get(&owner, ownerThread, kGsp, kTu117Family,
                     nullptr, &size) == nullptr && size == 0x1234);
    expect(store.get(&owner, ownerThread, kGsp, kTu117Family,
                     &bytes, nullptr) == nullptr && bytes == &store);

    const void *first = store.get(&owner, ownerThread, kGsp, kTu117Family,
                                  &bytes, &size);
    expect(first && bytes == gsp.data() && size == gsp.size());
    const void *second = store.get(&owner, ownerThread, kGsp, kTu117Family,
                                   &bytes, &size);
    expect(second && second != first && bytes == gsp.data() && size == gsp.size());
    const void *ucodesHandle = store.get(&owner, ownerThread, kUcodes, kTu117Family,
                                        &bytes, &size);
    expect(ucodesHandle && ucodesHandle != first && ucodesHandle != second &&
           bytes == ucodes.data() && size == ucodes.size());
    state = store.snapshot();
    expect(state.acquisitions == 3 && state.liveLeases == 3 &&
           state.deliveredGsp && state.deliveredUcodes);
    expect(!store.shutdown(ownerThread));
    expect(!store.shutdown(wrongThread));
    expect(!store.put(wrongThread, first));
    expect(!store.put(ownerThread, &foreignOwner));
    expect(store.snapshot().liveLeases == 3);
    expect(store.put(ownerThread, nullptr));
    expect(store.snapshot().releases == 0 && store.snapshot().liveLeases == 3);
    expect(store.put(ownerThread, first));
    expect(!store.put(ownerThread, first));
    expect(store.put(ownerThread, second));
    expect(store.put(ownerThread, ucodesHandle));
    state = store.snapshot();
    expect(state.acquisitions == state.releases && state.liveLeases == 0);

    const void *handles[kMaximumLeases]{};
    bool uniqueHandles = true;
    for (NvU32 i = 0; i < kMaximumLeases; ++i) {
        const NvU32 type = i & 1 ? kUcodes : kGsp;
        handles[i] = store.get(&owner, ownerThread, type, kTu117Family, &bytes, &size);
        expect(handles[i] != nullptr);
        expect(bytes == (type == kGsp ? gsp.data() : ucodes.data()) &&
               size == (type == kGsp ? gsp.size() : ucodes.size()));
        for (NvU32 j = 0; j < i; ++j)
            if (handles[i] == handles[j])
                uniqueHandles = false;
    }
    expect(uniqueHandles);
    expect(store.snapshot().liveLeases == kMaximumLeases);
    rejectedGet(store, &owner, ownerThread, kGsp, kTu117Family);
    expect(!store.shutdown(ownerThread));
    expect(store.snapshot().active && store.snapshot().liveLeases == kMaximumLeases);
    for (const void *handle : handles)
        expect(store.put(ownerThread, handle));
    expect(store.snapshot().liveLeases == 0);

    const void *replacement = store.get(&owner, ownerThread, kGsp, kTu117Family,
                                        &bytes, &size);
    expect(replacement && replacement != handles[0] && replacement != first);
    expect(!store.put(ownerThread, handles[0]));
    expect(store.snapshot().liveLeases == 1);
    expect(store.put(ownerThread, replacement));
    expect(store.shutdown(ownerThread));
    state = store.snapshot();
    expect(state.verified && state.deliveredGsp && state.deliveredUcodes &&
           !state.active && state.cleanShutdown && state.liveLeases == 0 &&
           state.acquisitions == 68 && state.releases == 68 && !state.overflow);
    expect(!store.ownedBy(ownerThread));
    rejectedGet(store, &owner, ownerThread, kGsp, kTu117Family);
    expect(!store.put(ownerThread, replacement));
    expect(!store.shutdown(ownerThread));
    expect(store.initialize(&owner, ownerThread, gsp.data(), gsp.size(),
                            ucodes.data(), ucodes.size()) == NV_ERR_INVALID_ARGUMENT);
    expect(store.snapshot().cleanShutdown);

    // Tokens from a completed store cannot free a later store's live lease.
    Store later;
    expect(later.initialize(&owner, ownerThread, gsp.data(), gsp.size(),
                            ucodes.data(), ucodes.size()) == NV_OK);
    const void *laterHandle = later.get(&owner, ownerThread, kGsp, kTu117Family,
                                        &bytes, &size);
    expect(laterHandle && laterHandle != first && laterHandle != replacement);
    expect(!later.put(ownerThread, first));
    expect(later.snapshot().liveLeases == 1);
    expect(later.put(ownerThread, laterHandle));
    expect(later.shutdown(ownerThread));
}

void checkConcurrentRejections(const std::vector<NvU8> &gsp,
                               const std::vector<NvU8> &ucodes)
{
    unsigned owner = 1;
    Store store;
    expect(store.initialize(&owner, ownerThread, gsp.data(), gsp.size(),
                            ucodes.data(), ucodes.size()) == NV_OK);
    constexpr unsigned workers = 4, iterations = 128;
    std::atomic<unsigned> errors{0};
    std::thread threads[workers];
    for (auto &thread : threads)
        thread = std::thread([&] {
            for (unsigned i = 0; i < iterations; ++i) {
                const void *bytes = &store;
                NvU32 size = 0x6161;
                if (store.get(&owner, wrongThread, kGsp, kTu117Family,
                              &bytes, &size) || bytes != &store || size != 0x6161)
                    ++errors;
                if (store.put(wrongThread, nullptr))
                    ++errors;
                if (store.shutdown(wrongThread))
                    ++errors;
            }
        });
    for (auto &thread : threads)
        thread.join();
    const auto state = store.snapshot();
    expect(errors.load() == 0);
    expect(state.rejected == workers * iterations * 3);
    expect(state.active && state.verified && !state.deliveredGsp &&
           !state.deliveredUcodes && state.liveLeases == 0 &&
           state.acquisitions == 0 && state.releases == 0 && !state.overflow);
    expect(store.shutdown(ownerThread));
}
}

int main(int argc, char **argv)
{
    if (argc != 3) {
        std::fprintf(stderr, "Usage: check_firmware_store_native GSP UCODES\n");
        return 2;
    }
    std::vector<NvU8> gsp, ucodes;
    if (!readImage(argv[1], gsp) || !readImage(argv[2], ucodes)) {
        std::fprintf(stderr, "Cannot read the approved firmware pair\n");
        return 2;
    }
    expect(gsp.size() == 22901632 && ucodes.size() == 8837632);
    checkBadInitialization(gsp, ucodes);
    checkMainLifecycle(gsp, ucodes);
    checkConcurrentRejections(gsp, ucodes);
    std::printf("{\"format\":1,\"component\":\"nvidia-gsp-firmware-store\","
        "\"status\":\"%s\",\"checks\":%u,\"failures\":%u,"
        "\"maximum_live_leases\":%u,\"concurrent_rejections\":1536,"
        "\"real_pair_verified\":%s,\"firmware_delivered_cpu\":%s,"
        "\"firmware_loaded\":false,\"gpu_initialized\":false,"
        "\"execution\":\"native-user-space\",\"kernel_execution\":\"not_tested\","
        "\"bridge_execution\":\"not_tested\","
        "\"gpu_access\":false}\n",
        failures ? "failed" : "passed", checks, failures, kMaximumLeases,
        failures ? "false" : "true", failures ? "false" : "true");
    return failures ? 1 : 0;
}
