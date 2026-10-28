/* SPDX-License-Identifier: MIT.
 * Actual selected PCI read/write wrappers, completed-fact preboot helper and
 * OS-backend selector. Resource/configuration operations are typed CPU
 * endpoints. Two included fallback fragments contain the actual statements
 * from the missing-FHB tail and missing-upstream branch, without reimplementing
 * their policy. This is not original RM or kernel hardware execution.
 */
#include <stdio.h>
#include <string.h>
#include "S540PciTopologyFacts.h"
enum { PDB_PROP_OS_DOES_NOT_ALLOW_DIRECT_PCIE_MAPPINGS = 19,
       NV2080_CTRL_BUS_INFO_TYPE_FPCI = 7,
       NV2080_CTRL_BUS_INFO_TYPE_PCI_EXPRESS = 3 };
#define RMCFG_FEATURE_MODS_FEATURES 0
#define PCI_INVALID_DEVICEID 0xffffU
#define PCI_INVALID_VENDORID 0xffffU
#define PCI_INVALID_SUBDEVICEID 0xffffU
#define PCI_INVALID_SUBVENDORID 0xffffU
#define PCI_MAX_STACK_DEPTH 32
#define PCI_MAX_BUSES 256
#define PCI_MAX_DEVICES 32
#define PCI_MAX_FUNCTION 8
#define PCI_MAX_FUNCTIONS 8
#define PCI_MULTIFUNCTION 0x80U
#define PCI_CLASS_BRIDGE_DEV 6U
#define PCI_COMMON_CLASS_SUBCLASS 0x0aU
#define PCI_COMMON_CLASS_SUBBASECLASS_P2P 0x0604U
#define PCI_COMMON_CLASS_SUBBASECLASS_HOST 0x0600U
#define PCI_COMMON_CLASS_SUBBASECLASS_3DCTRL 0x0302U
#define PCI_COMMON_SUBSYSTEM_VENDOR_ID 0x2cU
#define PCI_COMMON_SUBSYSTEM_ID 0x2eU
#define PCI_HEADER_TYPE0_REVISION_ID 0x08U
#define PCI_HEADER_TYPE0_BASECLASS 0x0bU
#define PCI_HEADER_TYPE0_HEADER_TYPE 0x0eU
#define PCI_TYPE_1_SECONDARY_BUS_NUMBER 0x19U
#define PCI_IS_VENDORID_VALID(v) ((v)!=0U && (v)!=0xffffU)
#define NV_PRINTF(...) ((void)0)
typedef struct PciAddress {
    NvU32 domain;
    NvU8 bus, device, func;
    NvBool valid;
    void *handle;
} PciAddress;
typedef struct BusInfo { NvU16 vendorID, deviceID, subvendorID, subdeviceID; NvU8 revisionID; } BusInfo;
typedef struct BUSTOPOLOGYINFO {
    struct BUSTOPOLOGYINFO *next;
    void *handle;
    NvU32 domain;
    NvU8 bus, device, func;
    NvU16 pciSubBaseClass;
    BusInfo busInfo;
    NvU8 secBus;
    NvBool bVgaAdapter;
} BUSTOPOLOGYINFO, *PBUSTOPOLOGYINFO;
typedef struct OBJCL {
    PciAddress FHBAddr, chipsetIDBusAddr;
    BusInfo FHBBusInfo, chipsetIDInfo;
    NvU32 Chipset;
    PBUSTOPOLOGYINFO pBusTopologyInfo;
    NvS32 stackTop;
    struct { NvS16 bus; } busStack[PCI_MAX_STACK_DEPTH];
} OBJCL;
typedef struct OBJOS OBJOS;
struct OBJOS {
    NvBool (*getProperty)(OBJOS *, NvU32);
    void (*setProperty)(OBJOS *, NvU32, NvBool);
    NvBool osConfigOnly;
};
typedef struct OBJHYPERVISOR { NvBool bDetected; } OBJHYPERVISOR;
typedef struct OBJSYS { OBJCL *cl; OBJOS *os; OBJHYPERVISOR *hypervisor; } OBJSYS;
typedef struct PciPort { PciAddress addr; NvU16 VendorID, DeviceID; } PciPort;
typedef struct GpuArch { NvBool bGpuArchIsZeroFb; } GpuArch;
typedef struct OBJGPU {
    void *pOsGpuInfo;
    GpuArch *pGpuArch;
    struct { PciPort upstreamPort; } gpuClData;
} OBJGPU;
static OBJSYS *currentSys;
#define SYS_GET_INSTANCE() currentSys
#define SYS_GET_CL(sys) ((sys)->cl)
#define SYS_GET_OS(sys) ((sys)->os)
#define SYS_GET_HYPERVISOR(sys) ((sys)->hypervisor)
static unsigned checks, failures, cases, debugCalls, assertCalls;
#define EXPECT(v) do { ++checks; if (!(v)) { ++failures; fprintf(stderr, "Original PCI control line %d\n", __LINE__); } } while (0)
#define DBG_BREAKPOINT() do { ++debugCalls; } while (0)
#define NV_ASSERT(v) do { if (!(v)) ++assertCalls; } while (0)
static NV_STATUS endpointStatus;
static NvU32 endpointValue, readCalls, writeCalls, refusalCalls, lastOperation;
static NV_STATUS lastFailure, validationStatus, clStatus;
static NvU32 validationCalls, clCalls, backendCalls;
static NvBool backendReady, overwriteFailedRead;
static void *expectedNv;
static S540PciTopologyGspFacts expectedFacts;
static void *expectedHandle;
static NvU32 expectedOffset, expectedWrite;
static NvBool scanMode;
static NV_STATUS scanRead(void *, NvU32, NvU32 *);
static NvBool propertyGet(OBJOS *os, NvU32 property) {
    EXPECT(property == PDB_PROP_OS_DOES_NOT_ALLOW_DIRECT_PCIE_MAPPINGS);
    return os->osConfigOnly;
}
static void propertySet(OBJOS *os, NvU32 property, NvBool value) {
    EXPECT(property == PDB_PROP_OS_DOES_NOT_ALLOW_DIRECT_PCIE_MAPPINGS);
    EXPECT(backendReady == NV_TRUE && value == NV_TRUE);
    os->osConfigOnly = value;
}
void s540PciTopologyRecordFailure(NvU32 operation, NV_STATUS status) {
    ++refusalCalls; lastOperation = operation; lastFailure = status;
}
NvBool s540PciTopologyUsesOsConfig(const void *nv) {
    ++backendCalls; EXPECT(nv == expectedNv); return backendReady;
}
static NvBool sameReference(const S540PciTopologyReference *a,
    const S540PciTopologyReference *b) {
    return a->handle==b->handle && a->segment==b->segment && a->bus==b->bus &&
        a->device==b->device && a->function==b->function && a->reserved==0 &&
        a->vendor==b->vendor && a->deviceId==b->deviceId;
}
NV_STATUS s540PciTopologyValidateForGsp(const void *nv,
    const S540PciTopologyGspFacts *facts) {
    ++validationCalls; EXPECT(nv == expectedNv);
    EXPECT(facts->format==1 && facts->bytes==sizeof(expectedFacts));
    EXPECT(sameReference(&facts->fhb,&expectedFacts.fhb));
    EXPECT(sameReference(&facts->chipset,&expectedFacts.chipset));
    EXPECT(sameReference(&facts->upstream,&expectedFacts.upstream));
    return validationStatus;
}
static NV_STATUS readValue(void *handle, NvU32 offset) {
    ++readCalls;
    if(scanMode)return scanRead(handle,offset,&endpointValue);
    EXPECT(handle == expectedHandle && offset == expectedOffset);
    return endpointStatus;
}
static NV_STATUS os_pci_read_byte(void *handle, NvU32 offset, NvU8 *value) {
    NV_STATUS status = readValue(handle, offset);
    if (status == NV_OK || overwriteFailedRead) *value = (NvU8)endpointValue;
    return status;
}
static NV_STATUS os_pci_read_word(void *handle, NvU32 offset, NvU16 *value) {
    NV_STATUS status = readValue(handle, offset);
    if (status == NV_OK || overwriteFailedRead) *value = (NvU16)endpointValue;
    return status;
}
static NV_STATUS os_pci_read_dword(void *handle, NvU32 offset, NvU32 *value) {
    NV_STATUS status = readValue(handle, offset);
    if (status == NV_OK || overwriteFailedRead) *value = endpointValue;
    return status;
}
static NV_STATUS writeValue(void *handle, NvU32 offset, NvU32 value) {
    ++writeCalls; EXPECT(handle == expectedHandle && offset == expectedOffset);
    EXPECT(value == expectedWrite); return endpointStatus;
}
static NV_STATUS os_pci_write_byte(void *h, NvU32 o, NvU8 v) { return writeValue(h, o, v); }
static NV_STATUS os_pci_write_word(void *h, NvU32 o, NvU16 v) { return writeValue(h, o, v); }
static NV_STATUS os_pci_write_dword(void *h, NvU32 o, NvU32 v) { return writeValue(h, o, v); }
static NV_STATUS clInitPcie(OBJGPU *gpu, OBJCL *cl) {
    ++clCalls; EXPECT(gpu->pOsGpuInfo == expectedNv && cl == currentSys->cl);
    EXPECT(currentSys->os && currentSys->os->osConfigOnly == NV_TRUE);
    return clStatus;
}
static NvU32 gpuGetBusIntfType_HAL(OBJGPU *gpu) {
    EXPECT(gpu->pOsGpuInfo == expectedNv); return NV2080_CTRL_BUS_INFO_TYPE_PCI_EXPRESS;
}
#include "actual-original.inc"
typedef struct ScanNode {
    NvU8 bus, device, function, header, secondary, revision;
    NvU16 vendor, deviceId, classSub;
} ScanNode;
static ScanNode scanNodes[3];
static NvU32 scanNodeCount, scanLookups, scanReadCalls, scanReadUnknown;
static BUSTOPOLOGYINFO scanPool[16];
static NvU32 scanPoolUsed, scanPoolLimit, scanFrees, timeoutResets;
static void *osPciInitHandle(NvU32 domain,NvU8 bus,NvU8 device,NvU8 function,
    NvU16 *vendor,NvU16 *deviceId) {
    ++scanLookups;*vendor=*deviceId=0;
    if(domain!=0)return NULL;
    /* Typed bounded-table endpoint: match precedes all config reads. */
    for(NvU32 n=0;n<scanNodeCount;++n) {
        ScanNode *node=&scanNodes[n];
        if(node->bus==bus && node->device==device && node->function==function) {
            *vendor=node->vendor;*deviceId=node->deviceId;return node;
        }
    }
    return NULL;
}
static NV_STATUS scanRead(void *handle,NvU32 offset,NvU32 *value) {
    for(NvU32 n=0;n<scanNodeCount;++n)if(handle==&scanNodes[n]) {
        ScanNode *node=&scanNodes[n];++scanReadCalls;
        if(offset==PCI_COMMON_CLASS_SUBCLASS)*value=node->classSub;
        else if(offset==PCI_HEADER_TYPE0_BASECLASS)*value=node->classSub>>8;
        else if(offset==PCI_HEADER_TYPE0_HEADER_TYPE)*value=node->header;
        else if(offset==PCI_TYPE_1_SECONDARY_BUS_NUMBER)*value=node->secondary;
        else if(offset==PCI_HEADER_TYPE0_REVISION_ID)*value=node->revision;
        else *value=0;
        return NV_OK;
    }
    ++scanReadUnknown;return NV_ERR_INVALID_ARGUMENT;
}
static void *portMemAllocNonPaged(NvU64 bytes) {
    EXPECT(bytes==sizeof(BUSTOPOLOGYINFO));
    return scanPoolUsed<scanPoolLimit?&scanPool[scanPoolUsed++]:NULL;
}
static void portMemSet(void *target,NvU8 value,NvU64 bytes) { memset(target,value,(size_t)bytes); }
static void portMemFree(void *target) {
    NvBool matched=NV_FALSE;
    for(NvU32 i=0;i<scanPoolUsed;++i)if(target==&scanPool[i])matched=NV_TRUE;
    EXPECT(matched);++scanFrees;
}
static void threadStateResetTimeout(void *thread) { EXPECT(thread==NULL);++timeoutResets; }
#define clFreeBusTopologyCache clFreeBusTopologyCache_IMPL
#include "actual-topology-scan.inc"
static void initializeScan(OBJCL *cl) {
    memset(cl,0,sizeof(*cl));memset(scanPool,0,sizeof(scanPool));
    scanNodeCount=3;scanLookups=scanReadCalls=scanReadUnknown=0;
    scanPoolUsed=scanFrees=timeoutResets=0;scanPoolLimit=16;
    scanNodes[0]=(ScanNode){0,0,0,0,0,1,0x8086U,0x5914U,0x0600U};
    /* Function zero is deliberately outside the allowlist. */
    scanNodes[1]=(ScanNode){0,28,2,1,2,2,0x8086U,0x9d12U,0x0604U};
    scanNodes[2]=(ScanNode){2,0,0,0,0,0xa1,0x10deU,0x1f91U,0x0300U};
    scanMode=NV_TRUE;endpointStatus=NV_OK;
}
static NvU32 cachedNodes(const OBJCL *cl) {
    NvU32 count=0;
    for(PBUSTOPOLOGYINFO p=cl->pBusTopologyInfo;p;p=p->next) {
        EXPECT(count<3);++count;
        if(p->pciSubBaseClass==0x0604U) {
            EXPECT(p->bus==0 && p->device==28 && p->func==2 && p->secBus==2);
            EXPECT(p->handle==&scanNodes[1] && p->busInfo.vendorID==0x8086U);
        }
        if(p->pciSubBaseClass==0x0300U)EXPECT(p->bus==2 && p->handle==&scanNodes[2]);
    }
    return count;
}
static NV_STATUS actualMissingFhb(OBJCL *pCl) {
#include "actual-missing-fhb.inc"
}
static NvBool actualMissingUpstream(OBJGPU *pGpu) {
    void *handle = NULL;
#include "actual-missing-upstream.inc"
    return NV_TRUE;
}
static S540PciTopologyReference reference(PciAddress address, BusInfo info) {
    S540PciTopologyReference out = {0};
    out.handle=address.handle;out.segment=address.domain;out.bus=address.bus;
    out.device=address.device;out.function=address.func;
    out.vendor=info.vendorID;out.deviceId=info.deviceID;return out;
}
int main(void) {
    int nv, fhbHandle, upstreamHandle, chipHandle;
    expectedNv=&nv;expectedHandle=&upstreamHandle;expectedOffset=0x1a;
    endpointValue=0x12345678U;
    for (unsigned width=1;width<=3;++width) {
        ++cases;endpointStatus=NV_OK;unsigned before=refusalCalls;
        NvU32 result=width==1?osPciReadByte(expectedHandle,expectedOffset):
            width==2?osPciReadWord(expectedHandle,expectedOffset):osPciReadDword(expectedHandle,expectedOffset);
        EXPECT(result==(width==1?0x78U:width==2?0x5678U:0x12345678U));
        EXPECT(refusalCalls==before);
        for(unsigned overwrite=0;overwrite<2;++overwrite) {
            ++cases;overwriteFailedRead=(NvBool)overwrite;endpointStatus=NV_ERR_INVALID_STATE;before=refusalCalls;
            result=width==1?osPciReadByte(expectedHandle,expectedOffset):
                width==2?osPciReadWord(expectedHandle,expectedOffset):osPciReadDword(expectedHandle,expectedOffset);
            EXPECT(result==(width==1?0xffU:width==2?0xffffU:0xffffffffU));
            EXPECT(refusalCalls==before+1 && lastOperation==width && lastFailure==NV_ERR_INVALID_STATE);
        }
        ++cases;endpointStatus=NV_OK;before=refusalCalls;
        endpointValue=0xffffffffU;
        result=width==1?osPciReadByte(expectedHandle,expectedOffset):
            width==2?osPciReadWord(expectedHandle,expectedOffset):osPciReadDword(expectedHandle,expectedOffset);
        EXPECT(result==(width==1?0xffU:width==2?0xffffU:0xffffffffU));EXPECT(refusalCalls==before);
        endpointValue=0x12345678U;
        for(unsigned fail=0;fail<2;++fail) {
            ++cases;endpointStatus=fail?NV_ERR_NOT_SUPPORTED:NV_OK;before=refusalCalls;
            expectedWrite=width==1?0xa5U:width==2?0xa55aU:0x87654321U;
            if(width==1)osPciWriteByte(expectedHandle,expectedOffset,(NvU8)expectedWrite);
            else if(width==2)osPciWriteWord(expectedHandle,expectedOffset,(NvU16)expectedWrite);
            else osPciWriteDword(expectedHandle,expectedOffset,expectedWrite);
            EXPECT(refusalCalls==before+fail);
            if(fail)EXPECT(lastOperation==width+3 && lastFailure==NV_ERR_NOT_SUPPORTED);
        }
    }
    EXPECT(readCalls==12 && writeCalls==6);
    OBJCL cl = {0};OBJOS os={propertyGet,propertySet,NV_TRUE};
    OBJSYS sys={&cl,&os,NULL};currentSys=&sys;
    OBJGPU gpu={0};gpu.pOsGpuInfo=expectedNv;
    cl.FHBAddr=(PciAddress){0x42U,0,0,0,NV_TRUE,&fhbHandle};
    cl.chipsetIDBusAddr=(PciAddress){0x42U,0,0,0,NV_TRUE,&chipHandle};
    cl.FHBBusInfo=(BusInfo){0x8086U,0x5914U,0,0,0};
    cl.chipsetIDInfo=(BusInfo){0x8086U,0x5914U,0,0,0};
    /* The selected generic chipset is not rejected as unrecognized. */
    cl.Chipset=0;
    gpu.gpuClData.upstreamPort.addr=(PciAddress){0x42U,0,28,2,NV_TRUE,&upstreamHandle};
    gpu.gpuClData.upstreamPort.VendorID=0x8086U;gpu.gpuClData.upstreamPort.DeviceID=0x9d12U;
    expectedFacts.format=1;expectedFacts.bytes=sizeof(expectedFacts);
    expectedFacts.fhb=reference(cl.FHBAddr,cl.FHBBusInfo);
    expectedFacts.chipset=reference(cl.chipsetIDBusAddr,cl.chipsetIDInfo);
    expectedFacts.upstream=reference(gpu.gpuClData.upstreamPort.addr,
        (BusInfo){gpu.gpuClData.upstreamPort.VendorID,gpu.gpuClData.upstreamPort.DeviceID,0,0,0});
    ++cases;validationStatus=NV_OK;EXPECT(_s540RequirePciTopology(&gpu)==NV_OK && validationCalls==1);
    ++cases;validationStatus=NV_ERR_OPERATING_SYSTEM;
    EXPECT(_s540RequirePciTopology(&gpu)==NV_ERR_OPERATING_SYSTEM && validationCalls==2);
    validationStatus=NV_OK;
    for(unsigned bad=0;bad<10;++bad) {
        ++cases;unsigned before=validationCalls;PciAddress *address=NULL;
        if(bad==0){EXPECT(_s540RequirePciTopology(NULL)==NV_ERR_NOT_SUPPORTED);}
        else if(bad==1){currentSys=NULL;EXPECT(_s540RequirePciTopology(&gpu)==NV_ERR_NOT_SUPPORTED);currentSys=&sys;}
        else if(bad==2){sys.cl=NULL;EXPECT(_s540RequirePciTopology(&gpu)==NV_ERR_NOT_SUPPORTED);sys.cl=&cl;}
        else if(bad==3){sys.os=NULL;EXPECT(_s540RequirePciTopology(&gpu)==NV_ERR_NOT_SUPPORTED);sys.os=&os;}
        else if(bad==4){os.osConfigOnly=NV_FALSE;EXPECT(_s540RequirePciTopology(&gpu)==NV_ERR_NOT_SUPPORTED);os.osConfigOnly=NV_TRUE;}
        else {
            address=bad<7?&cl.FHBAddr:bad<9?&cl.chipsetIDBusAddr:&gpu.gpuClData.upstreamPort.addr;
            if(bad==5||bad==7||bad==9){address->valid=NV_FALSE;EXPECT(_s540RequirePciTopology(&gpu)==NV_ERR_NOT_SUPPORTED);address->valid=NV_TRUE;}
            else {void *saved=address->handle;address->handle=NULL;EXPECT(_s540RequirePciTopology(&gpu)==NV_ERR_NOT_SUPPORTED);address->handle=saved;}
        }
        EXPECT(validationCalls==before);
    }
    ++cases;void *saved=gpu.gpuClData.upstreamPort.addr.handle;
    gpu.gpuClData.upstreamPort.addr.handle=NULL;unsigned before=validationCalls;
    EXPECT(_s540RequirePciTopology(&gpu)==NV_ERR_NOT_SUPPORTED && validationCalls==before);
    gpu.gpuClData.upstreamPort.addr.handle=saved;
    ++cases;backendReady=NV_TRUE;clStatus=NV_ERR_TIMEOUT;os.osConfigOnly=NV_FALSE;
    EXPECT(osInitScalability(&gpu)==NV_ERR_TIMEOUT && clCalls==1 && os.osConfigOnly==NV_TRUE);
    ++cases;backendReady=NV_FALSE;os.osConfigOnly=NV_FALSE;
    EXPECT(osInitScalability(&gpu)==NV_ERR_NOT_SUPPORTED && clCalls==1 && os.osConfigOnly==NV_FALSE);
    ++cases;sys.os=NULL;before=backendCalls;
    EXPECT(osInitScalability(&gpu)==NV_ERR_NOT_SUPPORTED && clCalls==1 && backendCalls==before);sys.os=&os;
    ++cases;sys.cl=NULL;before=backendCalls;
    EXPECT(osInitScalability(&gpu)==NV_ERR_NOT_SUPPORTED && clCalls==1 && backendCalls==before);sys.cl=&cl;
    ++cases;EXPECT(actualMissingFhb(&cl)==NV_ERR_NOT_SUPPORTED);
    EXPECT(cl.FHBAddr.valid==NV_FALSE && cl.FHBAddr.handle==NULL);
    EXPECT(cl.FHBBusInfo.vendorID==0xffffU && cl.FHBBusInfo.deviceID==0xffffU);
    EXPECT(debugCalls==1 && assertCalls==1);
    ++cases;EXPECT(actualMissingUpstream(&gpu)==NV_FALSE);
    EXPECT(gpu.gpuClData.upstreamPort.addr.valid==NV_FALSE && gpu.gpuClData.upstreamPort.addr.handle==NULL);
    EXPECT(gpu.gpuClData.upstreamPort.VendorID==0xffffU && gpu.gpuClData.upstreamPort.DeviceID==0xffffU);
    EXPECT(debugCalls==2);
    ++cases;initializeScan(&cl);
    EXPECT(clStoreBusTopologyCache_IMPL(&gpu,&cl,0,3,NV_FALSE)==NV_OK);
    EXPECT(cachedNodes(&cl)==3 && !scanReadUnknown && scanReadCalls>0);
    EXPECT(scanLookups>700 && scanLookups<=3*32*8 && timeoutResets==1);
    NvU32 lookupsBefore=scanLookups,readsBefore=scanReadCalls;
    ++cases;EXPECT(clStoreBusTopologyCache_IMPL(&gpu,&cl,0,3,NV_FALSE)==NV_OK);
    EXPECT(scanLookups==lookupsBefore && scanReadCalls==readsBefore);
    ++cases;initializeScan(&cl);
    EXPECT(clStoreBusTopologyCache_IMPL(&gpu,&cl,0,3,NV_TRUE)==NV_OK);
    EXPECT(cachedNodes(&cl)==3 && !scanReadUnknown && scanReadCalls>0);
    EXPECT(scanLookups==2*32*8 && timeoutResets==1);
    ++cases;initializeScan(&cl);scanNodeCount=0;
    EXPECT(clStoreBusTopologyCache_IMPL(&gpu,&cl,0,PCI_MAX_BUSES,NV_FALSE)==NV_OK);
    EXPECT(scanLookups==256*32*8 && !scanReadCalls && !scanReadUnknown);
    EXPECT(!scanPoolUsed && !cl.pBusTopologyInfo && timeoutResets==1);
    ++cases;initializeScan(&cl);scanNodeCount=0;
    EXPECT(clStoreBusTopologyCache_IMPL(&gpu,&cl,0,PCI_MAX_BUSES,NV_TRUE)==NV_OK);
    EXPECT(scanLookups==32*8 && !scanReadCalls && !scanReadUnknown);
    EXPECT(!scanPoolUsed && !cl.pBusTopologyInfo && timeoutResets==1);
    ++cases;initializeScan(&cl);scanPoolLimit=1;
    EXPECT(clStoreBusTopologyCache_IMPL(&gpu,&cl,0,3,NV_FALSE)==NV_ERR_INSUFFICIENT_RESOURCES);
    EXPECT(!cl.pBusTopologyInfo && scanFrees==1 && !scanReadUnknown);
    ++cases;initializeScan(&cl);scanPoolLimit=1;
    EXPECT(clStoreBusTopologyCache_IMPL(&gpu,&cl,0,3,NV_TRUE)==NV_ERR_INSUFFICIENT_RESOURCES);
    EXPECT(!cl.pBusTopologyInfo && scanFrees==1 && !scanReadUnknown);
    scanMode=NV_FALSE;
    printf("{\"status\":\"passed-actual-pci-original-producer-controls\",\"cases\":%u,\"checks\":%u,\"failures\":%u}\n",cases,checks,failures);
    return failures?1:0;
}
