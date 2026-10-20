    NV_STATUS retainedFailure(NV_STATUS status) {
        if(status==NV_OK)status=NV_ERR_INVALID_STATE;
        if(state.firstRetainedStatus==NV_OK)state.firstRetainedStatus=status;
        state.quarantined=true;state.retainedForever=true;
        state.ownsResources=true;state.cleanupComplete=false;
        if(state.globalAttempted)state.initializationStatus=status;
        else state.preparationStatus=status;
        s540FirstTxnObserveServiceRefusal(9,1,status);
        return status;
    }
    NV_STATUS retainedStop() {
        NV_STATUS status=NV_OK;
        state.prepared=false;state.retainedForever=true;
        state.ownsResources=true;state.cleanupComplete=false;
        // The actual backend must mask and drain its fixed IRQ contract.
        // Before IRQ arm, no positive GPU-mask claim is manufactured.
        if(transport.interruptInstalled()){
            status=transport.stopInterrupt();
            if(status!=NV_OK)return retainedFailure(status);
        }
        if(context){
            status=s540GspContextStopRetainedServices(context);
            if(status!=NV_OK)return retainedFailure(status);
            S540GspContextSnapshot observed{};s540GspContextSnapshot(context,&observed);
            if(observed.adapterInitialized&&!state.shutdownProtocolAttempted){
                status=s540GspContextRunRetainedShutdownProtocol(context);
                NvBool attempted=NV_FALSE,completed=NV_FALSE;
                (void)s540GspContextReadRetainedShutdown(context,&attempted,&completed);
                state.shutdownProtocolAttempted=attempted!=0;
                state.shutdownProtocolCompleted=completed!=0;
                state.shutdownProtocolStatus=status;
                if(status!=NV_OK)return retainedFailure(status);
            }
        }
        // No cancellation Finish/Unbind, device retirement drain, global or
        // Store shutdown, PM acknowledgement, worker join/destructor or free.
        // Typed protocol completion never substitutes for a DMA-stop receipt.
        state.quarantined=true;state.cleanupStatus=NV_ERR_IN_USE;
        return NV_ERR_IN_USE;
    }
