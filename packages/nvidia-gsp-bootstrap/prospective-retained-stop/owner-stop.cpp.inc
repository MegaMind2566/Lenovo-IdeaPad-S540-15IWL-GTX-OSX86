    void publishRetainedStop(const S540RetainedStopSnapshot &snapshot) {
        NvU32 empty = 0;
        if (!__atomic_compare_exchange_n(&retainedStopGuard, &empty, 1U, false,
            __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE)) return;
        retainedStopPublished = snapshot;
        __atomic_store_n(&retainedStopGuard, 0U, __ATOMIC_RELEASE);
    }
    S540RetainedStopSnapshot readRetainedStop() const {
        S540RetainedStopSnapshot value{}; value.format = 1; value.bytes = sizeof(value);
        NvU32 empty = 0;
        if (!__atomic_compare_exchange_n(&retainedStopGuard, &empty, 1U, false,
            __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE)) {
            value.snapshotStatus = NV_ERR_BUSY_RETRY;
            return value;
        }
        value = retainedStopPublished;
        __atomic_store_n(&retainedStopGuard, 0U, __ATOMIC_RELEASE);
        if (!value.format) {
            value.format = 1; value.bytes = sizeof(value); value.snapshotStatus = NV_ERR_NOT_READY;
        }
        return value;
    }
    NV_STATUS stopRetainedExperiment() {
        S540RetainedStopSnapshot result{};
        result.format = 1; result.bytes = sizeof(result);
        if (retainedStopAttempts != ~NvU32{0}) ++retainedStopAttempts;
        result.attempts = retainedStopAttempts;
        result.requested = result.retained = NV_TRUE;
        result.identityStatus = result.locksStatus = result.protocolStatus =
            result.closingStatus = result.servicesStatus = result.sealStatus =
            result.disableStatus = result.interruptStatus = result.shutdownStatus = NV_ERR_NOT_READY;
        state.prepared = false; state.quarantined = true;
        publishRetainedStop(result);
        auto observe = [this, &result](NV_STATUS status) {
            if (result.firstError == NV_OK && status != NV_OK) result.firstError = status;
            publishRetainedStop(result);
        };
        auto *nv = context ? s540GspContextState(context) : nullptr;
        S540FirstTxnSnapshot record{};
        result.identityStatus = nv ? s540FirstTxnGetSnapshot(nv, &record) : NV_STATUS(NV_ERR_NOT_READY);
        observe(result.identityStatus);
        if (result.identityStatus == NV_OK) {
            result.generation = record.generation;
            result.originalReturned = record.originalReturned;
            result.originalExitReady = record.originalExitReady;
            if (!record.generation || record.masterThread != thread || record.originalInFlight ||
                !record.originalReturned || !record.originalExitReady || record.inFlightFreePermits) {
                result.identityStatus = NV_ERR_NOT_READY;
                observe(result.identityStatus);
            } else {
                result.locksStatus = s540FirstTxnOriginalLocksReleased(nv);
                result.locksReleased = result.locksStatus == NV_OK;
                observe(result.locksStatus);
            }
        }
        if (result.identityStatus == NV_OK && result.locksReleased) {
            // The non-destructive original GSP shutdown protocol requires the
            // clean OP record and begins its own real cancellation CLEANUP.
            // Run before record closing/seal; never force BeginDestructive.
            result.protocolAttempted = NV_TRUE;
            result.protocolStatus = s540RetainedShutdownRun(
                s540GspContextMainStack(context), nv, &result.protocol);
            observe(result.protocolStatus);
            // The protocol can itself acquire original locks. Its real return
            // is not enough to prove that every unlock completed; pull the
            // genuine selected ownership reader again before any CPU join.
            result.locksStatus = s540FirstTxnOriginalLocksReleased(nv);
            result.locksReleased = result.locksStatus == NV_OK;
            observe(result.locksStatus);
            if (result.locksReleased) {
            result.closingStatus = s540FirstTxnBeginClosing(nv);
            observe(result.closingStatus);
            // Original-return/lock authority permits CPU joins even when the
            // cleanup clock expired or a hardware protocol refused. Each
            // checked endpoint still enforces its own actual phase/identity.
            result.servicesAttempted = NV_TRUE;
            result.servicesStatus = s540FirstTxnServicesSealAndDrain(nv, record.generation);
            result.servicesDrained = result.servicesStatus == NV_OK;
            observe(result.servicesStatus);
            result.sealStatus = s540FirstTxnSeal(nv);
            observe(result.sealStatus);
            S540GspContextSnapshot contextFacts{}; s540GspContextSnapshot(context, &contextFacts);
            if (contextFacts.adapterInitialized && !contextFacts.adapterDisabled) {
                result.disableAttempted = NV_TRUE;
                result.disableStatus = s540GspContextDisableAdapter(context);
                observe(result.disableStatus);
            }
            result.locksStatus = s540FirstTxnOriginalLocksReleased(nv);
            result.locksReleased = result.locksStatus == NV_OK;
            observe(result.locksStatus);
            if (result.locksReleased) {
            if (irqBinding.snapshot().installationAttempted) {
                result.interruptAttempted = NV_TRUE;
                result.interruptStatus = irqBinding.quiesce();
                const auto irq = irqBinding.snapshot();
                result.interruptSoftwareDrained = irq.softwareDrainStatus == NV_OK;
                result.interruptFullyDrained = irq.fullDrainStatus == NV_OK;
                observe(result.interruptStatus);
            }
            if (contextFacts.adapterInitialized && !contextFacts.adapterShutdown) {
                result.shutdownAttempted = NV_TRUE;
                result.shutdownStatus = s540GspContextShutdownAdapter(context,
                    result.interruptFullyDrained);
                observe(result.shutdownStatus);
            }
            }
            }
        }
        // No quiescence or final release is inferred from attempted stages.
        // Context, Session, global state, firmware, queues, IOVAs, PM lease and
        // module text remain held until reboot, including complete protocols.
        result.status = result.firstError != NV_OK ? result.firstError : NV_STATUS(NV_ERR_IN_USE);
        state.cleanupStatus = result.status;
        publishRetainedStop(result);
        return result.status;
    }
