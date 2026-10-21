    {
        S540NvidiaGspBootstrap::Owner owner; ResourceFixture fixture;
        expect(owner.prepareNativeForTest(&provider, backend(fixture), images) == NV_OK,
            "hold acquisition failure case uses actual prepared Owner/Session");
        fixture.active = false; // Explicit real backend liveness failure endpoint.
        expect(owner.retainDiagnosticLifetime() == NV_ERR_INVALID_STATE,
            "real Session refuses acquisition after backend liveness loss");
        expect(!s540GspDiagnosticLifetimePinCount() && !owner.retainedDiagnosticOwner() &&
            !owner.snapshot().diagnosticLifetimeRetained && !owner.snapshot().hardwareDmaLifetimeHeld,
            "failed preacquisition releases reservation without inventing a hardware hold");
        fixture.active = true;
        expect(owner.stop() == NV_OK && !fixture.active,
            "failed acquisition keeps ordinary preoriginal cleanup available");
        expectCold();
    }
    {
        // The real owner intentionally outlives its public facade and this test.
        auto *owner = new S540NvidiaGspBootstrap::Owner;
        auto *fixture = new ResourceFixture;
        expect(owner->prepareNativeForTest(&provider, backend(*fixture), images) == NV_OK,
            "permanent case prepares actual context, PM, Session, Store and timer bindings");
        expect(!s540GspDiagnosticLifetimePinCount() && !owner->retainedDiagnosticOwner(),
            "an ordinary prepared session does not pretend to hold permanent image lifetime");
        const NvU64 worker = owner->snapshot().workerThread;
        NV_STATUS status = NV_ERR_NOT_READY;
        std::thread foreign([&] { status = owner->retainDiagnosticLifetime(); });
        foreign.join();
        auto state = owner->snapshot();
        expect(status == NV_OK && state.workerThread == worker && state.diagnosticLifetimeRetained &&
            state.hardwareDmaLifetimeHeld && state.hardwareDmaGeneration && owner->retainedDiagnosticOwner() &&
            s540GspDiagnosticLifetimePinCount() == 1,
            "foreign caller acquires real exact session hold on persistent ordinary owner worker");
        expect(owner->retainDiagnosticLifetime() == NV_ERR_STATE_IN_USE &&
            s540GspDiagnosticLifetimePinCount() == 1,
            "duplicate lifetime acquisition cannot inflate the permanent module count");
        expect(owner->initialize() == NV_ERR_NOT_SUPPORTED && owner->snapshot().blockedGates == 15,
            "permanent ownership leaves every original entry gate closed");
        RetainedPageFixture page;
        expect(owner->runNativeForTest(retireDiagnosticPage, &page) == NV_OK,
            "actual bound Session retains page backing and device mapping after logical retirement");
        expect(owner->stop() == NV_ERR_IN_USE,
            "core stop refuses before any context, service, transport, host or PM release");
        state = owner->snapshot();
        expect(state.workerActive && state.ownsResources && state.quarantined && state.hostInitialized &&
            state.platformBound && state.transportBound && state.firmwareBound && state.timersBound &&
            !state.cleanupComplete && fixture->active && fixtureState &&
            !fixture->released && !fixture->unmapped && page.bytes[0] == 0x5a,
            "retained stop preserves real outer owners, readable page backing and mapping");
        expect(owner->revokePowerNativeForTest() == NV_OK &&
            owner->runNativeForTest(inspect, nullptr) == NV_OK,
            "actual guarded PM producer publishes cancellation before queued stop runs");
        state = owner->snapshot();
        expect(state.powerRevoked && state.cancellationRevoked && state.cancellationBound &&
            state.powerRevokedAtNs && state.cancellationDeadlineNs == state.powerRevokedAtNs + 30000000000ULL &&
            !state.powerAcknowledged && state.diagnosticLifetimeRetained && state.hardwareDmaLifetimeHeld &&
            state.workerActive && state.timersBound && fixture->active &&
            !fixture->released && !fixture->unmapped,
            "real thirty second cancellation deadline stays fixed without fake PM acknowledgement or DMA stop");
        delete owner;
        expect(s540GspDiagnosticLifetimePinCount() == 1 && fixture->active && fixtureState &&
            !fixture->released && !fixture->unmapped && page.bytes[0] == 0x5a && s540DarwinLiveObjects(),
            "facade destruction preserves operational Impl, callback services, backing and image pin");
    }
