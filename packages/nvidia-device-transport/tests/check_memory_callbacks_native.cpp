// SPDX-License-Identifier: MIT
#include "../src/nv_unsupported_memory.h"
#include <csignal>
#include <cstdio>
#include <cstdlib>
#include <sys/resource.h>
#include <sys/wait.h>
#include <unistd.h>

namespace {
unsigned checks;
void expect(bool condition, const char *message) {
    ++checks;
    if (!condition) { std::fprintf(stderr, "Memory callback assertion failed: %s\n", message); std::exit(1); }
}
void rejected(NV_STATUS status, const char *message) {
    expect(status == NV_ERR_NOT_SUPPORTED, message);
}
void lifetimeGuard(unsigned which) {
    const pid_t child = fork();
    expect(child >= 0, "guard subprocess created");
    if (!child) {
        const rlimit limit{0, 0};
        (void)setrlimit(RLIMIT_CORE, &limit);
        if (!std::freopen("/dev/null", "w", stderr)) _exit(76);
        switch (which) {
        case 0: s540Global_nv_unregister_peer_io_mem(nullptr, nullptr); break;
        case 1: s540Global_nv_unregister_phys_pages(nullptr, nullptr); break;
        case 2: s540Global_nv_unregister_user_pages(nullptr, 0, nullptr, nullptr); break;
        case 3: s540Global_nv_unregister_sgt(nullptr, nullptr, nullptr, nullptr); break;
        case 4: s540Global_nv_dma_unmap_peer(nullptr, 0, 0); break;
        case 5: s540Global_nv_dma_unmap_mmio(nullptr, 0, 0); break;
        case 6: s540Global_nv_dma_destroy_sysmem_window_for_fabric_access(nullptr, 0, 0); break;
        case 7: (void)s540Global_os_get_page_refcount(0); break;
        case 8: (void)s540Global_os_count_tail_pages(0); break;
        }
        _exit(77);
    }
    int status = 0;
    expect(waitpid(child, &status, 0) == child, "guard subprocess reaped");
    expect(WIFSIGNALED(status) && WTERMSIG(status) == SIGABRT,
           "unavailable lifetime/scalar callback cannot report success");
}
}
int main() {
    s540DeviceMemoryResetStatistics();
    NvU64 address = 0x12345000, bytes = 0x1234, extra = 0xabc, reserved = 0xdef;
    NvU64 ptes[2]{0x11111000,0x22222000};
    NvU32 pages = 7, width = 31, node = 0x55;
    NvS32 signedNode = 27;
    NvBool identity = NV_TRUE;
    void *privateData = reinterpret_cast<void *>(NvUPtr(0x600));
    auto *sgt = reinterpret_cast<sg_table *>(NvUPtr(0x700));
    auto *buffer = reinterpret_cast<nv_dma_buf_t *>(NvUPtr(0x800));
    rejected(s540Global_nv_alias_pages(nullptr,2,4096,0,0,0,ptes,NV_FALSE,&privateData), "guest alias refused");
    rejected(s540Global_nv_alloc_user_mapping(nullptr,privateData,0,0,4096,0,&address,&privateData), "user mapping refused");
    rejected(s540Global_nv_register_peer_io_mem(nullptr,ptes,2,&privateData), "peer IO import refused");
    rejected(s540Global_nv_register_phys_pages(nullptr,ptes,2,0,&privateData), "external physical import refused");
    rejected(s540Global_nv_register_user_pages(nullptr,2,ptes,privateData,&privateData,NV_FALSE), "Linux user pages refused");
    rejected(s540Global_nv_register_sgt(nullptr,ptes,2,0,&privateData,sgt,privateData,NV_FALSE), "Linux SGT registration refused");
    rejected(s540Global_nv_get_phys_pages(privateData,ptes,&pages), "struct page output refused");
    rejected(s540Global_nv_dma_map_peer(nullptr,nullptr,0,2,&address), "peer DMA refused");
    rejected(s540Global_nv_dma_map_mmio(nullptr,2,&address), "MMIO DMA refused");
    rejected(s540Global_nv_dma_import_sgt(nullptr,sgt,nullptr), "GEM import disabled");
    rejected(s540Global_nv_dma_import_dma_buf(nullptr,nullptr,NV_FALSE,&pages,&sgt,&buffer), "DMA-BUF import disabled");
    rejected(s540Global_nv_dma_import_from_fd(nullptr,-1,NV_FALSE,&pages,&sgt,&buffer), "DMA-BUF fd import disabled");
    rejected(s540Global_nv_dma_init_sysmem_window_for_fabric_access(nullptr,4096,&address,&bytes,&identity), "fabric window refused");
    rejected(s540Global_os_alloc_pages_node(0,4096,0,&address), "NUMA allocation refused");
    rejected(s540Global_os_get_page(address), "Linux page reference acquire refused");
    rejected(s540Global_os_put_page(address), "Linux page reference release refused");
    rejected(s540Global_os_numa_memblock_size(&bytes), "NUMA block size unavailable");
    rejected(s540Global_os_get_numa_node_memory_usage(0,&address,&bytes), "NUMA usage unavailable");
    rejected(s540Global_os_numa_add_gpu_memory(nullptr,0,4096,&node), "NUMA hotplug refused");
    rejected(s540Global_os_numa_remove_gpu_memory(nullptr,0,4096,node), "NUMA hotremove refused");
    rejected(s540Global_os_offline_page_at_address(address), "Linux page offline refused");
    rejected(s540Global_os_unlock_user_pages(2,privateData,0), "Linux user unpin refused");
    rejected(s540Global_os_iommu_sva_bind(nullptr,&privateData,&pages), "process SVA binding refused");
    expect(address == 0x12345000 && bytes == 0x1234 && pages == 7 && node == 0x55 && identity == NV_TRUE,
           "refused operations preserve scalar in/out values");
    expect(ptes[0] == 0x11111000 && ptes[1] == 0x22222000 &&
           privateData == reinterpret_cast<void *>(NvUPtr(0x600)) &&
           sgt == reinterpret_cast<sg_table *>(NvUPtr(0x700)) &&
           buffer == reinterpret_cast<nv_dma_buf_t *>(NvUPtr(0x800)),
           "refused operations preserve PTEs and opaque ownership");
    auto statistics = s540DeviceMemoryStatistics();
    expect(statistics.unavailableOperations == 23 && !statistics.disabledFeatureQueries &&
           !statistics.officialNoopReleases && !statistics.lifetimeViolations,
           "unimplemented operations remain distinguishable from supported callbacks");
    rejected(s540Global_nv_get_device_memory_config(nullptr,&address,&extra,&bytes,&reserved,&width,&signedNode),
             "exact original x86 coherent-memory query returns unsupported");
    rejected(s540Global_nv_get_egm_info(nullptr,&address,&bytes,&signedNode), "EGM platform query returns unsupported");
    rejected(s540Global_os_flush_cpu_cache_all(), "exact original x86 full cache flush unsupported");
    rejected(s540Global_os_flush_user_cache(), "exact original x86 user cache flush unsupported");
    expect(address == 0x12345000 && extra == 0xabc && bytes == 0x1234 && reserved == 0xdef &&
           width == 31 && signedNode == 27, "disabled feature queries preserve output");
    statistics = s540DeviceMemoryStatistics();
    expect(statistics.disabledFeatureQueries == 4 && statistics.unavailableOperations == 23,
           "expected disabled feature queries do not hide unavailable operations");
    s540Global_nv_free_user_mapping(nullptr,privateData,address,privateData);
    s540Global_nv_dma_release_sgt(sgt,nullptr);
    s540Global_nv_dma_release_dma_buf(buffer);
    s540Global_os_iommu_sva_unbind(privateData);
    statistics = s540DeviceMemoryStatistics();
    expect(statistics.officialNoopReleases == 4 && statistics.unavailableOperations == 23,
           "only exact original disabled/empty releases are noops");
    rejected(s540Global_nv_get_phys_pages(nullptr,nullptr,nullptr), "null structpage request refused without dereference");
    rejected(s540Global_nv_dma_import_from_fd(nullptr,0,NV_TRUE,nullptr,nullptr,nullptr), "null DMA-BUF outputs not dereferenced");
    for (unsigned guard = 0; guard != 9; ++guard) lifetimeGuard(guard);
    s540DeviceMemoryResetStatistics();
    statistics = s540DeviceMemoryStatistics();
    expect(!statistics.disabledFeatureQueries && !statistics.unavailableOperations &&
           !statistics.officialNoopReleases && !statistics.lifetimeViolations &&
           statistics.unavailableOperationsEver == 25 && !statistics.lifetimeViolationsEver,
           "native telemetry reset cannot erase lifetime-monotonic unavailable operations");
    std::printf("{\"format\":1,\"component\":\"nvidia-memory-callbacks\",\"status\":\"passed\","
                "\"failures\":0,\"execution\":\"native-user-space\","
                "\"checks\":%u,\"guard_subprocesses\":9,\"kernel_execution\":\"not_tested\",\"gpu_access\":false,"
                "\"linux_page_layouts_fabricated\":false,\"memory_operations_implemented\":false}\n", checks);
}
