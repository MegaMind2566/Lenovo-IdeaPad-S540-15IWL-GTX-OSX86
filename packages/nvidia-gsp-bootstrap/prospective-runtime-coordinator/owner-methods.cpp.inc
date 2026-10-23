    // All lifecycle callers are externally serialized. Only the dispatcher
    // worker mutates runtimeState; arbitrary diagnostic readers copy its
    // separately guarded publication and never sample live C++ subobjects.
    S540ExperimentalRuntimeRequest runtimeRequest{};
    S540ExperimentalRuntimeSnapshot runtimeState{}, runtimePublished{};
    mutable NvU32 runtimeSnapshotGuard=0;
    RuntimeEntry runtimeEntry{};
    void publishRuntime() {
        NvU32 empty=0;
        if(!__atomic_compare_exchange_n(&runtimeSnapshotGuard,&empty,1U,false,
            __ATOMIC_ACQUIRE,__ATOMIC_RELAXED))return;
        runtimePublished=runtimeState;
        __atomic_store_n(&runtimeSnapshotGuard,0U,__ATOMIC_RELEASE);
    }
    S540ExperimentalRuntimeSnapshot readRuntime() const {
        S540ExperimentalRuntimeSnapshot result{};result.format=1;result.bytes=sizeof(result);
        NvU32 empty=0;
        if(!__atomic_compare_exchange_n(&runtimeSnapshotGuard,&empty,1U,false,
            __ATOMIC_ACQUIRE,__ATOMIC_RELAXED)) {result.snapshotStatus=NV_ERR_IN_USE;return result;}
        result=runtimePublished;
        __atomic_store_n(&runtimeSnapshotGuard,0U,__ATOMIC_RELEASE);
        if(!result.format){result.format=1;result.bytes=sizeof(result);result.snapshotStatus=NV_ERR_NOT_READY;}
        return result;
    }
    void runtimeStage(NvU32 stage) {
        __atomic_store_n(&runtimeEntry.stage,stage,__ATOMIC_RELEASE);
        runtimeState.stage=stage;publishRuntime();
    }
    NV_STATUS runtimeFailure(NV_STATUS status) {
        if(runtimeState.firstStatus==NV_OK)runtimeState.firstStatus=status;
        state.initializationStatus=status;
        state.quarantined=diagnosticLifetimeHeld||transport.hardwareDmaLifetimeHeld();
        runtimeStage(S540_RUNTIME_FAILED);return status;
    }
    NV_STATUS runtimeOperation() {
        const auto token=__atomic_load_n(&cancellationToken,__ATOMIC_ACQUIRE);
        S540GspCancellationSnapshot cancellation{};
        NV_STATUS status=s540GspCancellationGetSnapshot(token,&cancellation);
        if(status!=NV_OK)return status;
        runtimeState.cancellationRevoked=cancellation.revoked;
        if(!cancellation.bound||cancellation.generation!=token||cancellation.ownerThread!=thread||
           cancellation.phase!=S540_GSP_CANCEL_OPERATION||cancellation.revoked||cancellation.publicationInFlight)
            return NV_ERR_OPERATION_ABORTED;
        status=s540GspCancellationCheckState(s540GspContextState(context));
        if(status!=NV_OK)return status;
        return power.status();
    }
    NV_STATUS experimentalInitialize() {
        // A repeated RPC cannot overwrite the first attempt's observations.
        if(runtimeState.stage!=S540_RUNTIME_UNUSED)return NV_ERR_STATE_IN_USE;
        runtimeState={};runtimeState.format=1;runtimeState.bytes=sizeof(runtimeState);
        runtimeState.snapshotStatus=NV_OK;runtimeState.workerThread=thread;
        runtimeState.globalStatus=runtimeState.contextStatus=runtimeState.bindStatus=
            runtimeState.irqStatus=runtimeState.originalStatus=NV_ERR_NOT_READY;
        runtimeStage(S540_RUNTIME_REQUEST);
        if(!owned()||!state.prepared||!context||!deviceBound||diagnosticLifetimeHeld)
            return runtimeFailure(NV_ERR_INVALID_STATE);
        S540ExperimentalNativeProfile profile{};
        NV_STATUS status=s540RuntimeReadCompiledProfile(&profile);
        if(status!=NV_OK)return runtimeFailure(status);
        if(runtimeRequest.format!=1||runtimeRequest.bytes!=sizeof(runtimeRequest)||
           runtimeRequest.manualAcknowledgement!=S540_EXPERIMENTAL_MANUAL_ACK||
           !runtimeEqual(runtimeRequest.codeContractSha256,profile.codeContractSha256,32)||
           !runtimeEqual(runtimeRequest.targetBuild,profile.targetBuild,16)||
           runtimeRequest.observedHostStackBytes<16384||
           profile.workerStackBytes>runtimeRequest.observedHostStackBytes||
           profile.irqStackBytes>16384)return runtimeFailure(NV_ERR_INVALID_ARGUMENT);
        runtimeState.observedHostStackBytes=runtimeRequest.observedHostStackBytes;
        runtimeState.requiredWorkerStackBytes=profile.workerStackBytes;
        runtimeState.requiredIrqStackBytes=profile.irqStackBytes;
        NvU32 unused=0;
        if(!__atomic_compare_exchange_n(&runtimeAttemptClaim,&unused,1U,false,
            __ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE))return runtimeFailure(NV_ERR_STATE_IN_USE);
        status=retainDiagnosticLifetime();
        runtimeState.lifetimeRetained=diagnosticLifetimeHeld;
        if(status!=NV_OK)return runtimeFailure(status);
        runtimeStage(S540_RUNTIME_RETAINED);
        state.initializationRefused=false;
        const auto token=__atomic_load_n(&cancellationToken,__ATOMIC_ACQUIRE);
        status=s540GspCancellationBegin(token);if(status!=NV_OK)return runtimeFailure(status);
        runtimeState.cancellationBegun=1;runtimeStage(S540_RUNTIME_CANCEL_OPERATION);
        status=runtimeOperation();if(status!=NV_OK)return runtimeFailure(status);
        status=s540FirstTxnBeginOwner(this);if(status!=NV_OK)return runtimeFailure(status);
        runtimeState.ownerEpochBegun=1;
        S540FirstTxnHostIdentity master{};
        status=s540FirstTxnMasterIdentity(&master);if(status!=NV_OK)return runtimeFailure(status);
        if(master.owner!=this||!master.generation)return runtimeFailure(NV_ERR_INVALID_STATE);
        runtimeState.generation=master.generation;
        runtimeStage(S540_RUNTIME_OWNER_EPOCH);
        runtimeEntry.owner=this;runtimeEntry.nv=s540GspContextState(context);
        runtimeEntry.thread=thread;runtimeEntry.cancellation=token;runtimeEntry.power=&power;
        RuntimeEntry *empty=nullptr;
        if(!__atomic_compare_exchange_n(&activeRuntimeEntry,&empty,&runtimeEntry,false,
            __ATOMIC_RELEASE,__ATOMIC_ACQUIRE))return runtimeFailure(NV_ERR_STATE_IN_USE);
        runtimeStage(S540_RUNTIME_GLOBAL);
        status=runtimeOperation();if(status!=NV_OK)return runtimeFailure(status);
        S540NvidiaGlobalRmResult global{};
        runtimeState.globalStatus=s540GlobalRmInitialize(&global);
        S540FirstTxnGlobalSnapshot epoch{};
        // Diagnostic-only pull remains available when a genuine original
        // failure has made the stronger master accessor refuse. A returned
        // core call is positive entry evidence; absence remains unknown.
        status=s540FirstTxnGlobalGetSnapshot(&epoch);
        if(status==NV_OK) {
            runtimeState.globalOriginalReturned=epoch.originalReturned;
            runtimeState.globalOriginalStatus=epoch.originalStatus;
            runtimeState.originalEntered=epoch.originalReturned;
        }
        if(runtimeState.globalStatus!=NV_OK)return runtimeFailure(runtimeState.globalStatus);
        if(status!=NV_OK)return runtimeFailure(status);
        status=s540FirstTxnGlobalReadMaster(&epoch);if(status!=NV_OK)return runtimeFailure(status);
        if(epoch.owner!=this||epoch.generation!=master.generation||epoch.nv||
           epoch.state!=S540_FIRST_GLOBAL_READY||!epoch.validated||!epoch.originalReturned||
           epoch.originalStatus!=NV_OK||!global.initialized||!s540GlobalRmIsInitialized())
            return runtimeFailure(NV_ERR_INVALID_STATE);
        state.globalInitialized=true;runtimeState.globalInitialized=1;runtimeStage(S540_RUNTIME_GLOBAL_READY);
        status=runtimeOperation();if(status!=NV_OK)return runtimeFailure(status);
        runtimeStage(S540_RUNTIME_CONTEXT);
        runtimeState.contextStatus=s540GspContextPrepare(context);
        if(runtimeState.contextStatus!=NV_OK)return runtimeFailure(runtimeState.contextStatus);
        status=runtimeOperation();if(status!=NV_OK)return runtimeFailure(status);
        runtimeStage(S540_RUNTIME_TRANSACTION);
        runtimeState.bindStatus=s540GspContextBindFirstTransaction(context,token);
        if(runtimeState.bindStatus!=NV_OK)return runtimeFailure(runtimeState.bindStatus);
        status=runtimeOperation();if(status!=NV_OK)return runtimeFailure(status);
        runtimeStage(S540_RUNTIME_IRQ);
        runtimeState.irqStatus=installDiagnosticInterrupts();
        runtimeState.interruptInstalled=transport.interruptInstalled();
        runtimeState.interruptArmed=transport.interruptArmed();
        if(runtimeState.irqStatus!=NV_OK)return runtimeFailure(runtimeState.irqStatus);
        status=runtimeOperation();if(status!=NV_OK)return runtimeFailure(status);
        runtimeStage(S540_RUNTIME_ORIGINAL);
        runtimeState.originalStatus=s540GspContextInitializeAdapter(context);
        S540GspContextSnapshot facts{};s540GspContextSnapshot(context,&facts);
        runtimeState.adapterAttempted=facts.adapterAttempted;
        runtimeState.adapterInitialized=facts.adapterInitialized;
        if(facts.adapterAttempted)runtimeState.originalEntered=1;
        S540FirstTxnSnapshot first{};
        status=s540FirstTxnGetSnapshot(s540GspContextState(context),&first);
        if(status==NV_OK)runtimeState.originalReturned=first.originalReturned;
        if(runtimeState.originalStatus!=NV_OK)return runtimeFailure(runtimeState.originalStatus);
        if(status!=NV_OK)return runtimeFailure(status);
        if(!facts.adapterAttempted||!facts.adapterInitialized||!first.originalReturned||
           !first.originalExitReady||first.originalInFlight)return runtimeFailure(NV_ERR_INVALID_STATE);
        status=runtimeOperation();if(status!=NV_OK)return runtimeFailure(status);
        state.initializationStatus=NV_OK;state.adapterInitialized=true;
        runtimeStage(S540_RUNTIME_RETURNED);return NV_OK;
    }
