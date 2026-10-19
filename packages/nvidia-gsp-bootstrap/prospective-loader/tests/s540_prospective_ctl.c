/* SPDX-License-Identifier: MIT */
/* Source-only control tool. It neither loads a module nor touches a PCI device. */
#if !defined(__APPLE__)
#error This compile-only control tool requires the real macOS userspace IOKit SDK
#endif
#include <IOKit/IOKitLib.h>
#include <CoreFoundation/CoreFoundation.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include "../S540ProspectiveLoaderProtocol.h"
static kern_return_t snapshot(io_connect_t connection,S540ProspectiveSnapshot *out) {
    size_t bytes=sizeof(*out);
    kern_return_t status=IOConnectCallStructMethod(connection,S540_PROSPECTIVE_SELECTOR_SNAPSHOT,
        NULL,0,out,&bytes);
    if (status==KERN_SUCCESS && (bytes!=sizeof(*out) || out->format!=S540_PROSPECTIVE_PROTOCOL_VERSION ||
        out->bytes!=sizeof(*out))) return kIOReturnBadArgument;
    return status;
}
int main(int argc,char **argv) {
    if (geteuid()!=0) { fprintf(stderr,"Administrator required.\n"); return 1; }
    if (argc>2 || (argc==2 && strcmp(argv[1],"--request-once"))) {
        fprintf(stderr,"Usage: s540_prospective_ctl [--request-once]\n"); return 1;
    }
    io_service_t service=IOServiceGetMatchingService(kIOMainPortDefault,
        IOServiceMatching("S540ProspectiveLoaderControl"));
    if (!service) { fprintf(stderr,"Control service is not started.\n"); return 1; }
    io_connect_t connection=IO_OBJECT_NULL;
    kern_return_t status=IOServiceOpen(service,mach_task_self(),S540_PROSPECTIVE_CONNECTION_TYPE,&connection);
    IOObjectRelease(service);
    if (status!=KERN_SUCCESS) { fprintf(stderr,"Open failed:0x%x\n",status); return 1; }
    S540ProspectiveSnapshot observed={0};
    status=snapshot(connection,&observed);
    if (status==KERN_SUCCESS && argc==2) {
        S540ProspectiveRequest request={S540_PROSPECTIVE_PROTOCOL_VERSION,sizeof(request),observed.generation};
        S540ProspectiveSnapshot ignored={0};size_t bytes=sizeof(ignored);
        kern_return_t requested=IOConnectCallStructMethod(connection,S540_PROSPECTIVE_SELECTOR_REQUEST,
            &request,sizeof(request),&ignored,&bytes);
        fprintf(stderr,"Request result:0x%x (entry policy remains closed).\n",requested);
        /* Always re-query; an error return need not copy structure outputs. */
        status=snapshot(connection,&observed);
    }
    IOServiceClose(connection);
    if (status!=KERN_SUCCESS) { fprintf(stderr,"Snapshot failed:0x%x\n",status); return 1; }
    printf("{\"format\":%u,\"phase\":%u,\"generation\":%llu,\"module_entry_accepted\":%u,"
        "\"control_service_started\":%u,\"one_shot_consumed\":%u,\"entry_policy_closed\":%u,"
        "\"target_loader_admission_proven\":%u,\"original_calls\":%u}\n",observed.format,
        observed.phase,(unsigned long long)observed.generation,observed.moduleEntryAccepted,
        observed.controlServiceStarted,observed.rootRequestConsumed,observed.entryPolicyClosed,
        observed.targetLoaderAdmissionProven,observed.originalCalls);
    return observed.entryPolicyClosed && !observed.targetLoaderAdmissionProven && !observed.originalCalls ? 0:1;
}
