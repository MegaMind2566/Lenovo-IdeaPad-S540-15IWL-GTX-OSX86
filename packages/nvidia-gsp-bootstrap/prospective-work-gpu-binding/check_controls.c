/* SPDX-License-Identifier: MIT; original bodies, strong record and real services.
 * Each case uses a fresh process because an immutable transaction has no reset.
 */
#include "parent-support.inc"
#include <pthread.h>

static void settled(S540FirstTxnSnapshot *s){
 require(s540Darwin_os_flush_work_queue(deviceQueue,NV_FALSE)==NV_OK);
 for(NvU32 i=0;i<3000;++i){require(s540FirstTxnGetSnapshot(&nv,s)==NV_OK);if(s->workActionReturned||s->firstStatus)break;usleep(1000);}
}
static void start(nv_nano_timer_t **handle){
 nv_create_nano_timer(&nv,&event.super,handle);require(*handle!=NULL);
 nv_start_nano_timer(&nv,*handle,0);
}
static void healthy(void){
 nv_nano_timer_t *handle=NULL;S540FirstTxnSnapshot s={0};setup();heldAction=1;
 expect(priv.pGpu==&gpu&&NV_GET_NV_STATE(&gpu)==&nv&&registryCalls==1,"actual attach publishes both reciprocal pointers before registry setup");
 start(&handle);require(waitFor(&actionOriginalReturned));require(s540FirstTxnGetSnapshot(&nv,&s)==NV_OK);
 expect(callbackCalls==1&&lockAcquires==1&&lockReleases==1&&workThread!=masterThread,"actual worker resolves bound GPU and runs original callback under token");
 expect(s.workAccepted==1&&s.workOriginalReturned==1&&!s.workActionReturned&&s.liveWork==1,"original wrapper completion does not release real action ownership");
 __atomic_store_n(&releaseAction,1U,__ATOMIC_RELEASE);settled(&s);
 expect(s.workActionReturned==1&&!s.liveWork&&!s.eventBorrowers&&!s.firstStatus,"real service return settles original work and event borrow");
}
static void attachDuplicate(void){
 setup();NV_SET_NV_STATE(&replacement,NULL);expect(osAttachGpu(&replacement,&nv)!=NV_OK,"replacement attach refused before original reciprocal stores");
 expect(priv.pGpu==&gpu&&NV_GET_NV_STATE(&gpu)==&nv&&!NV_GET_NV_STATE(&replacement)&&registryCalls==1,"duplicate cannot replace exact existing binding or rerun registry");
}
static void unreservedPublish(void){
 skipAttach=1;setup();expect(s540FirstTxnOriginalGpuAttachCommit(&gpu,&nv)!=NV_OK,"publication without reservation and reciprocal stores refused");
 expect(!priv.pGpu&&!NV_GET_NV_STATE(&gpu)&&!registryCalls,"failed publication cannot manufacture source stores");
}
static void foreignAttach(void){
 skipAttach=1;setup();apiOwned=0;
 expect(osAttachGpu(&gpu,&nv)!=NV_OK,"actual attach requires original API ownership");
 expect(!priv.pGpu&&!NV_GET_NV_STATE(&gpu)&&!registryCalls,"API refusal precedes both actual source writes");
}
static void queueBeforePublish(void){
 skipAttach=1;setup();nv_nano_timer_t *handle=NULL;start(&handle);usleep(10000);
 S540FirstTxnSnapshot s={0};require(s540FirstTxnGetSnapshot(&nv,&s)==NV_OK);
 expect(s.firstStatus&&!s.workAccepted&&!callbackCalls&&!lockAcquires,"real queue admission rejects work before immutable tuple publication");
 expect(s540FirstTxnGpuPrivateStateMayChange(&nv)!=NV_OK&&s.phase==S540_FIRST_RETAINED,"refusal remains sticky before producer failure free");
}
static void wrongInstance(void){
 setup();gpu.gpuInstance=1;nv_nano_timer_t *handle=NULL;start(&handle);usleep(10000);
 S540FirstTxnSnapshot s={0};require(s540FirstTxnGetSnapshot(&nv,&s)==NV_OK);
 expect(s.firstStatus&&!s.workAccepted&&!callbackCalls&&!lockAcquires,"real original work metadata cannot select another GPU instance");
}
static void resolvedGpu(unsigned mode){
 setup();holdBeforeWorker=1;nv_nano_timer_t *handle=NULL;start(&handle);require(waitFor(&workerReady));
 if(mode==0)lookupReplacement=1;else if(mode==1)lookupMissing=1;else if(mode==2)gpuToken=0;else NV_SET_NV_STATE(&gpu,NULL);
 __atomic_store_n(&releaseWorker,1U,__ATOMIC_RELEASE);require(waitFor(&actionOriginalReturned));
 S540FirstTxnSnapshot s={0};settled(&s);
 expect(s.firstStatus&&s.phase==S540_FIRST_RETAINED&&!callbackCalls,"worker revalidates actual resolved object, nv and acquired GPU token before callback");
 expect(lockAcquires==1&&lockReleases==1,"original done path releases GPU token after resolved-object refusal");
 S540GlobalRmHostRetentionSnapshot h={0};s540GlobalRmHostRetentionSnapshot(&h);
 expect(workFrees==1&&h.retiredAllocations>0,"refusal precedes original done free and real host retains allocation");
 expect(actionStatus==NV_OK&&s.workOriginalReturned==1&&s.firstStatus,"actual wrapper completion settles only call reference and preserves sticky failure");
}
static void privateGuard(void){
 setup();nv.flags|=NV_FLAG_IN_RECOVERY;RmClearPrivateState(&nv);
 expect(priv.pGpu==&gpu&&NV_GET_NV_PRIV(&nv)==&priv&&!mutationCalls,"actual recovery clear refuses before private-state mutation");
 RmFreePrivateState(&nv);
 expect(priv.pGpu==&gpu&&NV_GET_NV_PRIV(&nv)==&priv&&!mutationCalls,"actual private free refuses before registry/unregister/free");
 expect(s540FirstTxnOriginalGpuDetach(&gpu)!=NV_OK,"GPU owner without reviewed deletion policy cannot detach");
}
static void entryMetadataChanged(void){
 setup();heldAction=1;nv_nano_timer_t *handle=NULL;start(&handle);require(waitFor(&actionOriginalReturned));
 OsQueueWorkItemFlags flags={0};flags.bDontFreeParams=1;flags.bLockGpuGroupDevice=1;
 require(osQueueWorkItem(&gpu,_tmrEventServiceTimerWorkItem,&event.super,flags)==NV_OK);
 nv_work_item_t *pending=lastAllocatedWork;require(pending!=NULL);pending->gpuInstance=1;
 __atomic_store_n(&releaseAction,1U,__ATOMIC_RELEASE);
 expect(s540Darwin_os_flush_work_queue(deviceQueue,NV_FALSE)!=NV_OK,"actual queue entry rejects changed metadata after successful original production");
 S540FirstTxnSnapshot s={0};require(s540FirstTxnGetSnapshot(&nv,&s)==NV_OK);
 expect(s.workAccepted==2&&s.workOriginalReturned==1&&callbackCalls==1&&lockAcquires==1,"changed queued instance never enters second original worker or callback");
 expect(s.phase==S540_FIRST_RETAINED&&s.liveWork==1&&s.eventBorrowers>0,"entry failure retains real queued item and exact event borrow");
}
static void *refuseThread(void *unused){(void)unused;require(waitFor(&commitReady));s540FirstTxnObserveServiceRefusal(902,2,NV_ERR_NOT_SUPPORTED);__atomic_store_n(&releaseCommit,1U,__ATOMIC_RELEASE);return NULL;}
static void concurrentRefusal(void){
 skipAttach=1;setup();pauseCommit=1;
 pthread_t thread;require(pthread_create(&thread,NULL,refuseThread,NULL)==0);
 expect(osAttachGpu(&gpu,&nv)!=NV_OK,"foreign refusal between actual attach stores and publication blocks commit");
 require(pthread_join(thread,NULL)==0);
 expect(priv.pGpu==&gpu&&NV_GET_NV_STATE(&gpu)==&nv&&!registryCalls,"interrupted actual attachment retains reciprocal owners without downstream initialization");
 expect(s540FirstTxnGpuAttachReserve(&nv,&replacement,0)!=NV_OK,"failed reservation cannot be replaced in same generation");
 S540FirstTxnSnapshot s={0};require(s540FirstTxnGetSnapshot(&nv,&s)==NV_OK);
 expect(s.firstStatus==NV_ERR_NOT_SUPPORTED&&s.phase==S540_FIRST_RETAINED,"concurrent failure remains first sticky status");
}
int main(void){
 unsigned total=0,totalFailures=0;
 for(unsigned t=0;t<13;++t){int fds[2];require(pipe(fds)==0);pid_t child=fork();require(child>=0);
  if(!child){close(fds[0]);if(t==0)healthy();else if(t==1)attachDuplicate();else if(t==2)unreservedPublish();else if(t==3)foreignAttach();else if(t==4)queueBeforePublish();else if(t==5)wrongInstance();else if(t<10)resolvedGpu(t-6);else if(t==10)privateGuard();else if(t==11)concurrentRefusal();else entryMetadataChanged();unsigned r[2]={checks,failures};require(write(fds[1],r,sizeof(r))==sizeof(r));close(fds[1]);_Exit(failures?1:0);}
  close(fds[1]);unsigned r[2]={0};ssize_t n=read(fds[0],r,sizeof(r));close(fds[0]);int status;require(waitpid(child,&status,0)==child);total+=r[0];totalFailures+=r[1];
  if(n!=sizeof(r)||!WIFEXITED(status)||WEXITSTATUS(status)){++totalFailures;fprintf(stderr,"binding child %u failed: %d\n",t,status);}
 }
 printf("{\"format\":1,\"status\":\"%s\",\"cases\":13,\"checks\":%u,\"failures\":%u,\"actual_original_bodies\":15,\"real_record_services_host\":true,\"gpu_access\":false,\"hardware_admission\":false}\n",totalFailures?"failed":"passed",total,totalFailures);return totalFailures?1:0;
}
