static void s540PreparationReset(S540PreparationObservation &value) {
    value = S540PreparationObservation{};
    value.format = 1; value.bytes = sizeof(value);
    value.firstFailureStatus = value.lastStatus = NV_ERR_NOT_READY;
}
static void s540PreparationStage(S540PreparationObservation &value, NvU32 stage) {
    value.stage = stage;
    value.observedMask = (value.observedMask | S540_PREP_OBS_STAGE) & ~NvU32(S540_PREP_OBS_STATUS);
}
static void s540PreparationCompleted(S540PreparationObservation &value) {
    value.lastCompleted = value.stage; value.lastStatus = NV_OK;
    value.observedMask |= S540_PREP_OBS_STATUS;
}
static NV_STATUS s540PreparationFailed(S540PreparationObservation &value, NV_STATUS status) {
    value.lastStatus = status; value.observedMask |= S540_PREP_OBS_STATUS;
    if (!(value.observedMask & S540_PREP_OBS_FIRST_FAILURE)) {
        value.firstFailureStage = value.stage; value.firstFailureStatus = status;
        value.observedMask |= S540_PREP_OBS_FIRST_FAILURE;
    }
    return status;
}
static_assert(sizeof(S540PreparationObservation) == 104, "preparation observation ABI");
static_assert(sizeof(S540PreparationPowerObservation) == 56, "PM observation ABI");
static_assert(NvU32(S540_PREP_HOST_NOTEBOOK) == NvU32(S540_GLOBAL_FACT_NOTEBOOK) &&
    NvU32(S540_PREP_HOST_BATTERY) == NvU32(S540_GLOBAL_FACT_BATTERY) &&
    NvU32(S540_PREP_HOST_EFI) == NvU32(S540_GLOBAL_FACT_EFI) &&
    NvU32(S540_PREP_HOST_VGPU_HYPERVISOR) == NvU32(S540_GLOBAL_FACT_VGPU_HYPERVISOR) &&
    NvU32(S540_PREP_HOST_NVSWITCH) == NvU32(S540_GLOBAL_FACT_NVSWITCH) &&
    NvU32(S540_PREP_HOST_S0IX) == NvU32(S540_GLOBAL_FACT_S0IX) &&
    NvU32(S540_PREP_HOST_CPU) == NvU32(S540_GLOBAL_FACT_CPU) &&
    NvU32(S540_PREP_HOST_OS_VERSION) == NvU32(S540_GLOBAL_FACT_OS_VERSION) &&
    NvU32(S540_PREP_HOST_ALL) == NvU32(S540_GLOBAL_FACT_ALL), "host fact bit identities");
