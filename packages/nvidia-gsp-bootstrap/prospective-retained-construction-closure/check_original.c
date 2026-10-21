/* SPDX-License-Identifier: MIT; CPU control endpoints, actual original types. */
#include "core/core.h"
#include "core/system.h"
#include "core/locks.h"
#include "rmapi/rmapi.h"
#include "S540NvidiaGspFirstTransaction.h"
unsigned s540GlobalEpochControlScenario;
unsigned s540GlobalEpochControlCoreReturns;
NV_STATUS s540GlobalEpochControlHookStatus;
unsigned s540RetainedControlClaims,s540RetainedControlBadClaims,s540RetainedControlCleanupAfterClaim;
void s540RetainedControlClaim(const void *system,NV_STATUS failure)
{
    S540FirstTxnGlobalSnapshot view={0};
    ++s540RetainedControlClaims;
    s540FirstTxnGlobalGetSnapshot(&view);
    if(!system||SYS_GET_INSTANCE()!=system||!view.constructionRetained||
        view.retainedSystem!=system||view.constructionStatus!=failure||
        view.state!=S540_FIRST_GLOBAL_IN_CORE||view.originalReturned||
        !view.firstStatus||failure==NV_OK)++s540RetainedControlBadClaims;
}
void s540RetainedControlCleanup(unsigned site,const void *system)
{
    S540FirstTxnGlobalSnapshot view={0};
    (void)site;(void)system;
    s540FirstTxnGlobalGetSnapshot(&view);
    if(view.constructionRetained)++s540RetainedControlCleanupAfterClaim;
}
NvBool s540RetainedControlRootValid(void)
{
    S540FirstTxnGlobalSnapshot view={0};OBJSYS *sys=SYS_GET_INSTANCE();
    s540FirstTxnGlobalGetSnapshot(&view);
    return view.constructionRetained&&sys&&sys==view.retainedSystem&&
        !sys->PDB_PROP_SYS_DESTRUCTING&&
        sys->__nvoc_pbase_OBJSYS==sys&&sys->__nvoc_pbase_Object&&
        sys->__nvoc_pbase_OBJTRACEABLE;
}
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
