// SPDX-License-Identifier: MIT
#include "S540NvidiaGspFirmware.hpp"
#include "S540NvidiaGspFirmwareBridge.h"
#include "../../nvidia-firmware-assets/src/S540NvidiaFirmwareAssets.hpp"
#include "../../nvidia-darwin-services/src/S540NvidiaDarwinServices.h"

namespace S540NvidiaGspFirmware {
namespace {
Store *bound;
NvU64 generation;
const void *nextToken(NvU32 slot) {
    NvU64 prior = __atomic_load_n(&generation, __ATOMIC_RELAXED);
    do {
        // Leave the upper byte clear: tokens fit a 64-bit pointer and no wrap
        // or recycled generation can resurrect a lease from an earlier owner.
        if (prior >= (NvU64(1) << 48) - 1) return nullptr;
    } while (!__atomic_compare_exchange_n(&generation, &prior, prior + 1, false,
                                          __ATOMIC_RELAXED, __ATOMIC_RELAXED));
    return reinterpret_cast<const void *>(NvUPtr(((prior + 1) << 8) | (slot + 1)));
}
void increment(NvU32 &value, bool &overflow) {
    if (value == ~NvU32(0)) __atomic_store_n(&overflow, true, __ATOMIC_RELAXED);
    else ++value;
}
}
Store::Store() : leases_{}, owner_(nullptr), gsp_(nullptr), ucodes_(nullptr),
    thread_(0), gspSize_(0), ucodesSize_(0), state_{} {}
void Store::reject() {
    NvU32 prior = __atomic_load_n(&state_.rejected, __ATOMIC_RELAXED);
    while (prior != ~NvU32(0) && !__atomic_compare_exchange_n(&state_.rejected,
           &prior, prior + 1, false, __ATOMIC_RELAXED, __ATOMIC_RELAXED)) {}
    if (prior == ~NvU32(0)) __atomic_store_n(&state_.overflow, true, __ATOMIC_RELAXED);
}
bool Store::ownedBy(NvU64 thread) const {
    return thread != 0 && thread == thread_ && state_.active;
}
NV_STATUS Store::initialize(const void *ownerState, NvU64 ownerThread,
                            const void *gsp, NvU64 gspBytes,
                            const void *ucodes, NvU64 ucodesBytes) {
    if (state_.active || state_.liveLeases) { reject(); return NV_ERR_STATE_IN_USE; }
    // A store is single-use; audit evidence and rejected calls cannot be reset.
    if (state_.verified || !ownerState || !ownerThread) {
        reject(); return NV_ERR_INVALID_ARGUMENT;
    }
    auto checked = S540NvidiaFirmwareAssets::verifyPair(gsp, gspBytes, ucodes, ucodesBytes);
    if (!checked.passed() || gspBytes > ~NvU32(0) || ucodesBytes > ~NvU32(0)) {
        reject(); return NV_ERR_INVALID_DATA;
    }
    owner_ = ownerState; thread_ = ownerThread; gsp_ = gsp; ucodes_ = ucodes;
    gspSize_ = NvU32(gspBytes); ucodesSize_ = NvU32(ucodesBytes);
    state_.verified = state_.active = true;
    return NV_OK;
}
const void *Store::get(const void *ownerState, NvU64 thread, NvU32 type, NvU32 family,
                       const void **bytes, NvU32 *size) {
    if (!ownedBy(thread) || ownerState != owner_ || !bytes || !size ||
        family != kTu117Family || (type != kGsp && type != kUcodes)) {
        reject(); return nullptr;
    }
    NvU32 index = 0;
    while (index != kMaximumLeases && leases_[index].token) ++index;
    if (index == kMaximumLeases) { reject(); return nullptr; }
    const void *token = nextToken(index);
    if (!token) { reject(); return nullptr; }
    leases_[index] = Lease{token, type};
    ++state_.liveLeases;
    increment(state_.acquisitions, state_.overflow);
    if (type == kGsp) {
        *bytes = gsp_; *size = gspSize_; state_.deliveredGsp = true;
    } else {
        *bytes = ucodes_; *size = ucodesSize_; state_.deliveredUcodes = true;
    }
    return token;
}
bool Store::put(NvU64 thread, const void *handle) {
    if (!ownedBy(thread)) { reject(); return false; }
    // Linux release_firmware(NULL) is a valid optional cleanup operation.
    if (!handle) return true;
    for (NvU32 i = 0; i != kMaximumLeases; ++i) {
        if (leases_[i].token != handle) continue;
        leases_[i] = Lease{}; --state_.liveLeases;
        increment(state_.releases, state_.overflow);
        return true;
    }
    reject(); return false;
}
bool Store::shutdown(NvU64 thread) {
    if (!ownedBy(thread) || state_.liveLeases) { reject(); return false; }
    state_.active = false; state_.cleanShutdown = true;
    owner_ = gsp_ = ucodes_ = nullptr; thread_ = 0; gspSize_ = ucodesSize_ = 0;
    return true;
}
Snapshot Store::snapshot() const {
    Snapshot result{};
    result.acquisitions = state_.acquisitions;
    result.releases = state_.releases;
    result.liveLeases = state_.liveLeases;
    result.verified = state_.verified;
    result.deliveredGsp = state_.deliveredGsp;
    result.deliveredUcodes = state_.deliveredUcodes;
    result.active = state_.active;
    result.cleanShutdown = state_.cleanShutdown;
    result.rejected = __atomic_load_n(&state_.rejected, __ATOMIC_RELAXED);
    result.overflow = __atomic_load_n(&state_.overflow, __ATOMIC_RELAXED);
    return result;
}
NV_STATUS bind(Store *store) {
    NvU64 thread = 0;
    if (!store || s540Darwin_os_get_current_thread(&thread) != NV_OK ||
        !store->ownedBy(thread)) return NV_ERR_INVALID_STATE;
    Store *expected = nullptr;
    return __atomic_compare_exchange_n(&bound, &expected, store, false,
           __ATOMIC_RELEASE, __ATOMIC_RELAXED) ? NV_OK : NV_ERR_STATE_IN_USE;
}
NV_STATUS unbind(Store *store) {
    // Shutdown and caller-owned callback quiescence precede unbinding. No
    // successful callback may run after Store::shutdown or during destruction.
    if (!store || store->snapshot().active || store->snapshot().liveLeases)
        return NV_ERR_STATE_IN_USE;
    Store *expected = store;
    return __atomic_compare_exchange_n(&bound, &expected, static_cast<Store *>(nullptr),
           false, __ATOMIC_ACQ_REL, __ATOMIC_RELAXED) ? NV_OK : NV_ERR_INVALID_STATE;
}
}
extern "C" const void *s540GspFirmwareAcquire(const void *owner, NvU32 type,
    NvU32 family, const void **bytes, NvU32 *size) {
    auto *store = __atomic_load_n(&S540NvidiaGspFirmware::bound, __ATOMIC_ACQUIRE);
    NvU64 thread = 0;
    if (!store || s540Darwin_os_get_current_thread(&thread) != NV_OK) return nullptr;
    return store->get(owner, thread, type, family, bytes, size);
}
extern "C" void s540GspFirmwareRelease(const void *handle) {
    auto *store = __atomic_load_n(&S540NvidiaGspFirmware::bound, __ATOMIC_ACQUIRE);
    NvU64 thread = 0;
    if (store && s540Darwin_os_get_current_thread(&thread) == NV_OK) store->put(thread, handle);
}
