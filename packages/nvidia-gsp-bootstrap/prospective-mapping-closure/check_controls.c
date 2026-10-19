/* SPDX-License-Identifier: MIT
 * Complete original callers, strong transaction and real mutex/queue backend.
 * GPU runtime/locks/PM actions remain explicit CPU endpoint fixtures. */
#include "parent-support.inc"
#include <pthread.h>
void s540MappingTestFailAllocation(void);
#define EXACT(name,type) _Static_assert(__builtin_types_compatible_p(__typeof__(&name),type),#name " original ABI")
EXACT(nv_acquire_mmap_lock,void (NV_API_CALL *)(nv_state_t *));
EXACT(nv_release_mmap_lock,void (NV_API_CALL *)(nv_state_t *));
EXACT(nv_get_all_mappings_revoked_locked,NvBool (NV_API_CALL *)(nv_state_t *));
EXACT(nv_set_safe_to_mmap_locked,void (NV_API_CALL *)(nv_state_t *,NvBool));
EXACT(nv_revoke_gpu_mappings,NV_STATUS (NV_API_CALL *)(nv_state_t *));

static NvU32 idleCalls, notIdleCalls, deferredCalls, powerDepth, runMapping;
static NvU32 enteredMapping, finishedMapping;
static void acquireDynamicPowerMutex(nv_priv_t *p){require(p==&priv&&!powerDepth);++powerDepth;}
static void releaseDynamicPowerMutex(nv_priv_t *p){require(p==&priv&&powerDepth==1);--powerDepth;}
static NvBool RmCanEnterGcx(OBJGPU *g){require(g==&gpu);return NV_TRUE;}
static void RmScheduleCallbackForIdlePreConditions(OBJGPU *g){require(g==&gpu);++deferredCalls;}
NV_STATUS NV_API_CALL nv_indicate_idle(nv_state_t *n){require(n==&nv);++idleCalls;return NV_OK;}
NV_STATUS NV_API_CALL nv_indicate_not_idle(nv_state_t *n){require(n==&nv);++notIdleCalls;return NV_OK;}
NvBool nv_dynamic_power_state_transition(nv_state_t *n,nv_dynamic_power_state_t old,nv_dynamic_power_state_t next){
 require(n==&nv);NvS32 expected=(NvS32)old;return __atomic_compare_exchange_n((NvS32 *)&priv.dynamic_power.state,&expected,(NvS32)next,NV_FALSE,__ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE);
}
#include "actual-mapping-callers.inc"
static void mapping_Run(void){
 if(!runMapping)return;
 __atomic_store_n(&enteredMapping,1U,__ATOMIC_RELEASE);
 control_RmIndicateIdle(0,NULL);
 __atomic_store_n(&finishedMapping,1U,__ATOMIC_RELEASE);
}
static S540FirstTxnSnapshot snapshot(void){S540FirstTxnSnapshot s={0};require(s540FirstTxnGetSnapshot(&nv,&s)==NV_OK);return s;}
static void healthy(void){
 setup();priv.dynamic_power.state=NV_DYNAMIC_POWER_STATE_IDLE_SUSTAINED;
 nv_acquire_mmap_lock(&nv);
 expect(!nv_get_all_mappings_revoked_locked(&nv),"zero-initialized mapping state is not a fabricated revocation receipt");
 nv_set_safe_to_mmap_locked(&nv,NV_TRUE);nv_release_mmap_lock(&nv);
 expect(nv_revoke_gpu_mappings(&nv)==NV_OK,"explicit revoke succeeds for the selected admitted empty user mapping set");
 nv_acquire_mmap_lock(&nv);expect(nv_get_all_mappings_revoked_locked(&nv),"revocation state persists under real lock");nv_release_mmap_lock(&nv);
 control_RmIndicateIdle(0,NULL);
 expect(idleCalls==1&&!deferredCalls&&priv.dynamic_power.state==NV_DYNAMIC_POWER_STATE_IDLE_INDICATED,"complete original idle caller observes real revoked state under mutex");
 priv.dynamic_power.deferred_idle_enabled=NV_TRUE;control_RmForceGpuNotIdle(0,NULL);
 expect(notIdleCalls==1&&deferredCalls==1&&priv.dynamic_power.state==NV_DYNAMIC_POWER_STATE_IDLE_INSTANT,"complete original wake caller takes and releases matching mapping lock");
 expect(snapshot().firstStatus==NV_OK,"genuine mapping operations preserve healthy strong record");
}
static void notRevoked(void){
 setup();priv.dynamic_power.state=NV_DYNAMIC_POWER_STATE_IDLE_SUSTAINED;
 control_RmIndicateIdle(0,NULL);
 expect(!idleCalls&&deferredCalls==1&&priv.dynamic_power.state==NV_DYNAMIC_POWER_STATE_IDLE_SUSTAINED,"original caller cannot indicate idle before explicit revocation");
 expect(snapshot().firstStatus==NV_OK,"false revoked query is ordinary state rather than refusal");
}
static void noLock(void){
 setup();expect(!nv_get_all_mappings_revoked_locked(&nv),"query without owner token returns false");
 expect(snapshot().firstStatus!=NV_OK,"unlocked query produces genuine sticky refusal");
 expect(nv_revoke_gpu_mappings(&nv)!=NV_OK,"sticky failure cannot later publish revoked state");
}
static void recursive(void){
 setup();nv_acquire_mmap_lock(&nv);nv_acquire_mmap_lock(&nv);
 expect(snapshot().firstStatus==NV_ERR_INVALID_LOCK_STATE,"recursive acquire refuses rather than deadlocking or issuing a second token");
 nv_release_mmap_lock(&nv);
 expect(snapshot().firstStatus==NV_ERR_INVALID_LOCK_STATE,"real owner release remains possible after failure and preserves refusal");
}
static void foreignNv(void){
 setup();nv_state_t foreign={0};expect(nv_revoke_gpu_mappings(&foreign)!=NV_OK,"foreign nv fails exact strong-record identity before dereference");
 expect(snapshot().firstStatus!=NV_OK,"foreign identity is sticky on retained attempt");
}
static void *releaseForeign(void *unused){(void)unused;nv_release_mmap_lock(&nv);return NULL;}
static void foreignThread(void){
 setup();nv_acquire_mmap_lock(&nv);pthread_t t;require(pthread_create(&t,NULL,releaseForeign,NULL)==0);require(pthread_join(t,NULL)==0);
 expect(snapshot().firstStatus==NV_ERR_INVALID_LOCK_STATE,"actual foreign OS thread cannot release another thread's mutex");
 nv_release_mmap_lock(&nv);
 expect(snapshot().firstStatus==NV_ERR_INVALID_LOCK_STATE,"retained real owner can release token after foreign refusal");
}
static void *acquireForeign(void *unused){(void)unused;nv_acquire_mmap_lock(&nv);return NULL;}
static void foreignAcquire(void){
 setup();pthread_t t;NvU32 before=s540DarwinLiveObjects();
 require(pthread_create(&t,NULL,acquireForeign,NULL)==0);require(pthread_join(t,NULL)==0);
 expect(snapshot().firstStatus!=NV_OK,"unadmitted actual OS thread fails genuine record authorization");
 expect(s540DarwinLiveObjects()==before,"unauthorized acquire cannot initialize or allocate a mapping mutex");
}
static void stickyHeld(void){
 setup();nv_acquire_mmap_lock(&nv);s540FirstTxnObserveServiceRefusal(900,1,NV_ERR_NOT_SUPPORTED);
 expect(!nv_get_all_mappings_revoked_locked(&nv),"held query preserves first refusal and cannot invent successful revocation");
 nv_set_safe_to_mmap_locked(&nv,NV_TRUE);nv_release_mmap_lock(&nv);
 expect(snapshot().firstStatus==NV_ERR_NOT_SUPPORTED,"setter and balanced release cannot erase earlier refusal");
}
static void callbackContended(NvBool refuseWhileBlocked){
 setup();priv.dynamic_power.state=NV_DYNAMIC_POWER_STATE_IDLE_SUSTAINED;require(nv_revoke_gpu_mappings(&nv)==NV_OK);
 nv_acquire_mmap_lock(&nv);runMapping=1;nv_nano_timer_t *handle=NULL;
 nv_create_nano_timer(&nv,&event.super,&handle);require(handle!=NULL);nv_start_nano_timer(&nv,handle,0);require(waitFor(&enteredMapping));
 usleep(10000);expect(!__atomic_load_n(&finishedMapping,__ATOMIC_ACQUIRE),"real authenticated queue callback blocks behind master mapping mutex");
 if(refuseWhileBlocked)s540FirstTxnObserveServiceRefusal(901,2,NV_ERR_NOT_SUPPORTED);
 nv_release_mmap_lock(&nv);require(waitFor(&finishedMapping));require(waitFor(&actionOriginalReturned));
 if(refuseWhileBlocked){
  expect(!idleCalls&&priv.dynamic_power.state==NV_DYNAMIC_POWER_STATE_IDLE_SUSTAINED,"blocked callback rechecks sticky refusal after acquiring the real mutex and cannot indicate idle");
  expect(snapshot().firstStatus==NV_ERR_NOT_SUPPORTED,"actual late callback preserves the earlier failure");
 }else{
  expect(idleCalls==1&&workThread!=masterThread,"actual original callback resumes and consumes real revoked state after token release");
  require(s540Darwin_os_flush_work_queue(deviceQueue,NV_FALSE)==NV_OK);
  expect(snapshot().firstStatus==NV_OK,"real callback authorization and tuple revalidation succeed under contention");
 }
}
static void allocationFailure(void){
 setup();NvU32 before=s540DarwinLiveObjects();s540MappingTestFailAllocation();
 expect(nv_revoke_gpu_mappings(&nv)==NV_ERR_NO_MEMORY,"actual Darwin storage failure refuses mapping initialization");
 expect(snapshot().firstStatus==NV_ERR_NO_MEMORY&&s540DarwinLiveObjects()==before,"failed initialization publishes no mutex and preserves real first failure");
 expect(nv_revoke_gpu_mappings(&nv)==NV_ERR_NO_MEMORY,"partial initialization has no retry or success override");
}
int main(void){
 unsigned total=0,totalFailures=0;
 for(unsigned t=0;t<11;++t){int fds[2];require(pipe(fds)==0);pid_t child=fork();require(child>=0);
  if(!child){close(fds[0]);switch(t){case 0:healthy();break;case 1:notRevoked();break;case 2:noLock();break;case 3:recursive();break;case 4:foreignNv();break;case 5:foreignThread();break;case 6:foreignAcquire();break;case 7:stickyHeld();break;case 8:callbackContended(NV_FALSE);break;case 9:callbackContended(NV_TRUE);break;default:allocationFailure();}
   unsigned r[2]={checks,failures};require(write(fds[1],r,sizeof(r))==sizeof(r));close(fds[1]);_Exit(failures?1:0);}
  close(fds[1]);unsigned r[2]={0};ssize_t n=read(fds[0],r,sizeof(r));close(fds[0]);int status;require(waitpid(child,&status,0)==child);total+=r[0];totalFailures+=r[1];
  if(n!=sizeof(r)||!WIFEXITED(status)||WEXITSTATUS(status)){++totalFailures;fprintf(stderr,"mapping child %u failed: %d\n",t,status);}}
 printf("{\"status\":\"%s\",\"checks\":%u,\"cases\":11,\"failures\":%u,\"actual_strong_record\":true,\"actual_original_callers\":2,\"real_mutex\":true,\"gpu_access\":false}\n",totalFailures?"failed":"passed",total,totalFailures);return totalFailures?1:0;
}
