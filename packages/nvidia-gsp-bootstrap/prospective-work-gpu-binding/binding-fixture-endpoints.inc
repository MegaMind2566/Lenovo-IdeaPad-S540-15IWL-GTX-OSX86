/* SPDX-License-Identifier: MIT
 * Endpoint-only CPU fixtures. Real bodies below retain reciprocal pointer
 * stores, failure ordering and real service/record calls without substitutions.
 */
static NvBool fixtureApiOwned(void){
 ++apiQueryCount;
 if(pauseCommit&&apiQueryCount==2){__atomic_store_n(&commitReady,1U,__ATOMIC_RELEASE);require(waitFor(&releaseCommit));}
 return apiOwned!=0;
}
static NvU32 fixtureGpuOwnedMask(void){return lockDepth&&gpuToken?1U:0U;}
static void fixtureRegistry(OBJGPU *g){require(g==&gpu);++registryCalls;
 if(attachRefusal)s540FirstTxnObserveServiceRefusal(901,1,NV_ERR_NOT_SUPPORTED);}
static void fixtureMutation(void){++mutationCalls;}
static void fixturePrivateFree(void *p){(void)p;fixtureMutation();}
static void *fixtureMemSet(void *p,NvU8 c,NvLength n){fixtureMutation();return __builtin_memset(p,c,n);}
#undef rmapiLockIsOwner
#define rmapiLockIsOwner fixtureApiOwned
#undef rmGpuLocksGetOwnedMask
#define rmGpuLocksGetOwnedMask fixtureGpuOwnedMask
#define initUnixSpecificRegistry fixtureRegistry
#undef initVGXSpecificRegistry
#define initVGXSpecificRegistry(g) ((void)(g),impossible())
#undef os_is_vgx_hyper
#define os_is_vgx_hyper() NV_FALSE
#undef portMemSet
#define portMemSet fixtureMemSet
#undef gpumgrUnregisterGpuId
#define gpumgrUnregisterGpuId(id) ((void)(id),fixtureMutation())
#undef kvgpumgrDetachGpu
#define kvgpumgrDetachGpu(id) ((void)(id),fixtureMutation())
#undef RmDestroyRegistry
#define RmDestroyRegistry(n) ((void)(n),fixtureMutation())
#undef os_free_mem
#define os_free_mem fixturePrivateFree
