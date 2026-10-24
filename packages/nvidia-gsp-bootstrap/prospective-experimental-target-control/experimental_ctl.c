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
    return sysctlbyname(name,value,&bytes,NULL,0)==0 && bytes==strlen(expected)+1 &&
        bytes<=sizeof(value) && value[bytes-1]==0 && !strcmp(value,expected);
}
static int readStack(NvU64 *result) {
    NvU64 value=0;size_t bytes=sizeof(value);
    if (sysctlbyname("kern.stack_size",&value,&bytes,NULL,0)!=0 || (bytes!=4 && bytes!=8) || !value) return 0;
    *result=value;return 1;
}
static kern_return_t observe(io_connect_t connection,S540ExperimentalSnapshot *out) {
    size_t bytes=sizeof(*out);memset(out,0,sizeof(*out));
    kern_return_t status=IOConnectCallStructMethod(connection,S540_EXPERIMENTAL_SELECTOR_SNAPSHOT,NULL,0,out,&bytes);
    if (status==KERN_SUCCESS && (bytes!=sizeof(*out) || out->format!=S540_EXPERIMENTAL_SNAPSHOT_VERSION ||
        out->bytes!=sizeof(*out))) return kIOReturnBadArgument;
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
static void printStop(const S540ExperimentalStopObservation *s) {
    const struct { const char *name;NvU32 value; } fields[]={
        {"format",s->format},{"bytes",s->bytes},{"attempts",s->attempts},{"status",s->status},
        {"first_error",s->firstError},{"snapshot_status",s->snapshotStatus},{"identity_status",s->identityStatus},
        {"locks_status",s->locksStatus},{"protocol_status",s->protocolStatus},{"closing_status",s->closingStatus},
        {"services_status",s->servicesStatus},{"seal_status",s->sealStatus},{"disable_status",s->disableStatus},
        {"interrupt_status",s->interruptStatus},{"shutdown_status",s->shutdownStatus},{"requested",s->requested},
        {"retained",s->retained},{"original_returned",s->originalReturned},{"original_exit_ready",s->originalExitReady},
        {"locks_released",s->locksReleased},{"protocol_attempted",s->protocolAttempted},{"services_attempted",s->servicesAttempted},
        {"interrupt_attempted",s->interruptAttempted},{"disable_attempted",s->disableAttempted},{"shutdown_attempted",s->shutdownAttempted},
        {"services_drained",s->servicesDrained},{"interrupt_software_drained",s->interruptSoftwareDrained},
        {"interrupt_fully_drained",s->interruptFullyDrained},{"cleanup_complete",s->cleanupComplete},
        {"physical_release_authorized",s->physicalReleaseAuthorized},{"pm_acknowledgement_sent",s->pmAcknowledgementSent},
        {"protocol_format",s->protocolFormat},{"protocol_bytes",s->protocolBytes},{"protocol_operation_status",s->protocolOperationStatus},
        {"protocol_original_return_status",s->protocolOriginalReturnStatus},{"protocol_unlock_status",s->protocolUnlockStatus},
        {"protocol_claimed",s->protocolClaimed},{"protocol_original_entered",s->protocolOriginalEntered},
        {"protocol_original_returned",s->protocolOriginalReturned},{"protocol_completed",s->protocolCompleted}};
    printf("\"retained_stop\":{\"generation\":%llu,\"protocol_generation\":%llu",
        (unsigned long long)s->generation,(unsigned long long)s->protocolGeneration);
    for (unsigned i=0;i<sizeof(fields)/sizeof(fields[0]);++i) printf(",\"%s\":%u",fields[i].name,fields[i].value);
    printf("}");
}
static const char *preparationStageLabel(NvU32 stage) {
    static const char *const names[]={"unobserved","validate","verify-firmware","allocate-owner",
        "snapshot-mutex","dispatcher-start","dispatch-prepare","power-start","platform-initialize",
        "host-facts","device-facts","host-strings","host-initialize","transport-start","pci-segment",
        "dma-remap","context-create","context-detacher","cancellation-bind","power-cancellation",
        "power-revoke-check","platform-bind","rm-bind","rm-dma-remap","allocate-gsp","allocate-ucodes",
        "copy-firmware","firmware-store","firmware-bind","timers-bind","final-power","complete"};
    return stage<sizeof(names)/sizeof(names[0]) ? names[stage]:"unknown";
}
static const char *powerStageLabel(NvU32 stage) {
    static const char *const names[]={"unobserved","join-attach","join-service-start","join-pm-init",
        "join-register-driver","join-request-off","join-add-power-child","join-request-on-priv",
        "join-mark-requested","wait-ready","wait-domain","wait-active","complete","final-status"};
    return stage<sizeof(names)/sizeof(names[0]) ? names[stage]:"unknown";
}
static const char *jsonBool(int value) { return value ? "true":"false"; }
static void printPreparation(const S540PreparationObservation *p,int snapshotValid) {
    const NvU32 knownMask=S540_PREP_OBS_STAGE|S540_PREP_OBS_STATUS|S540_PREP_OBS_FIRST_FAILURE|
        S540_PREP_OBS_HOST_FACTS|S540_PREP_OBS_DEVICE_FACTS|S540_PREP_OBS_POWER;
    int valid=snapshotValid && p->format==1 && p->bytes==sizeof(*p) && (p->observedMask&knownMask)!=0;
    int stageValid=valid && (p->observedMask&S540_PREP_OBS_STAGE) &&
        p->stage>S540_PREP_UNOBSERVED && p->stage<=S540_PREP_COMPLETE;
    int completedValid=valid && (p->observedMask&S540_PREP_OBS_STAGE) &&
        p->lastCompleted>S540_PREP_UNOBSERVED && p->lastCompleted<=S540_PREP_COMPLETE;
    int failureObserved=valid && (p->observedMask&S540_PREP_OBS_FIRST_FAILURE);
    int failureValid=failureObserved && p->firstFailureStage>S540_PREP_UNOBSERVED &&
        p->firstFailureStage<=S540_PREP_COMPLETE && p->firstFailureStatus!=NV_OK;
    int hostValid=valid && (p->observedMask&S540_PREP_OBS_HOST_FACTS);
    int deviceValid=valid && (p->observedMask&S540_PREP_OBS_DEVICE_FACTS);
    printf("\"preparation\":{\"format\":%u,\"bytes\":%u,\"valid\":%s,\"observed_mask\":%u,"
        "\"stage\":%u,\"stage_label\":\"%s\",\"stage_valid\":%s,"
        "\"last_completed\":%u,\"last_completed_label\":\"%s\",\"last_completed_valid\":%s,"
        "\"last_status\":%u,\"last_status_valid\":%s,\"first_failure_observed\":%s,"
        "\"first_failure_stage\":%u,\"first_failure_stage_label\":\"%s\",\"first_failure_status\":%u,"
        "\"first_failure_valid\":%s,\"host_facts_valid\":%s,\"host_known_mask\":%u,\"host_missing_mask\":%u,"
        "\"device_facts_valid\":%s,\"device_observed_mask\":%u,\"device_predicates_mask\":%u,\"host_facts\":{",
        p->format,p->bytes,jsonBool(valid),p->observedMask,p->stage,preparationStageLabel(p->stage),
        jsonBool(stageValid),p->lastCompleted,preparationStageLabel(p->lastCompleted),jsonBool(completedValid),
        p->lastStatus,jsonBool(valid && (p->observedMask&S540_PREP_OBS_STATUS)),jsonBool(failureObserved),
        p->firstFailureStage,preparationStageLabel(p->firstFailureStage),p->firstFailureStatus,
        jsonBool(failureValid),jsonBool(hostValid),p->hostKnown,p->hostMissing,jsonBool(deviceValid),
        p->deviceObserved,p->devicePredicates);
    const struct { const char *name;NvU32 bit; } hosts[]={
        {"notebook",S540_PREP_HOST_NOTEBOOK},{"battery",S540_PREP_HOST_BATTERY},{"efi",S540_PREP_HOST_EFI},
        {"vgpu_hypervisor",S540_PREP_HOST_VGPU_HYPERVISOR},{"nvswitch",S540_PREP_HOST_NVSWITCH},
        {"s0ix",S540_PREP_HOST_S0IX},{"cpu",S540_PREP_HOST_CPU},{"os_version",S540_PREP_HOST_OS_VERSION}};
    for (unsigned i=0;i<sizeof(hosts)/sizeof(hosts[0]);++i)
        printf("%s\"%s\":{\"known\":%s,\"missing\":%s}",i?",":"",hosts[i].name,
            hostValid?jsonBool(p->hostKnown&hosts[i].bit):"null",
            hostValid?jsonBool(p->hostMissing&hosts[i].bit):"null");
    printf("},\"device_predicates\":{");
    const struct { const char *name;NvU32 bit; } devices[]={
        {"segment",S540_PREP_DEVICE_SEGMENT},{"pci",S540_PREP_DEVICE_PCI},{"bars",S540_PREP_DEVICE_BARS},
        {"d0",S540_PREP_DEVICE_D0},{"intel_console",S540_PREP_DEVICE_INTEL_CONSOLE},
        {"nvidia_excluded",S540_PREP_DEVICE_NVIDIA_EXCLUDED},
        {"no_coherent_gpu_memory",S540_PREP_DEVICE_NO_COHERENT_GPU_MEMORY}};
    for (unsigned i=0;i<sizeof(devices)/sizeof(devices[0]);++i) {
        int observed=deviceValid && (p->deviceObserved&devices[i].bit);
        printf("%s\"%s\":{\"observed\":%s,\"satisfied\":%s}",i?",":"",devices[i].name,jsonBool(observed),
            observed?jsonBool(p->devicePredicates&devices[i].bit):"null");
    }
    const S540PreparationPowerObservation *power=&p->power;
    const NvU32 powerKnownMask=S540_PREP_PM_OBS_READY|S540_PREP_PM_OBS_DOMAIN|S540_PREP_PM_OBS_ACTIVE|
        S540_PREP_PM_OBS_WAIT_RESULT|S540_PREP_PM_OBS_RAW_IOR|S540_PREP_PM_OBS_PROTOCOL;
    int powerValid=valid && (p->observedMask&S540_PREP_OBS_POWER) && power->format==1 &&
        power->bytes==sizeof(*power) && (power->observedMask&powerKnownMask)!=0;
    int powerFailure=powerValid && power->firstFailureStage>S540_PREP_POWER_UNOBSERVED &&
        power->firstFailureStage<=S540_PREP_POWER_FINAL_STATUS && power->firstFailureStatus!=NV_OK;
    printf("},\"power\":{\"format\":%u,\"bytes\":%u,\"valid\":%s,\"observed_mask\":%u,\"flags\":%u,"
        "\"stage\":%u,\"stage_label\":\"%s\",\"stage_valid\":%s,"
        "\"last_completed\":%u,\"last_completed_label\":\"%s\",\"last_completed_valid\":%s,"
        "\"first_failure_stage\":%u,\"first_failure_stage_label\":\"%s\",\"first_failure_status\":%u,"
        "\"first_failure_valid\":%s,\"raw_io_return\":%u,\"raw_io_return_valid\":%s,"
        "\"first_failure_raw_io_return\":%u,\"first_failure_raw_io_return_valid\":%s,"
        "\"wait_result\":%u,\"wait_result_valid\":%s,\"predicates\":{",
        power->format,power->bytes,jsonBool(powerValid),power->observedMask,power->flags,power->stage,
        powerStageLabel(power->stage),jsonBool(powerValid && power->stage>S540_PREP_POWER_UNOBSERVED &&
            power->stage<=S540_PREP_POWER_FINAL_STATUS),power->lastCompleted,powerStageLabel(power->lastCompleted),
        jsonBool(powerValid && power->lastCompleted>S540_PREP_POWER_UNOBSERVED &&
            power->lastCompleted<=S540_PREP_POWER_FINAL_STATUS),power->firstFailureStage,
        powerStageLabel(power->firstFailureStage),power->firstFailureStatus,jsonBool(powerFailure),
        power->rawIOReturn,jsonBool(powerValid && power->rawIOReturnValid==1),
        power->firstFailureRawIOReturn,jsonBool(powerFailure && power->firstFailureRawIOReturnValid==1),
        power->waitResult,jsonBool(powerValid && power->waitResultValid==1));
    const struct { const char *name;NvU32 bit; } powerPredicates[]={
        {"ready",S540_PREP_PM_OBS_READY},{"domain",S540_PREP_PM_OBS_DOMAIN},{"active",S540_PREP_PM_OBS_ACTIVE}};
    for (unsigned i=0;i<sizeof(powerPredicates)/sizeof(powerPredicates[0]);++i) {
        int observed=powerValid && (power->observedMask&powerPredicates[i].bit);
        printf("%s\"%s\":{\"observed\":%s,\"value\":%s}",i?",":"",powerPredicates[i].name,
            jsonBool(observed),observed?jsonBool(power->flags&powerPredicates[i].bit):"null");
    }
    printf("},\"protocol_flags\":{");
    const struct { const char *name;NvU32 bit; } powerFlags[]={
        {"on_requested",S540_PREP_PM_FLAG_ON_REQUESTED},{"on_set",S540_PREP_PM_FLAG_ON_SET},
        {"on_completed",S540_PREP_PM_FLAG_ON_COMPLETED},{"revoked",S540_PREP_PM_FLAG_REVOKED},
        {"ack_pending",S540_PREP_PM_FLAG_ACK_PENDING},{"ack_sent",S540_PREP_PM_FLAG_ACK_SENT},
        {"stopped",S540_PREP_PM_FLAG_STOPPED}};
    for (unsigned i=0;i<sizeof(powerFlags)/sizeof(powerFlags[0]);++i)
        printf("%s\"%s\":%s",i?",":"",powerFlags[i].name,
            powerValid && (power->observedMask&S540_PREP_PM_OBS_PROTOCOL) ?
                jsonBool(power->flags&powerFlags[i].bit):"null");
    printf("}}}");
}
static const char *runtimeStageLabel(NvU32 stage) {
    static const char *const names[]={"unobserved","request","retained","cancel-operation","owner-epoch",
        "global","global-ready","context","transaction","irq","original-adapter","returned","failed"};
    return stage<sizeof(names)/sizeof(names[0]) ? names[stage]:"unknown";
}
static void printNullableUnsigned(NvU32 value,int valid) {
    if (valid) printf("%u",value);else printf("null");
}
static void printRuntime(const S540ExperimentalRuntimeObservation *r,int snapshotValid) {
    int masksValid=!(r->attemptedMask&~S540_RUNTIME_CALL_ALL) &&
        !(r->returnedMask&~r->attemptedMask);
    int valid=snapshotValid && r->format==1 && r->bytes==sizeof(*r) && r->snapshotStatus==NV_OK && masksValid &&
        r->stage>=1 && r->stage<=12 && r->lastStage>=1 && r->lastStage<=11;
    int stageValid=valid && r->stage>=1 && r->stage<=12;
    int lastValid=valid && r->lastStage>=1 && r->lastStage<=11;
    int firstFailure=valid && r->firstStatus!=NV_OK && r->firstFailureStage>=1 && r->firstFailureStage<=11;
    printf("\"runtime\":{\"format\":%u,\"bytes\":%u,\"snapshot_status\":%u,\"valid\":%s,"
        "\"stage\":%u,\"stage_label\":\"%s\",\"stage_valid\":%s,"
        "\"last_stage\":%u,\"last_stage_label\":\"%s\",\"last_stage_valid\":%s,"
        "\"first_status\":%u,\"first_failure_stage\":%u,\"first_failure_stage_label\":\"%s\","
        "\"first_failure_valid\":%s,\"attempted_mask\":%u,\"returned_mask\":%u,\"calls\":{",
        r->format,r->bytes,r->snapshotStatus,jsonBool(valid),r->stage,runtimeStageLabel(r->stage),jsonBool(stageValid),
        r->lastStage,runtimeStageLabel(r->lastStage),jsonBool(lastValid),r->firstStatus,r->firstFailureStage,
        runtimeStageLabel(r->firstFailureStage),jsonBool(firstFailure),r->attemptedMask,r->returnedMask);
    const struct {const char *name;NvU32 bit;NV_STATUS status;} calls[]={
        {"global",S540_RUNTIME_CALL_GLOBAL,r->globalStatus},{"context",S540_RUNTIME_CALL_CONTEXT,r->contextStatus},
        {"bind",S540_RUNTIME_CALL_BIND,r->bindStatus},{"irq",S540_RUNTIME_CALL_IRQ,r->irqStatus},
        {"original_adapter",S540_RUNTIME_CALL_ORIGINAL,r->originalStatus}};
    for (unsigned i=0;i<sizeof(calls)/sizeof(calls[0]);++i) {
        int attempted=valid && (r->attemptedMask&calls[i].bit);
        int returned=valid && (r->returnedMask&calls[i].bit);
        printf("%s\"%s\":{\"attempted\":%s,\"returned\":%s,\"status\":",i?",":"",calls[i].name,
            valid?jsonBool(attempted):"null",valid?jsonBool(returned):"null");
        printNullableUnsigned(calls[i].status,returned);printf("}");
    }
    printf("},\"facts\":{");
    const struct {const char *name;NvU32 value;} facts[]={
        {"lifetime_retained",r->lifetimeRetained},{"cancellation_begun",r->cancellationBegun},
        {"owner_epoch_begun",r->ownerEpochBegun},{"global_initialized",r->globalInitialized},
        {"global_original_returned",r->globalOriginalReturned},{"any_original_entry_observed",r->originalEntered},
        {"adapter_attempted",r->adapterAttempted},{"adapter_initialized",r->adapterInitialized},
        {"adapter_original_returned",r->originalReturned},{"interrupt_installed",r->interruptInstalled},
        {"interrupt_armed",r->interruptArmed},{"cancellation_revoked",r->cancellationRevoked}};
    for (unsigned i=0;i<sizeof(facts)/sizeof(facts[0]);++i)
        printf("%s\"%s\":%s",i?",":"",facts[i].name,
            valid && facts[i].value<=1?jsonBool(facts[i].value):"null");
    printf("},\"global_original_status\":");
    printNullableUnsigned(r->globalOriginalStatus,valid && r->globalOriginalReturned==1);
    printf(",\"generation\":%llu,\"observed_host_stack_bytes\":%llu,\"required_worker_stack_bytes\":%llu,"
        "\"required_irq_stack_bytes\":%llu}",(unsigned long long)r->generation,
        (unsigned long long)r->observedHostStackBytes,(unsigned long long)r->requiredWorkerStackBytes,
        (unsigned long long)r->requiredIrqStackBytes);
}
static void printIrqSource(const S540ExperimentalIrqSourceObservation *r,int snapshotValid) {
    int valid=snapshotValid && r->format==1 && r->bytes==sizeof(*r) &&
        r->sourceProbeAttempted==1 && r->sourceProbeReturned==1;
    int selected=valid && r->sourceProbeStatus==NV_OK && r->selectedSourceValid==1 &&
        r->selectedTypeValid==1 && r->sourceCount>0 && r->sourceCount<=32 &&
        r->sourcesObserved==r->sourceCount && r->messagedSources==1 && r->selectedSource<r->sourceCount &&
        (r->selectedInterruptType&0x00010000U)!=0 && /* Pinned IOPCIDevice.h PCI-message type bit. */
        r->inventoryValid==1 && r->msiCapable==1 && r->msixCapable==0 && r->msiVectors==1;
    printf("\"irq_source\":{\"format\":%u,\"bytes\":%u,\"valid\":%s,"
        "\"probe_attempted\":%s,\"probe_returned\":%s,\"probe_status\":",
        r->format,r->bytes,jsonBool(valid),
        snapshotValid && r->format==1 && r->bytes==sizeof(*r) && r->sourceProbeAttempted<=1?
            jsonBool(r->sourceProbeAttempted):"null",
        snapshotValid && r->format==1 && r->bytes==sizeof(*r) && r->sourceProbeReturned<=1?
            jsonBool(r->sourceProbeReturned):"null");
    printNullableUnsigned(r->sourceProbeStatus,valid);
    printf(",\"source_count\":");printNullableUnsigned(r->sourceCount,valid && r->sourceCount>0);
    printf(",\"sources_observed\":");printNullableUnsigned(r->sourcesObserved,valid);
    printf(",\"messaged_sources\":");printNullableUnsigned(r->messagedSources,valid);
    printf(",\"selection_valid\":%s,\"selected_source\":",jsonBool(selected));
    printNullableUnsigned(r->selectedSource,selected);
    printf(",\"selected_interrupt_type\":");printNullableUnsigned(r->selectedInterruptType,selected);
    printf(",\"inventory_valid\":%s,\"msi_capable\":%s,\"msix_capable\":%s,\"msi_vectors\":",
        valid && r->inventoryValid<=1?jsonBool(r->inventoryValid):"null",
        valid && r->inventoryValid==1 && r->msiCapable<=1?jsonBool(r->msiCapable):"null",
        valid && r->inventoryValid==1 && r->msixCapable<=1?jsonBool(r->msixCapable):"null");
    printNullableUnsigned(r->msiVectors,valid && r->inventoryValid==1);printf("}");
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
        "\"pm_acknowledgement_authorized\":false,\"acceleration_test\":false,",
        attempted?"true":"false",(unsigned)requested,(unsigned)stopped,(unsigned)observation,s->phase,s->lastStatus,
        (unsigned long long)s->generation,(unsigned long long)s->observedKernelStackBytes,s->requestConsumed,
        s->requestRunning,s->retainedUntilReboot,s->ownerAllocated,s->providerFound,s->preparationAttempted,
        s->preparationReturned,s->preparationStatus,s->initializationAttempted,s->initializationReturned,
        s->initializationStatus,s->originalEntryObserved,s->globalInitialized,s->adapterInitialized,s->firmwareLoaded,
        s->interruptInstalled,s->interruptArmed,s->stopAttempted,s->stopReturned,s->stopStatus,s->cancellationStatus,
        s->runtimeObservationStatus,s->stopObservationStatus,s->powerRevoked,s->cancellationRevoked,s->powerAcknowledged);
    printf("\"snapshot_valid\":%s,\"snapshot_format\":%u,\"snapshot_bytes\":%u,",
        jsonBool(observation==KERN_SUCCESS),s->format,s->bytes);
    printPreparation(&s->preparation,observation==KERN_SUCCESS);printf(",");
    printStop(&s->retainedStop);printf(",");
    printRuntime(&s->runtime,observation==KERN_SUCCESS);printf(",");
    printIrqSource(&s->irqSource,observation==KERN_SUCCESS);printf("}\n");
}
int main(int argc,char **argv) {
    int run=argc==3 && !strcmp(argv[1],"--run-once") && !strcmp(argv[2],"--ack-retained-first-initialization");
    int target=argc==2 && !strcmp(argv[1],"--target");
    int stop=argc==2 && !strcmp(argv[1],"--stop");
    if (!run && !target && !stop && !(argc==2 && !strcmp(argv[1],"--snapshot"))) {
        fprintf(stderr,"Usage: experimental_ctl --target | --snapshot | --stop | --run-once --ack-retained-first-initialization\n");return 2;
    }
    if (geteuid()!=0) { fprintf(stderr,"Administrator required.\n");return 2; }
    NvU64 stack=0;
    if (!readText("kern.osversion","25G241") || !readText("kern.osrelease","25.6.0") || !readStack(&stack)) {
        fprintf(stderr,"Target build/release or actual kern.stack_size could not be confirmed.\n");return 2;
    }
    if (stack<S540_EXPERIMENTAL_REQUIRED_STACK) {
        fprintf(stderr,"Actual kern.stack_size is below this experiment's required minimum.\n");return 2;
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
    } else if (stop) {
        S540ExperimentalSnapshot output={0};size_t bytes=sizeof(output);
        stopped=IOConnectCallStructMethod(connection,S540_EXPERIMENTAL_SELECTOR_STOP,NULL,0,&output,&bytes);
        status=observe(connection,&observed);
    }
    printSnapshot(&observed,requested,stopped,status,run);
    IOServiceClose(connection);
    return status==KERN_SUCCESS && (!run || requested==KERN_SUCCESS) && (!stop || stopped==KERN_SUCCESS) ? 0:1;
}
