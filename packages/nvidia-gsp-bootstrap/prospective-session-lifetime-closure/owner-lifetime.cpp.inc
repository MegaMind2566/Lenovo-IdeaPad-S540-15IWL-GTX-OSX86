    NV_STATUS retainDiagnosticLifetime() {
        if (!owned() || !state.prepared || !context || !deviceBound)
            return NV_ERR_INVALID_STATE;
        if (diagnosticLifetimeHeld) return NV_ERR_STATE_IN_USE;
        S540GspContextSnapshot facts{};
        s540GspContextSnapshot(context, &facts);
        if (facts.adapterAttempted || facts.adapterInitialized || facts.quarantined)
            return NV_ERR_INVALID_STATE;
        const auto token = __atomic_load_n(&cancellationToken, __ATOMIC_ACQUIRE);
        S540GspCancellationSnapshot cancellation{};
        NV_STATUS status = s540GspCancellationGetSnapshot(token, &cancellation);
        if (status != NV_OK) return status;
        if (!cancellation.bound || cancellation.ownerThread != thread ||
            cancellation.phase != S540_GSP_CANCEL_IDLE || cancellation.revoked ||
            cancellation.publicationInFlight || power.status() != NV_OK)
            return NV_ERR_NOT_READY;
        status = s540ReserveDiagnosticModulePin();
        if (status != NV_OK) return status;
        status = S540NvidiaDeviceTransport::beginRmHardwareDma(&transport);
        if (!transport.hardwareDmaLifetimeHeld()) {
            s540CancelDiagnosticModuleReservation();
            return status == NV_OK ? NV_STATUS(NV_ERR_INVALID_STATE) : status;
        }
        // This exact stable Impl owns Session, Context, dispatcher, PM, platform,
        // immutable firmware, snapshot guard and all live service bindings.
        // Keep every member and this image text after acquisition, even when a
        // real PM revocation races the successful acquisition below.
        diagnosticLifetimeHeld = true;
        if (status != NV_OK) return status;
        if (power.status() != NV_OK) return NV_ERR_NOT_READY;
        status = s540GspCancellationGetSnapshot(token, &cancellation);
        if (status != NV_OK) return status;
        return cancellation.revoked || cancellation.publicationInFlight ?
            NV_STATUS(NV_ERR_NOT_READY) : NV_STATUS(NV_OK);
    }
