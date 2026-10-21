    NV_STATUS installDiagnosticInterrupts() {
        if (!owned() || !state.prepared || !context || !diagnosticLifetimeHeld ||
            !transport.hardwareDmaLifetimeHeld()) return NV_ERR_INVALID_STATE;
        return irqBinding.install(context, &transport, &power, this, thread,
            __atomic_load_n(&cancellationToken, __ATOMIC_ACQUIRE));
    }
    NV_STATUS quiesceDiagnosticInterrupts() {
        if (!owned() || !diagnosticLifetimeHeld) return NV_ERR_INVALID_STATE;
        return irqBinding.quiesce();
    }
