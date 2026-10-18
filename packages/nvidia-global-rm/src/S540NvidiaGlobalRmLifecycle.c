// SPDX-License-Identifier: MIT
// Compile with the reviewed global-RM namespace header and RS_STANDALONE=0.
#include "core/core.h"
#include "core/system.h"
#include "rmapi/rmapi.h"
#include "resserv/rs_server.h"
#include "S540NvidiaGlobalRm.h"
#include "S540NvidiaGlobalRmProfile.h"
#include "../../nvidia-global-rm-crypto/src/S540NvidiaGlobalCrypto.h"

extern RsServer g_resServ;
extern void RmShutdownRm(void);
static NvBool running;

static NvBool cryptoUnused(void)
{
    S540NvidiaGlobalCryptoSnapshot snapshot = {0};
    s540Global_crypto_snapshot(&snapshot);
    return snapshot.unavailable_calls == 0 &&
           snapshot.unavailable_symbol_mask == 0 && snapshot.counter_overflow == 0 &&
           snapshot.unavailable_symbol_mask_high == 0;
}

static NvBool cleanShutdown(void)
{
    S540NvidiaGlobalRmHostSnapshot host;
    s540GlobalRmHostSnapshot(&host);
    return SYS_GET_INSTANCE() == NULL && !portIsInitialized() &&
        host.originalLiveAllocations == 0 && host.originalLiveBytes == 0 &&
        host.invalidFrees == 0 && host.unavailableCalls == 0 && cryptoUnused();
}

static void inspect(S540NvidiaGlobalRmResult *out)
{
    OBJSYS *sys = SYS_GET_INSTANCE();
    S540NvidiaGlobalRmHostSnapshot host;
    NvU32 count = 0;
    RsClient *memoryExportClient = NULL;
    out->systemObject = sys != NULL;
    out->expectedChildren = 15;
    if (sys != NULL) {
        count += sys->pHalMgr != NULL;
        count += sys->pPfm != NULL;
        count += sys->pHypervisor != NULL;
        count += sys->pOS != NULL;
        count += sys->pCl != NULL;
        count += sys->pGpuMgr != NULL;
        count += sys->pGsyncMgr != NULL;
        count += sys->pGpuAcct != NULL;
        count += sys->pPlatformRequestHandler != NULL;
        count += sys->pRcDB != NULL;
        count += sys->pVmm != NULL;
        count += sys->pKernelVgpuMgr != NULL;
        count += sys->pGpuBoostMgr != NULL;
        count += sys->pFabric != NULL;
        count += sys->pGpuDb != NULL;
        out->memoryExportClient = sys->hSysMemExportClient != 0 &&
            serverGetClientUnderLock(&g_resServ, sys->hSysMemExportClient,
                                      &memoryExportClient) == NV_OK &&
            memoryExportClient != NULL && serverGetClientCount(&g_resServ) >= 1;
    }
    out->presentChildren = count;
    out->children = count == out->expectedChildren;
    out->resourceServer = g_resServ.bConstructed && g_resServ.pAllocator != NULL;
    s540GlobalRmHostSnapshot(&host);
    out->unavailableCalls = host.unavailableCalls;
    out->osServiceMask = s540GlobalRmServiceMask();
}

NV_STATUS s540GlobalRmInitialize(S540NvidiaGlobalRmResult *out)
{
    S540NvidiaGlobalRmHostSnapshot host;
    NV_STATUS status;
    if (!out) return NV_ERR_INVALID_ARGUMENT;
    *out = (S540NvidiaGlobalRmResult){0};
    out->format = 1;
#if defined(KERNEL)
    // This development module has known upstream early-allocation failure
    // blockers and an incomplete external ABI closure. Production kexts must
    // refuse before executing any original global RM code until those gates
    // are closed and the complete Darwin lifecycle is independently checked.
    return out->startupStatus = NV_ERR_NOT_READY;
#endif
    if (running) return out->startupStatus = NV_ERR_STATE_IN_USE;
    s540GlobalRmHostSnapshot(&host);
    if (!host.initialized || host.unavailableCalls || host.invalidFrees ||
        !s540GlobalRmPlatformFacts() || !cryptoUnused())
        return out->startupStatus = NV_ERR_NOT_READY;
    // Refuse before construction acquires any original global epoch. Its
    // failure path invokes RmShutdownRm, which would otherwise destroy a
    // preexisting registry even when os_registry_init refused ownership.
    status = s540GlobalRmCheckRegistryCold();
    if (status != NV_OK) return out->startupStatus = status;
    status = coreInitializeRm();
    out->startupStatus = status;
    if (status != NV_OK) {
        // The upstream constructor unwinds its partially created children.
        // Its portable runtime/registry state still requires the original RM
        // shutdown entry. Each failure stage must retain this cleanup contract.
        RmShutdownRm();
        s540GlobalRmHostSnapshot(&host);
        out->unavailableCalls = host.unavailableCalls;
        out->osServiceMask = s540GlobalRmServiceMask();
        out->cleanShutdown = cleanShutdown();
        return status;
    }
    running = NV_TRUE;
    inspect(out);
    if (!out->systemObject || !out->children || !out->resourceServer ||
        !out->memoryExportClient || out->unavailableCalls || !cryptoUnused()) {
        s540GlobalRmShutdown(out);
        return out->startupStatus = NV_ERR_INVALID_STATE;
    }
    out->initialized = NV_TRUE;
    return NV_OK;
}

void s540GlobalRmShutdown(S540NvidiaGlobalRmResult *out)
{
    S540NvidiaGlobalRmHostSnapshot host;
    if (!running) return;
    RmShutdownRm();
    running = NV_FALSE;
    s540GlobalRmHostSnapshot(&host);
    if (out) {
        out->unavailableCalls = host.unavailableCalls;
        out->osServiceMask = s540GlobalRmServiceMask();
        out->cleanShutdown = cleanShutdown();
    }
}

NvBool s540GlobalRmIsInitialized(void)
{
    return running;
}
