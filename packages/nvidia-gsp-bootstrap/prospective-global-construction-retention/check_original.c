/* SPDX-License-Identifier: MIT; CPU control endpoints, actual original types. */
#include "core/core.h"
#include "core/system.h"
#include "core/locks.h"
#include "rmapi/rmapi.h"
#include "S540NvidiaGspFirstTransaction.h"
unsigned s540GlobalEpochControlScenario;
unsigned s540GlobalEpochControlCoreReturns;
NV_STATUS s540GlobalEpochControlHookStatus;
void s540GlobalEpochControlAfterCore(void)
{
    ++s540GlobalEpochControlCoreReturns;
    if(s540GlobalEpochControlScenario==7)
        s540GlobalEpochControlHookStatus=rmapiLockAcquire(API_LOCK_FLAGS_NONE,RM_LOCK_MODULES_INIT);
    else if(s540GlobalEpochControlScenario==8)
        /* No GPU exists: the actual all-GPU call still owns its allocation
         * lock while the per-GPU ownership mask remains zero. */
        s540GlobalEpochControlHookStatus=rmGpuLocksAcquire(GPU_LOCK_FLAGS_LOCK_ALLOC,RM_LOCK_MODULES_INIT);
    else if(s540GlobalEpochControlScenario==9)
        s540GlobalEpochControlHookStatus=s540FirstTxnGlobalEnter();
}
NV_STATUS s540GlobalEpochControlStartPort(void){return portInitialize();}
NvBool s540GlobalEpochControlPortLive(void){return portIsInitialized();}

/* Actual typed byte-preservation observer; no policy or admission result. */
#include <string.h>
static unsigned char retainedSystemBytes[sizeof(OBJSYS)];
static const OBJSYS *retainedSystem;
unsigned s540ConstructionControlCaptures,s540ConstructionControlGuards;
unsigned s540ConstructionControlMismatches;
void s540ConstructionControlRetained(const void *system)
{
    ++s540ConstructionControlCaptures;
    if(retainedSystem||system!=SYS_GET_INSTANCE())++s540ConstructionControlMismatches;
    retainedSystem=system;
    memcpy(retainedSystemBytes,system,sizeof(retainedSystemBytes));
}
NvBool s540ConstructionControlBytesMatch(void)
{
    return retainedSystem&&retainedSystem==SYS_GET_INSTANCE()&&
        !memcmp(retainedSystemBytes,retainedSystem,sizeof(retainedSystemBytes));
}
void s540ConstructionControlGuard(const void *system,unsigned bit)
{
    if(system!=retainedSystem||!s540ConstructionControlBytesMatch())
        ++s540ConstructionControlMismatches;
    s540ConstructionControlGuards|=bit;
}
