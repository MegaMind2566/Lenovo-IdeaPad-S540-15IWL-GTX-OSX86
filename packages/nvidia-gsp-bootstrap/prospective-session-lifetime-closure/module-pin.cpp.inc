// A reservation pins text during actual Session acquisition. Failed acquisition
// releases only that reservation; a hardware lifetime hold has no decrement path.
static NvU32 s540DiagnosticLifetimePins;
extern "C" NvU32 s540GspDiagnosticLifetimePinCount(void) {
    return __atomic_load_n(&s540DiagnosticLifetimePins, __ATOMIC_ACQUIRE);
}
static NV_STATUS s540ReserveDiagnosticModulePin(void) {
    NvU32 before = s540GspDiagnosticLifetimePinCount();
    for (;;) {
        if (before == ~NvU32{0}) return NV_ERR_INSUFFICIENT_RESOURCES;
        if (__atomic_compare_exchange_n(&s540DiagnosticLifetimePins, &before, before+1U,
                false, __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE)) return NV_OK;
    }
}
static void s540CancelDiagnosticModuleReservation(void) {
    const NvU32 before = __atomic_fetch_sub(&s540DiagnosticLifetimePins, 1U, __ATOMIC_ACQ_REL);
    if (!before) __builtin_trap();
}
