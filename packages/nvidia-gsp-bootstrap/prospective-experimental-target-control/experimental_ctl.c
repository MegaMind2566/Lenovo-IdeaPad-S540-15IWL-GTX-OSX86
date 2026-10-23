/* SPDX-License-Identifier: MIT */
#if !defined(__APPLE__) || !defined(__x86_64__)
#error The actual target client requires Intel macOS userspace IOKit
#endif
#include <IOKit/IOKitLib.h>
#include <CoreFoundation/CoreFoundation.h>
#include <sys/sysctl.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include "S540ExperimentalTargetProtocol.h"
#ifndef S540_EXPERIMENTAL_EXPECTED_SOURCE
#error Packaging must bind the client to the actual independently verified image
#endif
static const NvU8 expectedSource[32]=S540_EXPERIMENTAL_EXPECTED_SOURCE;
static const NvU8 expectedPolicy[32]=S540_EXPERIMENTAL_EXPECTED_POLICY;
static const NvU8 expectedNative[32]=S540_EXPERIMENTAL_EXPECTED_NATIVE;
static int registryNumber(io_registry_entry_t entry,const char *key,NvU32 *out) {
    CFStringRef name=CFStringCreateWithCString(kCFAllocatorDefault,key,kCFStringEncodingUTF8);
    if (!name) return 0;
    CFTypeRef value=IORegistryEntryCreateCFProperty(entry,name,kCFAllocatorDefault,0);CFRelease(name);
    int ok=value && CFGetTypeID(value)==CFDataGetTypeID() && CFDataGetLength((CFDataRef)value)==4;
    if (ok) { const UInt8 *p=CFDataGetBytePtr((CFDataRef)value);
        *out=(NvU32)p[0]|(NvU32)p[1]<<8|(NvU32)p[2]<<16|(NvU32)p[3]<<24; }
    if (value) CFRelease(value);return ok;
}
static int targetIdentity(void) {
    io_iterator_t iterator=IO_OBJECT_NULL;
    if (IOServiceGetMatchingServices(kIOMainPortDefault,IOServiceMatching("IOPCIDevice"),&iterator)!=KERN_SUCCESS) return 1;
    unsigned matches=0;int exhausted=0,valid=1;
    for (unsigned count=0;count<1024;++count) {
        if (!IOIteratorIsValid(iterator)) { valid=0;break; }
        io_registry_entry_t entry=IOIteratorNext(iterator);
        if (!entry) { exhausted=1;break; }
        NvU32 vendor,device,subvendor,subdevice,revision,classcode;
        if (registryNumber(entry,"vendor-id",&vendor) && vendor==0x10de &&
            registryNumber(entry,"device-id",&device) && device==0x1f91 &&
            registryNumber(entry,"subsystem-vendor-id",&subvendor) && subvendor==0x17aa &&
            registryNumber(entry,"subsystem-id",&subdevice) && subdevice==0x3806 &&
            registryNumber(entry,"revision-id",&revision) && revision==0xa1 &&
            registryNumber(entry,"class-code",&classcode) && classcode==0x030000) ++matches;
        IOObjectRelease(entry);
    }
    valid=valid && exhausted && IOIteratorIsValid(iterator);IOObjectRelease(iterator);
    printf("{\"scope\":\"readonly-registry-identity\",\"matches\":%u,\"iterator_valid\":%s,\"hardware_access\":false}\n",
        matches,valid?"true":"false");return valid && matches==1 ? 0:1;
}
static int readText(const char *name,const char *expected) {
    char value[128]={0};size_t bytes=sizeof(value);
    return sysctlbyname(name,value,&bytes,NULL,0)==0 && bytes>0 && bytes<=sizeof(value) &&
        value[sizeof(value)-1]==0 && !strcmp(value,expected);
}
static int readStack(NvU64 *result) {
    NvU64 value=0;size_t bytes=sizeof(value);
    if (sysctlbyname("kern.stack_size",&value,&bytes,NULL,0)!=0 || (bytes!=4 && bytes!=8) || !value) return 0;
    *result=value;return 1;
}
static kern_return_t observe(io_connect_t connection,S540ExperimentalSnapshot *out) {
    size_t bytes=sizeof(*out);memset(out,0,sizeof(*out));
    kern_return_t status=IOConnectCallStructMethod(connection,S540_EXPERIMENTAL_SELECTOR_SNAPSHOT,NULL,0,out,&bytes);
    if (status==KERN_SUCCESS && (bytes!=sizeof(*out) || out->format!=1 || out->bytes!=sizeof(*out))) return kIOReturnBadArgument;
    return status;
}
static int identityMatches(const S540ExperimentalSnapshot *observed,NvU64 stack) {
    return observed->moduleEntryAccepted && observed->controlServiceStarted && observed->generation &&
        !memcmp(observed->sourceSha256,expectedSource,32) && !memcmp(observed->policySha256,expectedPolicy,32) &&
        !memcmp(observed->nativeCodeContractSha256,expectedNative,32) &&
        observed->nativeRequiredKernelStackBytes && observed->nativeRequiredIrqStackBytes &&
        stack>=S540_EXPERIMENTAL_REQUIRED_STACK && stack>=observed->nativeRequiredKernelStackBytes &&
        !observed->wholeDmaStopProven && !observed->pmAcknowledgementAuthorized && !observed->accelerationTest;
}
static void printSnapshot(const S540ExperimentalSnapshot *s,kern_return_t requested,kern_return_t stopped,
    kern_return_t observation,int attempted) {
    printf("{\"format\":1,\"scope\":\"retained-first-initialization\",\"request_rpc_attempted\":%s,"
        "\"request_rpc_status\":%u,\"stop_rpc_status\":%u,\"snapshot_rpc_status\":%u,"
        "\"phase\":%u,\"last_status\":%u,\"generation\":%llu,\"observed_kernel_stack_bytes\":%llu,"
        "\"request_consumed\":%u,\"request_running\":%u,\"retained_until_reboot\":%u,"
        "\"owner_allocated\":%u,\"provider_found\":%u,\"preparation_attempted\":%u,\"preparation_returned\":%u,"
        "\"preparation_status\":%u,\"initialization_attempted\":%u,\"initialization_returned\":%u,"
        "\"initialization_status\":%u,\"original_entry_observed\":%u,\"global_initialized\":%u,"
        "\"adapter_initialized\":%u,\"firmware_loaded\":%u,\"interrupt_installed\":%u,\"interrupt_armed\":%u,"
        "\"stop_attempted\":%u,\"stop_returned\":%u,\"stop_status\":%u,\"cancellation_status\":%u,"
        "\"runtime_observation_status\":%u,\"stop_observation_status\":%u,\"power_revoked\":%u,"
        "\"cancellation_revoked\":%u,\"power_acknowledged\":%u,\"whole_dma_stop_proven\":false,"
        "\"pm_acknowledgement_authorized\":false,\"acceleration_test\":false}\n",
        attempted?"true":"false",(unsigned)requested,(unsigned)stopped,(unsigned)observation,s->phase,s->lastStatus,
        (unsigned long long)s->generation,(unsigned long long)s->observedKernelStackBytes,s->requestConsumed,
        s->requestRunning,s->retainedUntilReboot,s->ownerAllocated,s->providerFound,s->preparationAttempted,
        s->preparationReturned,s->preparationStatus,s->initializationAttempted,s->initializationReturned,
        s->initializationStatus,s->originalEntryObserved,s->globalInitialized,s->adapterInitialized,s->firmwareLoaded,
        s->interruptInstalled,s->interruptArmed,s->stopAttempted,s->stopReturned,s->stopStatus,s->cancellationStatus,
        s->runtimeObservationStatus,s->stopObservationStatus,s->powerRevoked,s->cancellationRevoked,s->powerAcknowledged);
}
int main(int argc,char **argv) {
    int run=argc==3 && !strcmp(argv[1],"--run-once") && !strcmp(argv[2],"--ack-retained-first-initialization");
    int target=argc==2 && !strcmp(argv[1],"--target");
    if (!run && !target && !(argc==2 && !strcmp(argv[1],"--snapshot"))) {
        fprintf(stderr,"Usage: experimental_ctl --target | --snapshot | --run-once --ack-retained-first-initialization\n");return 2;
    }
    if (geteuid()!=0) { fprintf(stderr,"Administrator required.\n");return 2; }
    NvU64 stack=0;
    if (!readText("kern.osversion","25G241") || !readText("kern.osrelease","25.6.0") || !readStack(&stack)) {
        fprintf(stderr,"Target build/release or actual kern.stack_size could not be confirmed.\n");return 2;
    }
    if (target) return targetIdentity();
    io_service_t service=IOServiceGetMatchingService(kIOMainPortDefault,IOServiceMatching("S540ExperimentalTargetControl"));
    if (!service) { fprintf(stderr,"Experimental control service is absent.\n");return 2; }
    io_connect_t connection=IO_OBJECT_NULL;
    uint64_t registryID=0;
    kern_return_t identified=IORegistryEntryGetRegistryEntryID(service,&registryID);
    kern_return_t status=IOServiceOpen(service,mach_task_self(),S540_EXPERIMENTAL_CONNECTION_TYPE,&connection);
    IOObjectRelease(service);
    if (status!=KERN_SUCCESS || identified!=KERN_SUCCESS || !registryID) {
        if (status==KERN_SUCCESS) IOServiceClose(connection);
        fprintf(stderr,"Open/registry identity failed:0x%x\n",status);return 2; }
    S540ExperimentalSnapshot observed={0};
    status=observe(connection,&observed);
    if (status!=KERN_SUCCESS || !identityMatches(&observed,stack) || observed.generation!=registryID) {
        fprintf(stderr,"Loaded image identity, native code contract, or observed stack does not match this client.\n");
        IOServiceClose(connection);return 2;
    }
    kern_return_t requested=KERN_SUCCESS,stopped=KERN_SUCCESS;
    if (run) {
        S540ExperimentalRequest request={0};request.format=1;request.bytes=sizeof(request);
        request.generation=observed.generation;request.observedKernelStackBytes=stack;
        request.manualAcknowledgement=S540_EXPERIMENTAL_MANUAL_ACK;
        memcpy(request.sourceSha256,expectedSource,32);memcpy(request.policySha256,expectedPolicy,32);
        memcpy(request.nativeCodeContractSha256,expectedNative,32);memcpy(request.targetBuild,"25G241",7);
        S540ExperimentalSnapshot output={0};size_t bytes=sizeof(output);
        requested=IOConnectCallStructMethod(connection,S540_EXPERIMENTAL_SELECTOR_REQUEST,&request,sizeof(request),&output,&bytes);
        // Error return does not prove a call never began. Always ask the same
        // live connection for a real stop, then independently re-observe.
        bytes=sizeof(output);
        stopped=IOConnectCallStructMethod(connection,S540_EXPERIMENTAL_SELECTOR_STOP,NULL,0,&output,&bytes);
        status=observe(connection,&observed);
    }
    printSnapshot(&observed,requested,stopped,status,run);
    IOServiceClose(connection);
    return status==KERN_SUCCESS && (!run || requested==KERN_SUCCESS) ? 0:1;
}
