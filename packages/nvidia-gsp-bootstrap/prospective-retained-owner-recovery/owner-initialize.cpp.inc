    NV_STATUS initialize() {
        if(!state.prepared||state.globalAttempted)return NV_ERR_INVALID_STATE;
        state.initializationRefused=true;
        if(power.status()!=NV_OK)return retainedFailure(NV_ERR_NOT_READY);
        // The real lifecycle retains its immutable kernel-entry gate.
        S540NvidiaGlobalRmResult global{};state.globalAttempted=true;
        NV_STATUS status=s540GlobalRmInitialize(&global);
        state.globalInitialized=s540GlobalRmIsInitialized()!=0;
        if(status!=NV_OK)return retainedFailure(status);
        S540FirstTxnGlobalSnapshot epoch{};
        status=s540FirstTxnGlobalReadMaster(&epoch);
        if(status!=NV_OK||epoch.nv||epoch.generation!=state.ownerGeneration||
            epoch.state!=S540_FIRST_GLOBAL_READY||!epoch.originalReturned||
            !epoch.validated||epoch.originalStatus!=NV_OK)
            return retainedFailure(status==NV_OK?NV_ERR_INVALID_STATE:status);
        // ContextBind alone binds both the strong nv and its real services.
        status=s540GspContextBindFirstTransaction(context,cancellationToken);
        if(status!=NV_OK)return retainedFailure(status);
        state.firstTransactionBound=true;
        status=s540ControlStateBindAdapter(s540GspContextState(context));
        if(status!=NV_OK)return retainedFailure(status);
        state.privatePreparationAttempted=true;
        status=s540GspContextPrepare(context);
        if(status!=NV_OK)return retainedFailure(status);
        state.privatePrepared=true;
        state.irqPreparationAttempted=true;
        status=s540GspIrqInstall(context);
        if(status!=NV_OK)return retainedFailure(status);
        // Host copies/Store persist. OSINIT's actual failure hook retains
        // its own firmware lease handles during the real original attempt.
        if(kBlockedGates){
            state.initializationStatus=NV_ERR_NOT_SUPPORTED;
            state.quarantined=true;state.retainedForever=true;
            return NV_ERR_NOT_SUPPORTED;
        }
        state.adapterEntryAttempted=true;
        status=s540GspContextInitializeAdapter(context);
        state.initializationStatus=status;
        if(status!=NV_OK)return retainedFailure(status);
        state.initializationRefused=false;
        return NV_OK;
    }
