/* SPDX-License-Identifier: MIT */
#include "S540PciTopology.hpp"

namespace S540NvidiaPciTopology {
namespace {
NvU64 lastGeneration;
static_assert(__atomic_always_lock_free(sizeof(NvU64), nullptr),
              "Topology generation must not import a runtime lock");
bool issueGeneration(NvU64 &out) {
    NvU64 value = __atomic_load_n(&lastGeneration, __ATOMIC_RELAXED);
    while (value < (~NvU64(0) >> 5)) {
        if (__atomic_compare_exchange_n(&lastGeneration, &value, value + 1U,
            false, __ATOMIC_RELAXED, __ATOMIC_RELAXED)) {
            out = value + 1U; return true;
        }
    }
    return false;
}
bool validIdentity(NvU32 identity) {
    const NvU16 vendor = NvU16(identity), device = NvU16(identity >> 16);
    return vendor != 0U && vendor != 0xffffU && device != 0xffffU;
}
NV_STATUS critical(const State &state, const Candidate &candidate,
    NvU32 &identity, NvU32 &revision, NvU32 &header, NvU32 &buses, bool host) {
    NV_STATUS status = state.reader.read(state.reader.context, candidate, 0U, 4U, identity);
    if (status != NV_OK) return status;
    status = state.reader.read(state.reader.context, candidate, 8U, 4U, revision);
    if (status != NV_OK) return status;
    status = state.reader.read(state.reader.context, candidate, 12U, 4U, header);
    if (status != NV_OK) return status;
    if (!validIdentity(identity) || revision == ~0U) return NV_ERR_INVALID_DATA;
    const NvU32 classSubclass = (revision >> 16U) & 0xffffU;
    header = (header >> 16U) & 0x7fU;
    if (host) {
        /* This selected Intel S540 profile never enters chipset write quirks
         * for another vendor. CS_UNKNOWN remains a valid generic selection.
         */
        if (classSubclass != 0x0600U || header != 0U || NvU16(identity) != 0x8086U)
            return NV_ERR_NOT_SUPPORTED;
        buses = 0U;
    } else {
        if (classSubclass != 0x0604U || header != 1U || candidate.rootConfig)
            return NV_ERR_NOT_SUPPORTED;
        status = state.reader.read(state.reader.context, candidate, 24U, 4U, buses);
        if (status != NV_OK) return status;
        buses &= 0x00ffffffU;
        const NvU8 primary = NvU8(buses), secondary = NvU8(buses >> 8U);
        const NvU8 subordinate = NvU8(buses >> 16U);
        if (primary != candidate.bus || secondary <= primary || secondary > subordinate ||
            state.gpuBus < secondary || state.gpuBus > subordinate)
            return NV_ERR_INVALID_DATA;
    }
    return NV_OK;
}
NV_STATUS revalidate(const State &state, const Record &record, bool host) {
    NvU32 identity = 0U, revision = 0U, header = 0U, buses = 0U;
    const NV_STATUS status = critical(state, record.candidate, identity, revision, header, buses, host);
    if (status != NV_OK) return status;
    return identity == record.identity && revision == record.classRevision &&
        header == record.headerType && buses == record.buses ? NV_OK : NV_ERR_INVALID_STATE;
}
bool sameAddress(const Candidate &a, const Candidate &b) {
    return a.segment == b.segment && a.bus == b.bus && a.device == b.device && a.function == b.function;
}
bool matches(const Record &record, const S540PciTopologyReference &reference) {
    return !reference.reserved && reference.handle == record.handle &&
        reference.segment == record.candidate.segment && reference.bus == record.candidate.bus &&
        reference.device == record.candidate.device && reference.function == record.candidate.function &&
        reference.vendor == NvU16(record.identity) && reference.deviceId == NvU16(record.identity >> 16U);
}
}

bool ready(const State &state, const void *owner) {
    return owner && state.owner == owner && state.prepared && state.generation &&
        state.count >= 2U && state.count <= kMaximumRecords;
}
void clear(State &state) { state = State{}; }
NV_STATUS prepare(State &state, const void *owner, NvU32 segment, NvU8 gpuBus,
    const Reader &reader, const Candidate *candidates, NvU32 count) {
    if (state.owner || state.prepared) return NV_ERR_STATE_IN_USE;
    if (!owner || !reader.context || !reader.read || !candidates || segment > 0xffffU ||
        count < 2U || count > kMaximumRecords || !gpuBus) return NV_ERR_INVALID_ARGUMENT;
    state.owner = owner; state.segment = segment; state.gpuBus = gpuBus; state.reader = reader;
    NV_STATUS failure = NV_OK;
    NvU8 downstreamBus = gpuBus;
    for (NvU32 i = 0U; i != count; ++i) {
        const Candidate &candidate = candidates[i];
        const bool host = i + 1U == count;
        if (!candidate.resource || candidate.segment != segment || candidate.device >= 32U ||
            candidate.function >= 8U || (candidate.rootConfig &&
            (!host || segment || candidate.bus || candidate.device || candidate.function))) {
            failure = NV_ERR_INVALID_ARGUMENT; break;
        }
        for (NvU32 previous = 0U; previous != i; ++previous) {
            if (sameAddress(candidate, candidates[previous]) || candidate.resource == candidates[previous].resource) {
                failure = NV_ERR_INVALID_DATA; break;
            }
        }
        if (failure != NV_OK) break;
        Record &record = state.records[i];
        record.candidate = candidate;
        failure = critical(state, candidate, record.identity, record.classRevision,
            record.headerType, record.buses, host);
        if (failure != NV_OK) break;
        if (host) {
            if (candidate.bus != downstreamBus) { failure = NV_ERR_INVALID_DATA; break; }
        } else {
            if (NvU8(record.buses >> 8U) != downstreamBus) { failure = NV_ERR_INVALID_DATA; break; }
            downstreamBus = candidate.bus;
        }
        ++state.count;
    }
    if (failure == NV_OK && !issueGeneration(state.generation)) failure = NV_ERR_INSUFFICIENT_RESOURCES;
    if (failure != NV_OK) { clear(state); return failure; }
    for (NvU32 i = 0U; i != count; ++i)
        state.records[i].handle = reinterpret_cast<void *>(static_cast<NvUPtr>((state.generation << 4U) | (i + 1U)));
    state.prepared = true;
    return NV_OK;
}
void *find(State &state, const void *owner, NvU32 segment, NvU8 bus, NvU8 device,
    NvU8 function, NvU16 *vendor, NvU16 *deviceId) {
    if (!ready(state, owner)) return nullptr;
    /* Match the fixed table before reading any PCI configuration register.
     * Original exhaustive DBDF enumeration therefore has a bounded cheap miss.
     */
    for (NvU32 i = 0U; i != state.count; ++i) {
        const Record &record = state.records[i];
        if (record.candidate.segment != segment || record.candidate.bus != bus ||
            record.candidate.device != device || record.candidate.function != function) continue;
        if (revalidate(state, record, i + 1U == state.count) != NV_OK) return nullptr;
        if (vendor) *vendor = NvU16(record.identity);
        if (deviceId) *deviceId = NvU16(record.identity >> 16U);
        return record.handle;
    }
    return nullptr;
}
NV_STATUS read(State &state, const void *owner, void *handle, NvU32 offset,
    NvU32 width, NvU32 &value) {
    if (!ready(state, owner) || !handle) return NV_ERR_INVALID_STATE;
    if ((width != 1U && width != 2U && width != 4U) || offset >= 4096U ||
        width > 4096U - offset || (offset & (width - 1U))) return NV_ERR_INVALID_ARGUMENT;
    for (NvU32 i = 0U; i != state.count; ++i) {
        const Record &record = state.records[i];
        if (record.handle != handle) continue;
        if (record.candidate.rootConfig && (offset >= 256U || width > 256U - offset))
            return NV_ERR_NOT_SUPPORTED;
        NV_STATUS status = revalidate(state, record, i + 1U == state.count);
        if (status != NV_OK) return status;
        NvU32 captured = 0U;
        status = state.reader.read(state.reader.context, record.candidate, offset, width, captured);
        if (status != NV_OK) return status;
        if ((width == 1U && captured > 0xffU) || (width == 2U && captured > 0xffffU))
            return NV_ERR_INVALID_DATA;
        status = revalidate(state, record, i + 1U == state.count);
        if (status != NV_OK) return status;
        value = captured; return NV_OK;
    }
    return NV_ERR_OBJECT_NOT_FOUND;
}
NV_STATUS validate(State &state, const void *owner, const S540PciTopologyGspFacts &facts) {
    if (!ready(state, owner)) return NV_ERR_NOT_READY;
    if (facts.format != 1U || facts.bytes != sizeof(facts)) return NV_ERR_INVALID_ARGUMENT;
    if (!matches(state.records[state.count - 1U], facts.fhb) || !matches(state.records[0], facts.upstream))
        return NV_ERR_INVALID_DATA;
    bool chipset = false;
    for (NvU32 i = 0U; i != state.count; ++i) {
        if (matches(state.records[i], facts.chipset)) chipset = true;
        const NV_STATUS status = revalidate(state, state.records[i], i + 1U == state.count);
        if (status != NV_OK) return status;
    }
    return chipset ? NV_OK : NV_ERR_INVALID_DATA;
}
}
