// SPDX-License-Identifier: MIT
#include "nv_device_services.h"
#if defined(KERNEL)
#include <machine/machine_routines.h>
#include <libkern/libkern.h>
#else
#include <cstdio>
#include <cstdlib>
#endif
namespace {
using namespace S540NvidiaDeviceTransport;
struct Allocation {
    void *token;
    void *sessionToken;
    void *dmaToken;
    NvU32 pages;
    NvU32 cache;
    NvU32 cpuMappings;
    bool contiguous;
    bool mapped;
    bool freePending;
    bool retired;
    bool dmaRetirement;
};
struct Mapping {
    void *token;
    Allocation *allocation;
    void *address;
};
struct Binding {
    Session *session;
    nv_state_t *state;
    nv_dma_device_t *dma;
    void *pciHandle;
    Allocation allocations[kMaximumAllocations];
    Mapping mappings[64];
};
Binding binding{};
NvU64 abiGeneration = 0;
bool ordinary() {
#if defined(KERNEL)
    return !ml_at_interrupt_context() && ml_get_interrupts_enabled();
#else
    return true;
#endif
}
void *token(bool mapping) {
    if (abiGeneration >= (~NvU64(0) >> 2)) return nullptr;
    return reinterpret_cast<void *>(static_cast<NvUPtr>((++abiGeneration << 1) | (mapping ? 1U : 0U)));
}
bool stateValid(nv_state_t *state) {
    return ordinary() && binding.session && binding.session->active() && state == binding.state;
}
[[noreturn]] void deviceContractViolation(const char *message) {
    // Scalar/void callbacks cannot encode a failed ownership contract as an
    // ordinary default result. Their status-bearing gates must run first.
#if defined(KERNEL)
    panic("NVIDIA device services contract violation: %s", message);
#else
    std::fprintf(stderr, "NVIDIA device services contract violation: %s\n", message);
    std::abort();
#endif
}
Allocation *find(void *value) {
    if (!value) return nullptr;
    for (auto &entry : binding.allocations)
        if (entry.token == value && !entry.retired) return &entry;
    return nullptr;
}
NV_STATUS release(Allocation &entry) {
    bool deferred = false;
    NV_STATUS status = binding.session->releaseRmAllocation(entry.sessionToken, deferred);
    if (status == NV_OK) {
        if (deferred) entry.retired = true;
        else entry = Allocation{};
    }
    return status;
}
}
NV_STATUS S540NvidiaDeviceTransport::bindRmDevice(Session *session, nv_state_t *state,
                                                  nv_dma_device_t *dma) {
    if (!ordinary() || !session || !session->active() || !state || !dma)
        return NV_ERR_INVALID_ARGUMENT;
    if (binding.session) return NV_ERR_STATE_IN_USE;
    NV_STATUS status = session->setRmBinding(true);
    if (status != NV_OK) return status;
    void *handle = session->pciHandle();
    if (!handle) { (void)session->setRmBinding(false); return NV_ERR_INSUFFICIENT_RESOURCES; }
    binding.session = session; binding.state = state; binding.dma = dma;
    binding.pciHandle = handle;
    return NV_OK;
}
NV_STATUS S540NvidiaDeviceTransport::unbindRmDevice(Session *session) {
    if (!ordinary() || !session || binding.session != session) return NV_ERR_INVALID_STATE;
    for (const auto &entry : binding.allocations) if (entry.token) return NV_ERR_IN_USE;
    for (const auto &entry : binding.mappings) if (entry.token) return NV_ERR_IN_USE;
    NV_STATUS status = session->setRmBinding(false);
    if (status != NV_OK) return status;
    binding = Binding{};
    return NV_OK;
}
NV_STATUS S540NvidiaDeviceTransport::drainRmRetirements(Session *session) {
    if (!ordinary() || !session || binding.session != session || !session->active())
        return NV_ERR_INVALID_STATE;
    for (auto &entry : binding.allocations) if (entry.token && (entry.retired || entry.dmaRetirement)) {
        const NV_STATUS status = session->reclaimRmRetirement(entry.sessionToken);
        if (status != NV_OK) return status;
        if (entry.retired) entry = Allocation{};
        else entry.dmaRetirement = false;
    }
    return NV_OK;
}
NV_STATUS S540NvidiaDeviceTransport::queryRmDmaRemap(nv_state_t *state, NvBool &required) {
    if (!stateValid(state)) return NV_ERR_INVALID_STATE;
    return binding.session->requiresDmaRemap(required);
}
extern "C" NvBool NV_API_CALL s540Global_nv_requires_dma_remap(nv_state_t *state) {
    NvBool required;
    if (queryRmDmaRemap(state, required) != NV_OK)
        deviceContractViolation("DMA-remap callback requires an admitted bound policy");
    return required;
}
extern "C" NV_STATUS NV_API_CALL s540Global_nv_get_num_phys_pages(void *allocation, NvU32 *pages) {
    if (!pages) return NV_ERR_INVALID_ARGUMENT;
    if (!ordinary() || !binding.session || !binding.session->active()) return NV_ERR_INVALID_STATE;
    Allocation *entry = find(allocation);
    if (!entry || entry->freePending) return NV_ERR_OBJECT_NOT_FOUND;
    *pages = entry->pages;
    return NV_OK;
}
S540NvidiaDeviceTransport::AbiStatistics S540NvidiaDeviceTransport::abiStatistics() {
    AbiStatistics out{}; out.bound = binding.session != nullptr;
    for (const auto &entry : binding.allocations) if (entry.token) {
        ++out.allocations; if (entry.mapped) ++out.dmaMappings;
        if (entry.retired) ++out.retiredAllocations;
        if (entry.dmaRetirement) ++out.retiredDmaMappings;
    }
    for (const auto &entry : binding.mappings) if (entry.token) ++out.mappings;
    return out;
}
extern "C" NV_STATUS NV_API_CALL s540Global_nv_alloc_pages(nv_state_t *state,
    NvU32 pages, NvU64 pageSize, NvBool contiguous, NvU32 cache, NvBool zeroed,
    NvBool unencrypted, NvS32 node, NvU64 *ptes, void **privateData) {
    if (!stateValid(state)) return NV_ERR_INVALID_STATE;
    if (!ptes || !privateData || !pages || contiguous > 1 || zeroed > 1 || unencrypted > 1)
        return NV_ERR_INVALID_ARGUMENT;
    if (pageSize != kPageBytes || pages > kMaximumPages || cache > 2 || unencrypted || node != -1)
        return NV_ERR_NOT_SUPPORTED;
    Allocation *entry = nullptr;
    for (auto &candidate : binding.allocations) if (!candidate.token) { entry = &candidate; break; }
    if (!entry) return NV_ERR_INSUFFICIENT_RESOURCES;
    void *id = token(false);
    if (!id) return NV_ERR_INSUFFICIENT_RESOURCES;
    void *sessionToken = nullptr;
    NV_STATUS status = binding.session->allocate(pages, ptes, &sessionToken, contiguous != 0, cache);
    if (status != NV_OK) return status;
    entry->token = id; entry->sessionToken = sessionToken;
    entry->pages = pages; entry->cache = cache; entry->contiguous = contiguous != 0;
    *privateData = id;
    return NV_OK;
}
extern "C" NV_STATUS NV_API_CALL s540Global_nv_free_pages(nv_state_t *state,
    NvU32 pages, NvBool contiguous, NvU32 cache, void *privateData) {
    if (!stateValid(state)) return NV_ERR_INVALID_STATE;
    Allocation *entry = find(privateData);
    if (!entry) return NV_ERR_OBJECT_NOT_FOUND;
    if (contiguous > 1 || pages != entry->pages || (contiguous != 0) != entry->contiguous || cache != entry->cache)
        return NV_ERR_INVALID_ARGUMENT;
    if (entry->mapped) return NV_ERR_IN_USE;
    if (entry->freePending) return NV_ERR_INVALID_STATE;
    if (entry->cpuMappings) { entry->freePending = true; return NV_OK; }
    return release(*entry);
}
extern "C" void *NV_API_CALL s540Global_nv_alloc_kernel_mapping(nv_state_t *state,
    void *privateData, NvU64 pageIndex, NvU32 pageOffset, NvU64 size, void **mappingPrivate) {
    if (!stateValid(state) || !mappingPrivate || pageOffset >= kPageBytes || !size)
        return nullptr;
    Allocation *entry = find(privateData);
    if (!entry || entry->freePending || pageIndex >= entry->pages) return nullptr;
    const NvU64 offset = pageIndex * kPageBytes + pageOffset;
    const NvU64 bytes = NvU64(entry->pages) * kPageBytes;
    if (offset > bytes || size > bytes - offset) return nullptr;
    Mapping *mapping = nullptr;
    for (auto &candidate : binding.mappings) if (!candidate.token) { mapping = &candidate; break; }
    if (!mapping) return nullptr;
    void *id = token(true);
    if (!id) return nullptr;
    void *address = nullptr;
    if (binding.session->borrowHost(entry->sessionToken, offset, size, &address) != NV_OK)
        return nullptr;
    mapping->token = id; mapping->allocation = entry; mapping->address = address;
    ++entry->cpuMappings;
    *mappingPrivate = id;
    return address;
}
extern "C" void NV_API_CALL s540Global_nv_free_kernel_mapping(nv_state_t *state,
    void *privateData, void *address, void *mappingPrivate) {
    if (!stateValid(state)) return;
    Allocation *entry = find(privateData);
    if (!entry) return;
    for (auto &mapping : binding.mappings) {
        if (mapping.token == mappingPrivate && mapping.allocation == entry && mapping.address == address) {
            mapping = Mapping{};
            if (entry->cpuMappings) --entry->cpuMappings;
            if (!entry->cpuMappings && entry->freePending && release(*entry) != NV_OK) {
                // nv_free_pages already transferred the caller's ownership.
                // This void callback cannot return a failed completion. Keep
                // the tracked backing for an explicit, status-bearing drain.
                if (binding.session->retainRmAllocation(entry->sessionToken) != NV_OK)
                    deviceContractViolation("void CPU-map release lost its retained allocation owner");
                entry->retired = true;
            }
            return;
        }
    }
}
extern "C" NV_STATUS NV_API_CALL s540Global_nv_dma_map_alloc(nv_dma_device_t *dma,
    NvU64 pages, NvU64 *ptes, NvBool contiguous, NvBool readOnly, void **privateData) {
    if (!ordinary() || !binding.session || dma != binding.dma || !binding.session->active())
        return NV_ERR_INVALID_STATE;
    if (!ptes || !privateData || contiguous > 1 || readOnly > 1) return NV_ERR_INVALID_ARGUMENT;
    Allocation *entry = find(*privateData);
    if (!entry || entry->freePending) return NV_ERR_OBJECT_NOT_FOUND;
    if (pages != entry->pages || (contiguous != 0) != entry->contiguous)
        return NV_ERR_INVALID_ARGUMENT;
    if (readOnly) return NV_ERR_NOT_SUPPORTED;
    if (entry->mapped) return NV_ERR_STATE_IN_USE;
    void *mappingToken = token(true);
    if (!mappingToken) return NV_ERR_INSUFFICIENT_RESOURCES;
    NV_STATUS status = binding.session->mapDma(entry->sessionToken, ptes);
    if (status == NV_OK) {
        entry->mapped = true;
        entry->dmaRetirement = false;
        entry->dmaToken = mappingToken;
        *privateData = mappingToken;
    }
    return status;
}
extern "C" NV_STATUS NV_API_CALL s540Global_nv_dma_unmap_alloc(nv_dma_device_t *dma,
    NvU64 pages, NvU64 *ptes, void **privateData) {
    if (!ordinary() || !binding.session || dma != binding.dma || !binding.session->active())
        return NV_ERR_INVALID_STATE;
    if (!ptes || !privateData) return NV_ERR_INVALID_ARGUMENT;
    Allocation *entry = nullptr;
    for (auto &candidate : binding.allocations)
        if (candidate.mapped && candidate.dmaToken == *privateData) { entry = &candidate; break; }
    if (!entry) return NV_ERR_OBJECT_NOT_FOUND;
    if (pages != entry->pages) return NV_ERR_INVALID_ARGUMENT;
    if (!entry->mapped) return NV_ERR_INVALID_STATE;
    bool deferred = false;
    NV_STATUS status = binding.session->unmapRmDma(entry->sessionToken, ptes, deferred);
    if (status == NV_OK) {
        entry->mapped = false; entry->dmaToken = nullptr;
        entry->dmaRetirement = deferred;
        *privateData = entry->token;
    }
    return status;
}
extern "C" void NV_API_CALL s540Global_nv_set_dma_address_size(nv_state_t *state, NvU32 bits) {
    if (stateValid(state)) (void)binding.session->setDmaAddressSize(bits);
}

S540NvidiaDeviceTransport::Session *S540NvidiaDeviceTransport::boundRmSession() {
    return ordinary() ? binding.session : nullptr;
}
extern "C" NvU64 NV_API_CALL s540Global_nv_get_kern_phys_address(NvU64 host) {
    NvU64 physical = 0;
    if (ordinary() && binding.session)
        (void)binding.session->physicalAddressForHost(host, physical);
    return physical;
}

void *S540NvidiaDeviceTransport::boundPciHandle() {
    return ordinary() && binding.session && binding.session->active() ? binding.pciHandle : nullptr;
}
namespace {
NV_STATUS pciRead(void *handle, NvU32 offset, NvU32 width, NvU32 &value) {
    if (!ordinary() || !binding.session || !handle || handle != binding.pciHandle)
        return NV_ERR_INVALID_STATE;
    return binding.session->readConfig(offset,width,value);
}
NV_STATUS pciWrite(void *handle, NvU32 offset, NvU32 width, NvU32 value) {
    if (!ordinary() || !binding.session || !handle || handle != binding.pciHandle)
        return NV_ERR_INVALID_STATE;
    return binding.session->writeConfig(offset,width,value);
}
}
extern "C" void *NV_API_CALL s540Global_os_pci_init_handle(NvU32 segment,
    NvU8 bus, NvU8 device, NvU8 function, NvU16 *vendor, NvU16 *deviceId) {
    if (vendor) *vendor = 0;
    if (deviceId) *deviceId = 0;
    if (!ordinary() || !binding.session || !vendor || !deviceId) return nullptr;
    const Snapshot facts = binding.session->snapshot();
    if (!facts.segmentKnown || facts.segment != segment || facts.bus != bus ||
        facts.device != device || facts.function != function || !binding.session->accessible())
        return nullptr;
    *vendor = 0x10de; *deviceId = 0x1f91;
    return binding.pciHandle;
}
extern "C" NV_STATUS NV_API_CALL s540Global_os_pci_read_byte(void *handle, NvU32 offset, NvU8 *out) {
    if (!out) return NV_ERR_INVALID_ARGUMENT;
    NvU32 captured = 0; NV_STATUS status = pciRead(handle,offset,1,captured);
    if (status == NV_OK) *out = static_cast<NvU8>(captured);
    return status;
}
extern "C" NV_STATUS NV_API_CALL s540Global_os_pci_read_word(void *handle, NvU32 offset, NvU16 *out) {
    if (!out) return NV_ERR_INVALID_ARGUMENT;
    NvU32 captured = 0; NV_STATUS status = pciRead(handle,offset,2,captured);
    if (status == NV_OK) *out = static_cast<NvU16>(captured);
    return status;
}
extern "C" NV_STATUS NV_API_CALL s540Global_os_pci_read_dword(void *handle, NvU32 offset, NvU32 *out) {
    if (!out) return NV_ERR_INVALID_ARGUMENT;
    return pciRead(handle,offset,4,*out);
}
extern "C" NV_STATUS NV_API_CALL s540Global_os_pci_write_byte(void *handle, NvU32 offset, NvU8 value) {
    return pciWrite(handle,offset,1,value);
}
extern "C" NV_STATUS NV_API_CALL s540Global_os_pci_write_word(void *handle, NvU32 offset, NvU16 value) {
    return pciWrite(handle,offset,2,value);
}
extern "C" NV_STATUS NV_API_CALL s540Global_os_pci_write_dword(void *handle, NvU32 offset, NvU32 value) {
    return pciWrite(handle,offset,4,value);
}
extern "C" void *NV_API_CALL s540Global_os_map_kernel_space(NvU64 physical, NvU64 bytes, NvU32 mode) {
    // NVIDIA NV_MEMORY_UNCACHED: register space cannot gain a cacheable alias.
    if (!ordinary() || !binding.session || mode != 1) return nullptr;
    void *address = nullptr;
    if (binding.session->mapRegisters(physical,bytes,&address) != NV_OK) return nullptr;
    return address;
}
extern "C" void NV_API_CALL s540Global_os_unmap_kernel_space(void *address, NvU64 bytes) {
    if (ordinary() && binding.session) (void)binding.session->unmapRegisters(address,bytes);
}
extern "C" NvBool NV_API_CALL s540Global_nv_is_gpu_accessible(nv_state_t *) {
    // Original Linux contract checks current process's open NVIDIA file. This
    // kernel-only checkpoint publishes no user client, so authorization denies.
    return NV_FALSE;
}
extern "C" NvBool NV_API_CALL s540Global_nv_match_gpu_os_info(nv_state_t *, void *) {
    return NV_FALSE;
}
extern "C" void NV_API_CALL s540Global_nv_flush_coherent_cpu_cache_range(nv_state_t *state,
    NvU64 address, NvU64 bytes) {
    if (!stateValid(state) || !bytes || address > ~NvU64(0) - (bytes - 1)) return;
    // Original nv.c6346 performs explicit cache maintenance only on AArch64.
    // This x86_64 profile rejects DMA bounce aliases and uses coherent pages.
    __atomic_thread_fence(__ATOMIC_SEQ_CST);
}
extern "C" void NV_API_CALL s540Global_nv_dma_cache_invalidate(nv_dma_device_t *dma, void *privateData) {
    if (!ordinary() || !binding.session || dma != binding.dma) return;
    for (const auto &entry : binding.allocations)
        if (entry.mapped && entry.dmaToken == privateData) {
            // Exact nv-dma.c898 policy is cache maintenance only on AArch64.
            __atomic_thread_fence(__ATOMIC_SEQ_CST);
            return;
        }
}
