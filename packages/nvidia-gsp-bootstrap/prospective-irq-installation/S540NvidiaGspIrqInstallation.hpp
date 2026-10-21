// SPDX-License-Identifier: MIT
#pragma once
#include "S540NvidiaGspIrqIdentity.h"
#include "../src/S540NvidiaGspContext.h"
#include "../platform/S540NvidiaGspPower.hpp"
#include "../prospective-irq-callback-closure/S540NvidiaIrqClosure.h"
#include "../prospective-irq-callback-closure/rc/S540NvidiaIrqOriginal.h"
#include "../prospective-first-transaction/record/S540NvidiaGspFirstTransaction.h"
#include "../cancellation/S540NvidiaGspCancellation.h"
#include "../../nvidia-device-transport/src/S540NvidiaDeviceTransport.hpp"
#include "../../nvidia-darwin-services/src/S540NvidiaDarwinServices.h"
#if !defined(S540_NVIDIA_IRQ_INSTALLATION) || S540_NVIDIA_IRQ_INSTALLATION != 1
#error "Explicit IRQ installation source selection required"
#endif

namespace S540NvidiaGspIrq {
class Binding;
namespace Detail { static Binding *installed; }

// Embedded in the permanent operational Impl. Never a temporary contract owner.
class Binding {
    S540GspContext *context_=nullptr;
    S540NvidiaDeviceTransport::Session *session_=nullptr;
    S540NvidiaGspPower::Lease *power_=nullptr;
    const void *retainedOwner_=nullptr;
    NvU64 thread_=0;
    S540GspCancellationToken cancellation_=0;
    S540GspIrqIdentity identity_{};
    S540GspIrqInstallationSnapshot facts_{};

    NV_STATUS checkMaster() const {
        S540FirstTxnGlobalSnapshot epoch{};NvU64 tid=0;
        if(!context_||!session_||!power_||!retainedOwner_||
           !s540Darwin_os_semaphore_may_sleep()||s540Darwin_os_get_current_thread(&tid)!=NV_OK||tid!=thread_)
            return NV_ERR_INVALID_STATE;
        NV_STATUS status=s540FirstTxnGlobalReadMaster(&epoch);if(status!=NV_OK)return status;
        if(epoch.owner!=retainedOwner_||epoch.nv!=identity_.nv||epoch.masterThread!=thread_||
           epoch.generation!=identity_.generation||!epoch.validated||epoch.state!=S540_FIRST_GLOBAL_READY)
            return NV_ERR_INVALID_STATE;
        return s540GspContextMatchIrqIdentity(context_,&identity_)?NV_OK:NV_ERR_INVALID_STATE;
    }
    NV_STATUS checkOperation() const {
        NV_STATUS status=checkMaster();if(status!=NV_OK)return status;
        S540GspCancellationSnapshot cancellation{};
        status=s540GspCancellationGetSnapshot(cancellation_,&cancellation);if(status!=NV_OK)return status;
        if(!cancellation.bound||cancellation.generation!=cancellation_||cancellation.ownerThread!=thread_||
           cancellation.phase!=S540_GSP_CANCEL_OPERATION||cancellation.revoked||cancellation.publicationInFlight)
            return NV_ERR_OPERATION_ABORTED;
        status=s540GspCancellationCheckState(identity_.nv);if(status!=NV_OK)return status;
        status=power_->status();if(status!=NV_OK)return status;
        if(!session_->active()||!session_->accessible()||!session_->hardwareDmaLifetimeHeld()||
           !facts_.hardwareDmaGeneration||session_->hardwareDmaGeneration()!=facts_.hardwareDmaGeneration||
           session_->pciHandle()!=identity_.pciHandle)return NV_ERR_INVALID_STATE;
        return NV_OK;
    }
    static NV_STATUS validate(void *opaque) {
        const auto *self=static_cast<Binding *>(opaque);
        return self&&s540GspContextMatchIrqIdentity(self->context_,&self->identity_)?NV_OK:NV_ERR_INVALID_STATE;
    }
    static bool top(void *opaque,bool &locked,bool &unlocked) {
        auto *self=static_cast<Binding *>(opaque);NvBool l=NV_FALSE,u=NV_FALSE;
        const NvBool handled=s540GspContextInterruptTop(self->context_,&l,&u);
        locked=l!=NV_FALSE;unlocked=u!=NV_FALSE;return handled!=NV_FALSE;
    }
    static void locked(void *opaque) {
        s540GspContextLockedBottomHalf(static_cast<Binding *>(opaque)->context_);
    }
    static void unlocked(void *opaque) {
        s540GspContextUnlockedBottomHalf(static_cast<Binding *>(opaque)->context_);
    }
    static NV_STATUS selectMode(void *opaque) {
        auto *self=static_cast<Binding *>(opaque);
        self->facts_.modeStatus=s540GspContextSelectMessageInterrupt(self->context_,&self->identity_);
        self->facts_.modeSelected=self->facts_.modeStatus==NV_OK;
        return self->facts_.modeStatus;
    }
    static bool ready(void *opaque) {
        const auto *self=static_cast<Binding *>(opaque);
        return self&&!self->facts_.stopAttempts&&self->facts_.modeSelected&&self->checkOperation()==NV_OK;
    }
    static NV_STATUS mask(void *opaque) {
        auto *self=static_cast<Binding *>(opaque);
        // This is called only after the real controller/action software drain.
        // The original helper independently authenticates that exclusion.
        return s540FirstTxnIrqMaskHardware(static_cast<nvidia_stack_s *>(self->identity_.mainStack),
            static_cast<nv_state_t *>(self->identity_.nv));
    }
    void observeDrain() {
        facts_.softwareDrainStatus=s540FirstTxnIrqValidateSoftwareDrained();
        facts_.fullDrainStatus=s540FirstTxnIrqValidateDrained();
    }
    void stopAfterFailure() {
        if(facts_.stopAttempts!=~NvU32{0})++facts_.stopAttempts;
        facts_.stopStatus=session_->stopInterrupt();observeDrain();
    }
public:
    Binding() {
        facts_.installStatus=facts_.modeStatus=facts_.armStatus=facts_.stopStatus=
            facts_.softwareDrainStatus=facts_.fullDrainStatus=NV_ERR_NOT_READY;
    }
    Binding(const Binding &)=delete;Binding &operator=(const Binding &)=delete;
    NV_STATUS install(S540GspContext *context,S540NvidiaDeviceTransport::Session *session,
        S540NvidiaGspPower::Lease *power,const void *retainedOwner,NvU64 thread,
        S540GspCancellationToken token) {
        if(context_||!context||!session||!power||!retainedOwner||!thread||!token)return NV_ERR_INVALID_STATE;
        S540GspIrqIdentity identity{};S540GspContextSnapshot state{};
        NV_STATUS status=s540GspContextReadIrqIdentity(context,&identity);if(status!=NV_OK)return status;
        s540GspContextSnapshot(context,&state);
        if(state.adapterAttempted||state.adapterInitialized||state.quarantined)return NV_ERR_INVALID_STATE;
        context_=context;session_=session;power_=power;retainedOwner_=retainedOwner;thread_=thread;
        cancellation_=token;identity_=identity;facts_.generation=identity.generation;
        facts_.hardwareDmaGeneration=session->hardwareDmaGeneration();
        status=checkOperation();if(status!=NV_OK)return status;
        if(session->interruptInstalled()||session->interruptArmed())return NV_ERR_IN_USE;
        Binding *empty=nullptr;
        if(!__atomic_compare_exchange_n(&Detail::installed,&empty,this,false,
            __ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE))return NV_ERR_IN_USE;
        // The immutable callback owner and original identities are published
        // before the first OS registration. A partial failure is never reset.
        const S540NvidiaDeviceTransport::InterruptContract contract{
            this,top,locked,unlocked,mask,ready,identity_.nv,selectMode,validate};
        facts_.installationAttempted=NV_TRUE;
        facts_.installStatus=session_->installInterrupt(contract);
        if(facts_.installStatus!=NV_OK)return facts_.installStatus;
        status=checkOperation();if(status!=NV_OK){stopAfterFailure();return status;}
        facts_.armStatus=session_->armInterrupt();
        if(facts_.armStatus!=NV_OK){stopAfterFailure();return facts_.armStatus;}
        // PM may revoke while enableInterrupt is running. Do not report a
        // successful installation over that real event, even if enable passed.
        status=checkOperation();if(status!=NV_OK){stopAfterFailure();return status;}
        return NV_OK;
    }
    NV_STATUS quiesce() {
        NvU64 tid=0;
        if(!context_||__atomic_load_n(&Detail::installed,__ATOMIC_ACQUIRE)!=this||
           !s540Darwin_os_semaphore_may_sleep()||s540Darwin_os_get_current_thread(&tid)!=NV_OK||tid!=thread_)
            return NV_ERR_INVALID_STATE;
        // stopInterrupt performs actual software exclusion before mask. Sticky
        // cleanup authority remains the original helper's separate prerequisite.
        stopAfterFailure();return facts_.stopStatus;
    }
    NV_STATUS checkBeforeOriginalEntry(S540GspContext *context) const {
        if(context!=context_||facts_.stopAttempts||facts_.installStatus!=NV_OK||facts_.modeStatus!=NV_OK||facts_.armStatus!=NV_OK||
           !session_->interruptInstalled()||!session_->interruptArmed())return NV_ERR_NOT_READY;
        return checkOperation();
    }
    static NV_STATUS checkInstalled(S540GspContext *context) {
        Binding *bound=__atomic_load_n(&Detail::installed,__ATOMIC_ACQUIRE);
        return bound?bound->checkBeforeOriginalEntry(context):NV_ERR_NOT_READY;
    }
    S540GspIrqInstallationSnapshot snapshot() const {
        auto result=facts_;
        result.sessionInstalled=session_&&session_->interruptInstalled();
        result.sessionArmed=session_&&session_->interruptArmed();return result;
    }
};
}
