/* SPDX-License-Identifier: MIT */
#include "nv.h"
#include "os-interface.h"
#include "S540NvidiaGlobalRm.h"
#include "S540NvidiaGlobalRmCentralPolicy.h"
#include <stdio.h>
#include <unistd.h>
#include <signal.h>
#include <sys/wait.h>
int main(void)
{
    NvU32 checks = 0;
    S540NvidiaGlobalRmPlatformFacts facts = {0};
    S540NvidiaGlobalRmHostSnapshot host;
    pid_t child;
    int status = 0;
#define EXPECT(x) do { ++checks; if (!(x)) { fprintf(stderr,"Central policy check %d failed\n",__LINE__); return 1; } } while (0)
    facts.format = 1; facts.known = S540_GLOBAL_FACT_ALL;
    facts.cpuCount = 1; facts.cpuFrequencyHz = 2000000000ULL;
    facts.osMajor = 25; facts.osVersion = facts.osDate = "native-central-policy-fixture";
    EXPECT(s540GlobalRmHostInitialize(&facts) == NV_OK);
    EXPECT(S540_GLOBAL_RM_CENTRAL_POLICY_VERSION == 1);
    EXPECT(!os_supports_kernel_suspend_notifiers());
    EXPECT(!os_pci_remove_supported());
    EXPECT(os_enable_pci_req_atomics(NULL,OS_INTF_PCIE_REQ_ATOMICS_32BIT) == NV_ERR_NOT_SUPPORTED);
    EXPECT(os_enable_pci_req_atomics(NULL,OS_INTF_PCIE_REQ_ATOMICS_64BIT) == NV_ERR_NOT_SUPPORTED);
    EXPECT(os_enable_pci_req_atomics(NULL,OS_INTF_PCIE_REQ_ATOMICS_128BIT) == NV_ERR_NOT_SUPPORTED);
    EXPECT(os_enable_pci_req_atomics(NULL,(enum os_pci_req_atomics_type)99) == NV_ERR_NOT_SUPPORTED);
    nv_audio_dynamic_power(NULL);
    nv_pci_cxl_set_caching(NULL,NV_FALSE);
    nv_pci_cxl_set_caching(NULL,NV_TRUE);
    s540GlobalRmHostSnapshot(&host);
    EXPECT(!host.unavailableCalls && !host.invalidFrees && !host.liveAllocations);
    EXPECT(nv_indicate_idle(NULL) == NV_ERR_NOT_SUPPORTED);
    EXPECT(nv_indicate_not_idle(NULL) == NV_ERR_NOT_SUPPORTED);
    s540GlobalRmHostSnapshot(&host);
    EXPECT(host.unavailableCalls == 2 && !host.invalidFrees && !host.liveAllocations);
    child = fork();
    EXPECT(child >= 0);
    if (!child) os_pci_remove(NULL);
    EXPECT(waitpid(child,&status,0) == child);
    EXPECT(WIFSIGNALED(status) && (WTERMSIG(status) == SIGABRT || WTERMSIG(status) == SIGILL));
    EXPECT(s540GlobalRmHostShutdown());
    printf("{\"format\":1,\"component\":\"nvidia-central-policy\",\"status\":\"passed\",\"checks\":%u,\"failures\":0,\"execution\":\"native-user-space\",\"kernel_execution\":\"not_tested\",\"gpu_access\":false,\"unavailable_runtime_pm_operations\":2,\"hot_remove_tripwire\":true,\"physical_feature_absence_inferred\":false}\n",checks);
    return 0;
}
